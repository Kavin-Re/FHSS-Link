"""R5 (RED_TEAM idea 9) PRNG graveyard: how many observed hops until each hop-schedule generator is predicted, and what each costs.
Kerckhoffs: the attacker knows the algorithm, not the seed/key. Observed = the channel numbers of past hops (own-link simulation, no radio).
 - LCG 24-bit (a=1140671485, c=12820163, m=2^24), hop = (x>>8) mod 13. Attack: candidate-set filtering over all 2^24 states.
 - xorshift32, hop = x & 15 on a 16-channel plan (4 bits/hop). Attack: the generator is GF(2)-linear, so solve a linear system for the 32 state bits.
 - MT19937, 624 consecutive FULL 32-bit outputs leaked (e.g. in a plaintext nonce): untemper, clone the state, predict (checked against Python's random).
 - HMAC-SHA256 (keyed PRF): attacker uses its best generic predictor (repeat the most frequent channel seen); accuracy stays at chance 1/13.
Costs: relative CPU per hop in pure Python (indicative only)."""
import numpy as np, hmac, hashlib, random, time
from _common import *
A24, C24 = 1140671485, 12820163; M24 = 1 << 24

def lcg_stream(x, n):
    out = []
    for _ in range(n): x = (A24 * x + C24) % M24; out.append((x >> 8) % 13)
    return out

def lcg_attack(obs, extra_check=0):
    """obs = hops h1..hn where h_i = hop(x_i), x_i = step(x_{i-1}). Returns (surviving candidates for x_n, how many hops used)."""
    cand = np.arange(M24, dtype=np.uint64); used = 0   # candidates for x_1
    cand = cand[((cand >> np.uint64(8)) % np.uint64(13)) == obs[0]]; used = 1
    for i in range(1, len(obs)):
        cand = (np.uint64(A24) * cand + np.uint64(C24)) % np.uint64(M24)
        cand = cand[((cand >> np.uint64(8)) % np.uint64(13)) == obs[i]]; used = i + 1
        if len(cand) == 1: break
    return cand, used

def xs32(x):
    x ^= (x << 13) & 0xFFFFFFFF; x ^= x >> 17; x ^= (x << 5) & 0xFFFFFFFF; return x

def xorshift_attack(obs):
    """obs = low 4 bits of successive outputs o_1..o_n (o_i = state after i steps). Unknown x0 (32 bits). Output bits are linear in x0 over GF(2)."""
    # transition matrix columns: image of each basis vector
    Tm = [xs32(1 << j) for j in range(32)]                 # Tm[j] = T(e_j) as int
    def apply(vec): # vec: list of 32 column-ints representing a linear map from x0 bits -> current state bits; apply T to the map
        # state_bit_i of new = XOR over j of Tmatrix[i][j]*old_bit_j ; represent map as rows: row[i] = int bitmask over x0 bits
        new = [0] * 32
        for j in range(32):                                 # old bit j contributes to new bits that appear in T(e_j)
            tj = Tm[j]
            for i in range(32):
                if (tj >> i) & 1: new[i] ^= vec[j]
        return new
    rows = [1 << i for i in range(32)]                     # row[i] = mask of x0 bits that equal state bit i (identity)
    eqs = []
    for o in obs:
        rows = apply(rows)
        for b in range(4): eqs.append((rows[b], (o >> b) & 1))
    # Gaussian elimination over GF(2)
    piv = {}
    for m, v in eqs:
        for p, (pm, pv) in sorted(piv.items(), reverse=True):
            if (m >> p) & 1: m ^= pm; v ^= pv
        if m:
            p = m.bit_length() - 1; piv[p] = (m, v)
    if len(piv) < 32: return None, len(piv)
    sol = 0
    for p in sorted(piv):                                   # back-substitute in ascending pivot order
        m, v = piv[p]; rest = m & ~(1 << p)
        val = v ^ (bin(rest & sol).count("1") & 1)
        if val: sol |= 1 << p
    return sol, 32

def untemper(y):
    y ^= y >> 18
    y ^= (y << 15) & 0xEFC60000
    t = y
    for _ in range(5): t = y ^ ((t << 7) & 0x9D2C5680)
    y = t
    t = y
    for _ in range(3): t = y ^ (t >> 11)
    return t & 0xFFFFFFFF

def mt_clone(outputs624):
    r = random.Random(); r.setstate((3, tuple(untemper(o) for o in outputs624) + (624,), None)); return r

def hmac_hop(key, n): return int.from_bytes(hmac.new(key, n.to_bytes(8, "big"), hashlib.sha256).digest()[:4], "big") % 13

def run(seed=0, n_pred=300):
    rng = random.Random(seed); res = {}
    # LCG
    used_list = []
    for trial in range(5):
        x0 = rng.randrange(M24); st = lcg_stream(x0, 40); cand, used = lcg_attack(st[:30]); used_list.append(used)
        assert len(cand) == 1
        # predict the rest
        x = int(cand[0]); pred = []
        pred = []
        for i in range(used, 40):
            x = (A24 * x + C24) % M24; pred.append((x >> 8) % 13)
        assert pred == st[used:40], "LCG prediction mismatch"
    res["LCG24"] = dict(hops_needed=float(np.mean(used_list)), max=int(max(used_list)))
    # xorshift
    needs = []
    for trial in range(5):
        x0 = rng.randrange(1, 1 << 32); x = x0; o = []
        for _ in range(40): x = xs32(x); o.append(x & 15)
        for n in range(4, 40):
            sol, rank = xorshift_attack(o[:n])
            if sol is not None: break
        x = sol
        for i in range(n): x = xs32(x)
        pred = []
        for i in range(n, 40): x = xs32(x); pred.append(x & 15)
        assert pred == o[n:40], "xorshift prediction mismatch"; needs.append(n)
    res["xorshift32"] = dict(hops_needed=float(np.mean(needs)), max=int(max(needs)))
    # MT
    r = random.Random(rng.randrange(1 << 30)); outs = [r.getrandbits(32) for _ in range(624)]
    c = mt_clone(outs); ok = all(c.getrandbits(32) == r.getrandbits(32) for _ in range(2000))
    res["MT19937"] = dict(hops_needed=624, max=624, clone_ok=bool(ok))
    # HMAC: best generic predictor
    key_ = bytes(rng.randrange(256) for _ in range(16)); seq = [hmac_hop(key_, i) for i in range(4000)]
    hits = 0
    for i in range(1000, 4000):
        past = seq[:i]; guess = max(range(13), key=lambda ch: past.count(ch)) if i % 50 == 0 or i == 1000 else guess
        hits += (guess == seq[i])
    res["HMAC-SHA256"] = dict(hops_needed=None, accuracy=hits / 3000.0, chance=1 / 13)
    # costs
    def tm(f, n=20000):
        t = time.perf_counter(); f(n); return (time.perf_counter() - t) / n * 1e6
    def f_lcg(n):
        x = 1
        for _ in range(n): x = (A24 * x + C24) % M24; _h = (x >> 8) % 13
    def f_xs(n):
        x = 1
        for _ in range(n): x = xs32(x); _h = x & 15
    def f_mt(n):
        r = random.Random(1)
        for _ in range(n): _h = r.getrandbits(32) % 13
    def f_hm(n):
        for i in range(n): hmac_hop(b"k" * 16, i)
    res["cost_us_per_hop"] = dict(LCG24=tm(f_lcg), xorshift32=tm(f_xs), MT19937=tm(f_mt), HMAC_SHA256=tm(f_hm, 5000))
    return res

def main():
    res = run()
    for k in ("LCG24", "xorshift32", "MT19937", "HMAC-SHA256"): print(f"{k:12s} {res[k]}")
    print("cost (us/hop, pure Python):", {k: round(v, 2) for k, v in res["cost_us_per_hop"].items()})
    names = ["LCG24", "xorshift32", "MT19937 (32-bit leak)", "HMAC-SHA256"]; vals = [res["LCG24"]["hops_needed"], res["xorshift32"]["hops_needed"], 624, np.nan]
    fig, ax = plt.subplots(1, 2, figsize=(7.4, 3.3))
    ax[0].barh(names, [v if v == v else 0 for v in vals], color=[C["verm"], C["orange"], C["sky"], C["green"]]); ax[0].set_xscale("symlog"); ax[0].set_xlabel("observed hops to predict all future hops")
    ax[0].text(1, 3, " not predicted (accuracy %.3f, chance %.3f)" % (res["HMAC-SHA256"]["accuracy"], 1 / 13), va="center", fontsize=7); ax[0].invert_yaxis()
    cs = res["cost_us_per_hop"]; ax[1].bar(list(cs), list(cs.values()), color=C["grey"]); ax[1].set_ylabel("us per hop (pure Python)"); ax[1].tick_params(axis="x", labelsize=7)
    fig.suptitle("R5 PRNG graveyard", fontsize=9); save_fig(fig, "r5_prng_graveyard.png"); save_json("r5_prng_graveyard.json", res)
    key("hops observed to break LCG24 / xorshift32 / MT19937(32-bit leak) / HMAC", f"{res['LCG24']['hops_needed']:.1f} / {res['xorshift32']['hops_needed']:.1f} / 624 / unbroken (acc {res['HMAC-SHA256']['accuracy']:.3f})")
    return res
if __name__ == "__main__": main()
