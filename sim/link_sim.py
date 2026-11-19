"""Packet-level FH link simulator (Layer 2 model, pre-hardware).

One packet per slot on channel h[t]. h comes from a 16-bit LFSR shared by TX and RX.
Interferer modes (a controlled test source on our own link):
  static  : sits on `k` fixed channels
  sweep   : one channel, advances by 1 every `dwell` slots
  random  : one uniformly random channel per slot (does not know our hop pattern)
  follower: guesses our channel correctly with prob `p_follow` (worst case / reactive jammer)
A packet is lost with prob p_jam on a jammed channel, p_clean otherwise.
Sync: RX clock drifts `drift` (fraction of a slot) per slot; a packet is lost when |offset| > guard;
every received packet carries a timestamp and resets the offset to 0.
ARQ: a lost packet is retried in the next slot(s), up to `max_tx` attempts.
"""
import numpy as np


def lfsr_hops(n, M, seed=0xACE1):
    """16-bit Fibonacci LFSR x^16+x^14+x^13+x^11+1, hop = state mod M."""
    s, out = seed, []
    for _ in range(n):
        bit = ((s >> 0) ^ (s >> 2) ^ (s >> 3) ^ (s >> 5)) & 1
        s = (s >> 1) | (bit << 15)
        out.append(s % M)
    return np.array(out)


def run(mode, M=13, slots=20000, hop=True, k=1, dwell=1, p_jam=0.95, p_clean=0.01,
        drift=0.0, guard=0.25, max_tx=1, p_follow=0.0, seed=1):
    rng = np.random.default_rng(seed)
    h = lfsr_hops(slots, M) if hop else np.zeros(slots, dtype=int)
    t, offset, sent, delivered, tx = 0, 0.0, 0, 0, 0
    while t < slots:
        sent += 1
        for _ in range(max_tx):
            if t >= slots:
                break
            tx += 1
            offset += drift
            if mode == "static":
                jam = h[t] < k
            elif mode == "sweep":
                jam = h[t] == (t // dwell) % M
            elif mode == "random":
                jam = h[t] == rng.integers(M)
            elif mode == "follower":
                jam = rng.random() < p_follow or h[t] == rng.integers(M)
            else:
                jam = False
            if abs(offset) > guard:
                ok = False
            else:
                ok = rng.random() > (p_jam if jam else p_clean)
            t += 1
            if ok:
                offset = 0.0
                delivered += 1
                break
    return dict(pdr=delivered / sent, goodput=delivered / slots, tx_per_packet=tx / sent)


if __name__ == "__main__":
    for name, kw in {"fixed, static jammer": dict(mode="static", hop=False),
                     "FH M=13, static": dict(mode="static"),
                     "FH M=13 +ARQ3, static": dict(mode="static", max_tx=3),
                     "FH M=13, sweep": dict(mode="sweep"),
                     "FH M=13, random": dict(mode="random"),
                     "FH M=13, follower 30%": dict(mode="follower", p_follow=0.3),
                     "FH M=13, drift 0.01/slot": dict(mode="static", drift=0.01),
                     "FH M=13, drift 0.30/slot (never resyncs)": dict(mode="static", drift=0.30)}.items():
        print(f"{name:44s}", {a: round(b, 3) for a, b in run(**kw).items()})
