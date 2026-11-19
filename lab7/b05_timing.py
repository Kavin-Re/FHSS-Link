"""Beyond #5: timing side channel on tag comparison (simulation only, our own toy verifier).
A verifier compares an 8-byte beacon tag with an early-exit loop; each matched byte adds `delta` to the response time,
and the network adds Gaussian jitter sigma. The attacker recovers the tag byte by byte (256 guesses/byte, n repeats each).
Fix: constant-time compare (response time independent of the match length).
Averaging n repeats of a guess is simulated as one draw with sigma/sqrt(n) (exact for Gaussian noise).
Key number: repeats per guess needed for >=90 % full-tag forgery at a given sigma/delta, vs the 2^64 brute force."""
import hmac, hashlib
import numpy as np
from _common import *

TAG_LEN = 8

def early_exit_compare(a: bytes, b: bytes):
    """Returns (equal, loop_iterations). Iterations = matched prefix + 1 (until first mismatch) -> the leak."""
    it = 0
    for x, y in zip(a, b):
        it += 1
        if x != y:
            return False, it
    return len(a) == len(b), it

def attack_exact(tag):
    """Noise-free sanity check against the real early-exit compare: iteration counts reveal the tag."""
    known = b""
    queries = 0
    for pos in range(TAG_LEN):
        best, bit = -1, 0
        for g in range(256):
            guess = known + bytes([g]) + bytes(TAG_LEN - pos - 1)
            eq, it = early_exit_compare(tag, guess); queries += 1
            score = it + (1 if eq else 0)      # last byte: the accept/reject answer itself is the signal
            if score > best: best, bit = score, g
        known += bytes([bit])
    return known, queries

def byte_success(sigma_over_delta, n, trials, rng, constant_time=False):
    """P(attacker picks the right byte among 256 candidates) with n averaged repeats per candidate."""
    noise = rng.normal(0, sigma_over_delta / np.sqrt(n), size=(trials, 256))
    t = noise.copy()
    if not constant_time:
        t[:, 0] += 1.0          # candidate 0 is the true byte; its time is longer by delta (=1 unit)
    return float(np.mean(np.argmax(t, axis=1) == 0))

def run(fast=False, seed=7):
    rng = np.random.default_rng(seed)
    trials = 1500 if fast else 6000
    ratios = [0.5, 1, 2, 4, 8]
    ns = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024]
    res = {"ratios": ratios, "ns": ns, "byte_p": {}, "tag_p": {}, "ct_byte_p": {}}
    for r in ratios:
        bp = [byte_success(r, n, trials, rng) for n in ns]
        res["byte_p"][r] = bp
        res["tag_p"][r] = [p ** TAG_LEN for p in bp]       # bytes are independent: full-tag success = p^8
    res["ct_byte_p"] = {n: byte_success(2, n, trials, rng, constant_time=True) for n in (1, 64, 1024)}
    # smallest n (grid) giving >=90 % full forgery
    need = {}
    for r in ratios:
        ok = [n for n, p in zip(ns, res["tag_p"][r]) if p >= 0.9]
        need[r] = ok[0] if ok else None
    res["need_n"] = need
    res["queries_at_need"] = {r: (None if n is None else n * 256 * TAG_LEN) for r, n in need.items()}
    return res

def main():
    tag = hmac.new(b"lab7-demo-key", b"beacon", hashlib.sha256).digest()[:TAG_LEN]
    rec, q = attack_exact(tag)
    print(f"noise-free: recovered tag == true tag: {rec == tag}, with {q} queries (brute force: 2^64 = {2**64:.2e})")
    res = run()
    for r in res["ratios"]:
        print(f"sigma/delta={r}: n for >=90% full forgery = {res['need_n'][r]}  (queries {res['queries_at_need'][r]})")
    print("constant-time compare, per-byte success (chance 1/256 = 0.0039):", {k: round(v, 4) for k, v in res["ct_byte_p"].items()})
    fig, ax = plt.subplots(1, 2, figsize=(9, 3.4))
    cols = [C["blue"], C["sky"], C["green"], C["orange"], C["verm"]]
    for r, c in zip(res["ratios"], cols):
        ax[0].semilogx(res["ns"], res["tag_p"][r], "o-", color=c, label=f"sigma/delta={r}")
    ax[0].axhline(0.9, color=C["grey"], ls="--", lw=.8)
    ax[0].plot(res["ns"], [res["ct_byte_p"].get(n, np.nan) for n in res["ns"]], "ks", label="constant-time (per byte)")
    ax[0].set_xlabel("repeats per guess n"); ax[0].set_ylabel("P(full 8-byte tag forged)"); ax[0].legend(); ax[0].set_title("early-exit compare")
    xs = [r for r in res["ratios"] if res["need_n"][r]]
    ax[1].loglog(xs, [res["queries_at_need"][r] for r in xs], "o-", color=C["verm"], label="early-exit: queries for 90 %")
    ax[1].axhline(2 ** 64, color=C["black"], ls=":", label="brute force 2^64")
    ax[1].set_xlabel("jitter / per-byte time gap"); ax[1].set_ylabel("queries"); ax[1].legend(); ax[1].set_title("cost of the attack")
    save_fig(fig, "b05_timing.png")
    save_json("b05_timing.json", {k: v for k, v in res.items()})
    key("B5", f"early-exit compare: sigma/delta=2 needs n={res['need_n'][2]} repeats/guess -> {res['queries_at_need'][2]} queries for 90% tag forgery (vs 2^64 brute force); constant-time stays at chance")
if __name__ == "__main__":
    main()
