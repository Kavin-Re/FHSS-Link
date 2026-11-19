"""Experiment 5 - replay / forgery attacks vs a rolling counter + truncated HMAC-SHA256 (simulation only; stdlib hmac, no network).

Packet = counter (32-bit) | payload (8 B) | tag = HMAC-SHA256(key, counter||payload) truncated to tag_bits.
Channel: each legitimate packet is lost with prob p_loss (the attacker still records every packet it hears: worst case) and delivered
packets are delayed by a geometric reorder jitter. Receiver schemes:
  crc_only      accepts anything well-formed (an attacker computes CRCs)
  counter_only  rolling counter with a sliding window W, no MAC
  mac_only      accepts any valid tag
  mac_counter   valid tag AND counter fresh: c > highest, or within W of highest and not seen before
Attacks (attacker has NO key): replay_old (re-send a recorded packet verbatim), replay_inc (recorded packet with its counter field bumped to highest+1),
forge (counter highest+1, chosen payload, random tag). 'delayed replay of a jammed packet' = packet the receiver never got, replayed after delta later packets.
Known limit (tested, not hidden): an immediate relay of a genuine packet is accepted; counters give freshness only to within W, not distance bounding.
"""
import hmac, hashlib, struct
import numpy as np
import _common as cm
from _common import C, plt

KEY = b"lab5-test-key-not-a-secret-0123456789"


def tag_of(counter, payload, bits, key=KEY):
    t = hmac.new(key, struct.pack(">I", counter) + payload, hashlib.sha256).digest()
    return int.from_bytes(t, "big") >> (256 - bits)


class Receiver:
    def __init__(self, scheme, W=64, bits=32):
        self.s, self.W, self.bits, self.hi, self.seen = scheme, W, bits, -1, set()

    def _fresh(self, c):
        if c > self.hi: return True
        return (self.hi - c) < self.W and c not in self.seen

    def accept(self, c, payload, tag):
        s = self.s
        if s == "crc_only": return True
        if s in ("mac_only", "mac_counter") and tag != tag_of(c, payload, self.bits): return False
        if s == "mac_only": return True
        if not self._fresh(c): return False
        self.seen.add(c); self.hi = max(self.hi, c)
        if len(self.seen) > 4 * self.W: self.seen = {x for x in self.seen if self.hi - x < self.W}
        return True


def scenario(scheme, W=64, bits=32, n=4000, p_loss=0.2, p_reorder=0.3, p_atk=0.3, seed=1):
    rng = np.random.default_rng(seed); rx = Receiver(scheme, W, bits)
    sent = {}; arrivals = []                                   # (arrival_time, kind, counter, payload, tag, meta)
    for i in range(n):
        pay = rng.integers(0, 256, 8, dtype=np.uint8).tobytes(); sent[i] = (pay, tag_of(i, pay, bits))
        delay = 0 if rng.random() > p_reorder else int(rng.geometric(0.4))
        if rng.random() > p_loss: arrivals.append((i + delay + 0.5, "legit", i, *sent[i]))
        # attacker acts at time i+0.9 after the legit slot
        if rng.random() < p_atk and i > 10:
            kind = rng.choice(["replay_old", "replay_inc", "forge"]); j = int(rng.integers(0, i))
            if kind == "replay_old": arrivals.append((i + 0.9, kind, j, *sent[j]))
            elif kind == "replay_inc": arrivals.append((i + 0.9, kind, i, sent[j][0], sent[j][1]))   # old payload+tag, counter bumped to i
            else: arrivals.append((i + 0.9, kind, i, rng.integers(0, 256, 8, dtype=np.uint8).tobytes(), int(rng.integers(0, 1 << bits))))
    arrivals.sort(key=lambda a: a[0])
    delivered_legit = acc_legit = 0; att = {"replay_old": [0, 0], "replay_inc": [0, 0], "forge": [0, 0]}
    accepted_before = set(); dup_accepted = 0
    for t, kind, c, pay, tag in arrivals:
        ok = rx.accept(c, pay, tag)
        if kind == "legit": delivered_legit += 1; acc_legit += ok
        else:
            att[kind][0] += 1; att[kind][1] += ok
            if kind == "replay_old" and ok and c in accepted_before: dup_accepted += 1     # replay of a packet already accepted earlier
        if ok and c is not None and kind in ("legit", "replay_old"): accepted_before.add(c)
    return dict(legit_accept=acc_legit / max(1, delivered_legit), dup_accepted=dup_accepted, **{k: (v[1] / max(1, v[0])) for k, v in att.items()})


def forgery_rate(bits, attempts=200_000, seed=5):
    rng = np.random.default_rng(seed); rx = Receiver("mac_only", bits=bits); hits = 0
    guesses = rng.integers(0, 1 << bits, attempts, dtype=np.int64); pay = b"\x00" * 8
    for g in guesses.tolist(): hits += rx.accept(1, pay, g)
    return hits / attempts


def delayed_jammed_replay(delta, W, seed=2, n=400):
    """Attacker jams packet c0 (receiver never gets it) and records it; replays after `delta` later packets were delivered. Accepted?"""
    rx = Receiver("mac_counter", W, 32); c0 = 100; pay = b"STOPNOW!"
    for c in range(0, c0): rx.accept(c, b"x" * 8, tag_of(c, b"x" * 8, 32))
    for c in range(c0 + 1, c0 + 1 + delta): rx.accept(c, b"y" * 8, tag_of(c, b"y" * 8, 32))
    return rx.accept(c0, pay, tag_of(c0, pay, 32))


def false_reject(W, p_reorder, p_loss=0.1, n=6000, seed=3):
    r = scenario("mac_counter", W=W, n=n, p_loss=p_loss, p_reorder=p_reorder, p_atk=0.0, seed=seed); return 1 - r["legit_accept"]


def main():
    lines = []; table = {}
    for sch in ("crc_only", "counter_only", "mac_only", "mac_counter"):
        r = [scenario(sch, seed=s) for s in (1, 2, 3)]; table[sch] = {k: float(np.mean([x[k] for x in r])) for k in r[0]}
        lines.append(f"{sch:13s} legit accepted {table[sch]['legit_accept']:.3f} | attacker accepted: replay_old {table[sch]['replay_old']:.3f}  replay_inc {table[sch]['replay_inc']:.3f}  forge {table[sch]['forge']:.3f}")
    bits_l = [4, 6, 8, 10, 12, 16]; fr = [forgery_rate(b) for b in bits_l]
    lines.append("forgery success vs tag bits (200k guesses): " + ", ".join(f"{b}b {f:.2e} (2^-b={2.0 ** -b:.2e})" for b, f in zip(bits_l, fr)))
    deltas = list(range(0, 130, 4)); Ws = [8, 32, 64]; dr = {W: [float(delayed_jammed_replay(d, W)) for d in deltas] for W in Ws}
    lines.append("delayed replay of a jammed-and-recorded packet accepted? first delta rejected per W: " + ", ".join(f"W={W}: {next((d for d, a in zip(deltas, dr[W]) if not a), None)}" for W in Ws))
    rr = [0.0, 0.1, 0.3, 0.5]; Wl = [1, 2, 4, 8, 16, 32, 64]; fre = {p: [false_reject(W, p) for W in Wl] for p in rr}
    for p in rr: lines.append(f"legit false-reject (p_reorder={p}) vs W={Wl}: " + " ".join(f"{x:.4f}" for x in fre[p]))
    # immediate relay
    rx = Receiver("mac_counter", 64, 32); pay = b"12345678"; relay_first = rx.accept(5, pay, tag_of(5, pay, 32)); orig_after = rx.accept(5, pay, tag_of(5, pay, 32))
    lines.append(f"immediate relay: relayed copy accepted={relay_first}, original then accepted={orig_after} (counter+MAC give no distance bounding)")
    print("\n".join(lines))
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.2))
    names = ["crc_only", "counter_only", "mac_only", "mac_counter"]; atks = ["replay_old", "replay_inc", "forge", "legit_accept"]
    mat = np.array([[table[n][a] for a in atks] for n in names]); im = ax[0].imshow(mat, vmin=0, vmax=1, cmap="Blues")
    ax[0].set_xticks(range(4)); ax[0].set_xticklabels(["replay\nold", "replay,\ncounter bumped", "forge\n(random tag)", "LEGIT\naccepted"], fontsize=7); ax[0].set_yticks(range(4)); ax[0].set_yticklabels(names, fontsize=8); ax[0].grid(False)
    for i in range(4):
        for j in range(4): ax[0].text(j, i, f"{mat[i, j]:.2f}", ha="center", va="center", color="white" if mat[i, j] > 0.55 else "black", fontsize=9)
    ax[0].set_title("fraction accepted (loss 20%, reorder 30%, W=64, 32-bit tag)")
    ax[1].semilogy(bits_l, np.maximum(fr, 1e-6), "o", color=C["blue"], label="measured (200k guesses)"); xs = np.linspace(4, 16, 50); ax[1].semilogy(xs, 2.0 ** -xs, "-", color=C["black"], label="2^-bits"); ax[1].set_xlabel("tag bits"); ax[1].set_ylabel("forgery success per attempt"); ax[1].legend(); ax[1].set_title("forgery vs truncated tag length")
    ax2 = ax[1].twinx(); ax2.axis("off")
    for W, c in zip(Ws, [C["sky"], C["blue"], C["black"]]): ax[2].step(deltas, dr[W], where="post", color=c, label=f"delayed replay accepted, W={W}")
    ax[2].set_xlabel("delay (packets) before replaying a jammed packet"); ax[2].set_ylabel("accepted (1) / rejected (0)"); ax[2].legend(loc="center right")
    ax[2].set_title("freshness is only as tight as the window")
    cm.save_fig(fig, "fig5_replay_mac.png")
    cm.save_json("exp5_replay_mac.json", dict(table=table, forgery=dict(zip(map(str, bits_l), fr)), delayed={str(W): dr[W] for W in Ws}, deltas=deltas, false_reject={str(p): v for p, v in fre.items()}, Wl=Wl))
    open(cm.os.path.join(cm.OUT, "exp5_replay_mac.txt"), "w").write("\n".join(lines) + "\n")
    return table


if __name__ == "__main__":
    main()
