"""Arms race: a learning jammer (EXP3, adversarial bandit) vs defender policies, both adapting at once.
The jammer picks ONE channel per slot and is rewarded when our packet is lost. Zero-sum, so the best the defender
can do is the game value; uniform random hopping guarantees 1 - p_jam/M + small, whatever the jammer learns."""
import numpy as np
from adaptive import make_policy


class Exp3Jammer:
    def __init__(self, M, rng, gamma=0.07):
        self.M, self.rng, self.g = M, rng, gamma
        self.w = np.ones(M); self.last = 0; self.p = np.ones(M) / M

    def pick(self):
        self.p = (1 - self.g) * self.w / self.w.sum() + self.g / self.M
        self.last = int(self.rng.choice(self.M, p=self.p)); return self.last

    def feedback(self, lost):
        xhat = lost / self.p[self.last]
        self.w[self.last] *= np.exp(self.g * xhat / self.M)
        self.w /= self.w.max()


def play(policy, M=13, slots=20000, p_jam=0.95, p_clean=0.01, seed=1):
    rng = np.random.default_rng(seed)
    pol = make_policy(policy, M, np.random.default_rng(seed + 1))
    jam = Exp3Jammer(M, np.random.default_rng(seed + 2))
    ok_hist = np.zeros(slots); use = np.zeros(M)
    for t in range(slots):
        j = jam.pick(); c = pol.pick()
        ok = rng.random() > (p_jam if c == j else p_clean)
        pol.update(c, float(ok)); jam.feedback(1.0 - ok); ok_hist[t] = ok; use[c] += 1
    return ok_hist, use / use.sum()


if __name__ == "__main__":
    import json
    out = {}
    print("defender vs EXP3 jammer, M=13: PDR first 2000 / last 5000 slots, defender channel entropy (max 3.70 bits)")
    for p in ["blind", "afh", "ucb", "thompson", "mixed"]:
        rs = [play(p, seed=s) for s in (1, 2, 3)]
        first = np.mean([r[0][:2000].mean() for r in rs]); last = np.mean([r[0][-5000:].mean() for r in rs])
        u = np.mean([r[1] for r in rs], axis=0); H = float(-(u[u > 0] * np.log2(u[u > 0])).sum())
        out[p] = dict(first=float(first), last=float(last), entropy=H)
        print(f"{p:9s} first {first:.3f}  last {last:.3f}  entropy {H:.2f}", flush=True)
    json.dump(out, open("figures/game_table.json", "w"), indent=1)
