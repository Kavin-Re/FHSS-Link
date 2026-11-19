"""Beyond #20: electric-fish Jamming Avoidance Response (JAR) as a defender, compared with the bandit policies (simulation only).
Eigenmannia shifts its discharge frequency AWAY from a close interferer (sign of the beat decides the direction). Here: 13 channels on a line,
a narrowband jammer with adjacent-channel leakage (loss prob 0.95 / 0.60 / 0.25 at distance 0 / 1 / 2, else 0.01).
Defenders: fixed, blind-uniform, AFH, Thompson, UCB (ACK feedback only, from sim/adaptive.py read-only), and
  JAR       senses the jammer's channel when it is within +-3 channels (RSSI-like sensing, which the bandits do NOT get) and steps one channel away
            if it is within 2; at a band edge it cannot step away and stays (pure fish rule);
  JAR+jump  same, but at an edge it jumps to the far side (a non-biological fix);
  JAR+eps   JAR with 10 % uniform random hops (randomisation against a jammer that learns the rule).
Jammers: static(6); sweep (+1 channel / 5 slots); drift (random walk, 10 %/slot); follow-last (jams the channel used in the previous slot);
  tracker (moves one channel per slot toward the defender's last channel: it cannot be outrun by 1-channel steps, so it defeats the 'step away' rule)."""
import numpy as np
from _common import *
from adaptive import make_policy

M = 13
def p_loss(d): return np.where(d == 0, 0.95, np.where(d == 1, 0.60, np.where(d == 2, 0.25, 0.01)))

class Fixed:
    def __init__(self, M, rng, c=6): self.c = c
    def pick(self): return self.c
    def update(self, c, ok): pass

class JAR:
    def __init__(self, M, rng, jump=False, eps=0.0):
        self.M, self.rng, self.jump, self.eps = M, rng, jump, eps
        self.c = M // 2; self.jam = None; self.dir = 1
    def pick(self):
        if self.eps and self.rng.random() < self.eps: self.c = int(self.rng.integers(self.M)); return self.c
        if self.jam is not None:
            o = self.c - self.jam
            if abs(o) <= 2:
                step = int(np.sign(o)) if o != 0 else self.dir
                self.dir = step if step else self.dir
                nc = self.c + step
                if 0 <= nc < self.M: self.c = nc
                elif self.jump: self.c = int(np.argmax(np.abs(np.arange(self.M) - self.jam)))
        return self.c
    def sense(self, jam_pos):
        self.jam = jam_pos if abs(jam_pos - self.c) <= 3 else None
    def update(self, c, ok): pass

def make_def(name, rng):
    if name == "fixed": return Fixed(M, rng)
    if name == "JAR": return JAR(M, rng)
    if name == "JAR+jump": return JAR(M, rng, jump=True)
    if name == "JAR+eps": return JAR(M, rng, jump=True, eps=0.1)
    return make_policy(name, M, rng)

class Jam:
    def __init__(self, kind, rng):
        self.kind, self.rng, self.pos, self.t = kind, rng, 6, 0
    def move(self, my_last):
        k = self.kind; self.t += 1
        if k == "static": self.pos = 6
        elif k == "sweep":
            if self.t % 5 == 0: self.pos = (self.pos + 1) % M
        elif k == "drift":
            if self.rng.random() < 0.1: self.pos = int(np.clip(self.pos + self.rng.choice([-1, 1]), 0, M - 1))
        elif k == "follow-last": self.pos = my_last if my_last is not None else 6
        elif k == "tracker": self.pos = int(self.pos + np.sign(my_last - self.pos)) if my_last is not None else self.pos
        return self.pos

DEFS = ["fixed", "blind", "afh", "thompson", "ucb", "JAR", "JAR+jump", "JAR+eps"]
JAMS = ["static", "sweep", "drift", "follow-last", "tracker"]

def episode(dname, jname, slots, seed):
    rng = np.random.default_rng(seed); d = make_def(dname, rng); j = Jam(jname, rng)
    last = None; ok_sum = 0
    for t in range(slots):
        c = d.pick()
        pos = j.move(last)
        ok = int(rng.random() >= p_loss(np.array(abs(c - pos))))
        d.update(c, ok)
        if hasattr(d, "sense"): d.sense(pos)
        last = c; ok_sum += ok
    return ok_sum / slots

def run(fast=False):
    slots, seeds = (1500, 2) if fast else (4000, 5)
    mat = np.zeros((len(DEFS), len(JAMS)))
    for i, dn in enumerate(DEFS):
        for k, jn in enumerate(JAMS):
            mat[i, k] = np.mean([episode(dn, jn, slots, 100 * s + 7) for s in range(seeds)])
    return dict(defs=DEFS, jams=JAMS, delivery=mat.tolist(), slots=slots, seeds=seeds)

def main():
    out = run(); mat = np.array(out["delivery"])
    print("delivery ratio (rows defenders, cols jammers):", out["jams"])
    for dn, row in zip(DEFS, mat): print(f"  {dn:9s}", "  ".join(f"{v:.3f}" for v in row), f"| worst {row.min():.3f}")
    fig, ax = plt.subplots(figsize=(8, 3.8))
    w = 0.8 / len(DEFS); cols = [C["grey"], C["sky"], C["blue"], C["green"], C["yellow"], C["verm"], C["orange"], C["pink"]]
    for i, dn in enumerate(DEFS):
        ax.bar(np.arange(len(JAMS)) + i * w, mat[i], w, label=dn, color=cols[i])
    ax.set_xticks(np.arange(len(JAMS)) + 0.4 - w / 2); ax.set_xticklabels(JAMS); ax.set_ylabel("delivery ratio"); ax.set_ylim(0, 1.05); ax.legend(ncol=4, loc="lower left")
    save_fig(fig, "b20_fish.png"); save_json("b20_fish.json", out)
    d = {n: i for i, n in enumerate(DEFS)}; j = {n: k for k, n in enumerate(JAMS)}
    key("B20", f"vs static jammer: JAR {mat[d['JAR'], j['static']]:.3f} vs Thompson {mat[d['thompson'], j['static']]:.3f}; vs tracker jammer JAR {mat[d['JAR'], j['tracker']]:.3f} (JAR+eps {mat[d['JAR+eps'], j['tracker']]:.3f}); worst case JAR {mat[d['JAR']].min():.3f}, JAR+eps {mat[d['JAR+eps']].min():.3f}, Thompson {mat[d['thompson']].min():.3f}")
if __name__ == "__main__":
    main()
