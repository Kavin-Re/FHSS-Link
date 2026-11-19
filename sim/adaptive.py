"""Adaptive channel selection (defender) and interference environments.

Defender policies pick one channel per slot and learn from ACK feedback (success / fail):
  blind     uniform over all channels (what a keyed PRF schedule gives)
  afh       Bluetooth-AFH style: EWMA success per channel, blacklist weak channels, always keep a probing floor
  ucb       UCB1 on channel success (deterministic: predictable if the learner state leaks)
  thompson  discounted Beta-Bernoulli Thompson sampling (randomised)
  mixed     epsilon-uniform floor on top of Thompson (randomisation kept on purpose)
Jammers (all are models of an own-link test source):
  static, sweep, random, freq (jams our most-used channel: attacks adaptive defenders), moving (static set that relocates)
"""
import numpy as np


class Blind:
    def __init__(self, M, rng): self.M, self.rng = M, rng
    def pick(self): return int(self.rng.integers(self.M))
    def update(self, c, ok): pass


class AFH:
    def __init__(self, M, rng, alpha=0.05, thr=0.5, floor=0.1, min_good=None):
        self.M, self.rng, self.a, self.thr, self.floor = M, rng, alpha, thr, floor
        self.q = np.full(M, 0.9); self.min_good = min_good or max(2, M // 2)

    def pick(self):
        if self.rng.random() < self.floor:
            return int(self.rng.integers(self.M))
        good = np.flatnonzero(self.q >= self.thr)
        if len(good) < self.min_good:
            good = np.argsort(-self.q)[: self.min_good]
        return int(self.rng.choice(good))

    def update(self, c, ok): self.q[c] += self.a * (ok - self.q[c])


class UCB:
    def __init__(self, M, rng): self.M, self.n, self.s, self.t = M, np.zeros(M), np.zeros(M), 0
    def pick(self):
        self.t += 1
        un = np.flatnonzero(self.n == 0)
        if len(un): return int(un[0])
        return int(np.argmax(self.s / self.n + np.sqrt(2 * np.log(self.t) / self.n)))
    def update(self, c, ok): self.n[c] += 1; self.s[c] += ok


class Thompson:
    def __init__(self, M, rng, gamma=0.99, eps=0.0):
        self.M, self.rng, self.g, self.eps = M, rng, gamma, eps
        self.a, self.b = np.ones(M), np.ones(M)

    def pick(self):
        if self.eps and self.rng.random() < self.eps:
            return int(self.rng.integers(self.M))
        return int(np.argmax(self.rng.beta(self.a, self.b)))

    def update(self, c, ok):
        self.a *= self.g; self.b *= self.g
        self.a = np.maximum(self.a, 1e-3); self.b = np.maximum(self.b, 1e-3)
        self.a[c] += ok; self.b[c] += 1 - ok


def make_policy(name, M, rng):
    return {"blind": Blind, "afh": AFH, "ucb": UCB, "thompson": Thompson,
            "mixed": lambda M, r: Thompson(M, r, eps=0.2)}[name](M, rng)


class Jammer:
    def __init__(self, kind, M, rng, k=2, move_every=500):
        self.kind, self.M, self.rng, self.k, self.me = kind, M, rng, k, move_every
        self.cnt = np.zeros(M); self.t = 0; self.set = set(rng.choice(M, k, replace=False).tolist())

    def jammed(self):
        """Set of channels jammed this slot (decided BEFORE seeing this slot's channel)."""
        t = self.t
        if self.kind == "static": return set(range(self.k))
        if self.kind == "sweep": return {t % self.M}
        if self.kind == "random": return {int(self.rng.integers(self.M))}
        if self.kind == "freq":
            m = self.cnt.max()
            return {int(self.rng.choice(np.flatnonzero(self.cnt >= m - 1e-9)))}
        if self.kind == "moving":
            if t % self.me == 0 and t:
                self.set = set(self.rng.choice(self.M, self.k, replace=False).tolist())
            return self.set
        return set()

    def observe(self, c):
        self.cnt *= 0.995; self.cnt[c] += 1; self.t += 1


def simulate(policy, jammer, M=13, slots=10000, p_jam=0.95, p_clean=0.01, seed=1):
    rng = np.random.default_rng(seed)
    pol = make_policy(policy, M, np.random.default_rng(seed + 1000))
    jam = Jammer(jammer, M, np.random.default_rng(seed + 2000))
    ok_hist = np.zeros(slots)
    for t in range(slots):
        J = jam.jammed()
        c = pol.pick()
        ok = rng.random() > (p_jam if c in J else p_clean)
        pol.update(c, float(ok)); jam.observe(c); ok_hist[t] = ok
    return ok_hist


if __name__ == "__main__":
    import sys
    print("policy x jammer -> PDR (mean of 3 seeds, 8000 slots, M=13)")
    JS = ["static", "sweep", "random", "freq", "moving"]
    PS = ["blind", "afh", "ucb", "thompson", "mixed"]
    tab = {}
    for p in PS:
        for j in JS:
            tab[(p, j)] = float(np.mean([simulate(p, j, slots=8000, seed=s).mean() for s in (1, 2, 3)]))
        print(f"{p:9s}", {j: round(tab[(p, j)], 3) for j in JS}, flush=True)
    import json; json.dump({f"{p}|{j}": v for (p, j), v in tab.items()}, open("figures/adaptive_table.json", "w"), indent=1)
