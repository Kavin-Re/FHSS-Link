"""R1 (RED_TEAM idea 1) Bandit poisoning. Simulation of our own learner vs a modelled jammer.
Phase 1 (poison, T1 slots): the jammer jams each of the 10 'good' channels with probability q every slot (so they LOOK bad) and leaves 3 bait
channels clean. A Thompson-sampling learner migrates to the bait and banks hundreds of successes there.
Phase 2 (T2 slots): the jammer drops the poison and jams the 3 bait channels (p=0.95). We measure delivery in phase 2.
Defences tested: uniform hopping (no learning), exploration floor eps, discounting gamma (forgetting)."""
import numpy as np
from _common import *

def run(policy, poison=True, T1=1500, T2=1500, seed=0, eps=0.0, gamma=1.0, n_bait=3, q=0.5, M=M_DEF):
    rng = np.random.default_rng(seed)
    bait = np.zeros(M, bool); bait[:n_bait] = True
    a = np.ones(M); b = np.ones(M); ph2 = []; ph1 = []; jam_cost = 0
    for t in range(T1 + T2):
        if policy == "uniform": c = int(rng.integers(M))
        elif rng.random() < eps: c = int(rng.integers(M))
        else: c = int(np.argmax(rng.beta(a, b)))
        if t < T1:
            jammed = poison and (not bait[c]) and rng.random() < q
            jam_cost += poison * (M - n_bait) * q
        else:
            jammed = bait[c]
        ok = rng.random() > (P_JAM if jammed else P_CLEAN)
        if policy != "uniform":
            if gamma < 1: a = 1 + gamma * (a - 1); b = 1 + gamma * (b - 1)
            if ok: a[c] += 1
            else: b[c] += 1
        (ph1 if t < T1 else ph2).append(ok)
    return dict(p1=float(np.mean(ph1)), p2=float(np.mean(ph2)), p2_first300=float(np.mean(ph2[:300])), jam_cost=jam_cost)

POL = {"uniform": dict(policy="uniform"),
       "Thompson": dict(policy="ts"),
       "Thompson + floor 0.1": dict(policy="ts", eps=0.1),
       "Thompson + discount 0.98": dict(policy="ts", gamma=0.98),
       "Thompson + both": dict(policy="ts", eps=0.1, gamma=0.98)}

def evaluate(seeds=range(8), **kw):
    res = {}
    for name, p in POL.items():
        for poison in (False, True):
            r = [run(poison=poison, seed=s, **p, **kw) for s in seeds]
            res[(name, poison)] = {k: float(np.mean([x[k] for x in r])) for k in r[0]}
    return res

def main():
    res = evaluate()
    print(f"{'policy':28s} {'clean p2':>9s} {'poisoned p2':>12s} {'poisoned first300':>18s}")
    for name in POL:
        print(f"{name:28s} {res[(name, False)]['p2']:9.3f} {res[(name, True)]['p2']:12.3f} {res[(name, True)]['p2_first300']:18.3f}")
    fig, ax = plt.subplots(figsize=(6.4, 3.4)); names = list(POL); x = np.arange(len(names))
    ax.bar(x - 0.2, [res[(n, False)]["p2"] for n in names], 0.4, color=C["sky"], label="no poisoning")
    ax.bar(x + 0.2, [res[(n, True)]["p2"] for n in names], 0.4, color=C["verm"], label="poisoned in phase 1")
    ax.set_xticks(x); ax.set_xticklabels([n.replace(" + ", "\n+ ") for n in names], fontsize=7); ax.set_ylabel("phase-2 delivery")
    ax.set_title("R1 bandit poisoning: banked trust in bait channels"); ax.legend(); ax.set_ylim(0, 1)
    save_fig(fig, "r1_bandit_poison.png"); save_json("r1_bandit_poison.json", {f"{k[0]}|poison={k[1]}": v for k, v in res.items()})
    key("Thompson delivery after poisoning (phase 2) vs uniform", f"{res[('Thompson', True)]['p2']:.3f} vs {res[('uniform', True)]['p2']:.3f}")
    return res
if __name__ == "__main__": main()
