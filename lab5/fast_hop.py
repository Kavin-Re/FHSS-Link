"""Experiment 2 - fast-hop jammer vs the defender's adaptation loop (simulation only).

A k=2 channel jammer RELOCATES to a fresh uniformly random pair every H slots (H = jammer dwell; H=1 is a per-slot random-pair jammer).
It does not observe the defender (open-loop), so it is the cheapest possible 'moving target': its only lever is its hop rate.
The defender's adaptation loop sees ACK feedback D slots late (D = feedback/reaction delay) and learns with the existing policies
from sim/adaptive.py: AFH (EWMA alpha=0.05), UCB1 (undiscounted), discounted Thompson (gamma=0.99), plus the keyed schedule = Blind (uniform; no learning).
PHY: lost with prob 0.95 on a jammed channel, 0.01 otherwise (as in sim/adaptive.py). Reference for the keyed schedule: 0.8454 (k=2, M=13).
"""
import sys, collections
import numpy as np
import _common as cm
from _common import C, plt
import adaptive

POLICIES = ["keyed", "afh", "ucb", "thompson"]
def make(name, M, rng): return adaptive.make_policy("blind" if name == "keyed" else name, M, rng)


def simulate(policy, H, D, M=13, k=2, slots=4000, seed=1):
    rng = np.random.default_rng(seed); pol = make(policy, M, np.random.default_rng(seed + 1000)); jr = np.random.default_rng(seed + 2000)
    S = set(jr.choice(M, k, replace=False).tolist()); q = collections.deque(); ok_sum = 0
    for t in range(slots):
        if t and t % H == 0: S = set(jr.choice(M, k, replace=False).tolist())
        c = pol.pick(); ok = rng.random() > (cm.P_JAM if c in S else cm.P_CLEAN); ok_sum += ok
        q.append((c, float(ok)))
        if len(q) > D:
            cc, oo = q.popleft(); pol.update(cc, oo)
    return ok_sum / slots


def grid(Hs, Ds, seeds=(1, 2, 3), slots=4000):
    return {(p, D, H): float(np.mean([simulate(p, H, D, slots=slots, seed=s) for s in seeds])) for p in POLICIES for D in Ds for H in Hs}


def main(Hs=(1, 2, 4, 8, 16, 32, 64, 128, 256, 1000), Ds=(0, 8, 32), seeds=(1, 2, 3), slots=4000):
    g = grid(Hs, Ds, seeds, slots); ref = cm.game_value(13, 2)
    lines = [f"PDR vs jammer dwell H (slots); k=2, M=13, keyed reference {ref:.4f}; feedback delay D"]
    summary = {}
    for D in Ds:
        lines.append(f"-- D = {D}")
        for p in POLICIES:
            lines.append(f"{p:9s} " + " ".join(f"H{H}:{g[(p, D, H)]:.3f}" for H in Hs))
        for p in POLICIES[1:]:
            gain = [H for H in Hs if g[(p, D, H)] >= g[("keyed", D, H)] + 0.02]
            harm = [H for H in Hs if g[(p, D, H)] <= g[("keyed", D, H)] - 0.02]
            summary[f"{p}|D={D}"] = dict(first_H_with_gain=(min(gain) if gain else None), H_with_harm=harm)
            lines.append(f"  {p}: first H where it beats keyed by >=0.02: {min(gain) if gain else 'never'};  H where it is >=0.02 WORSE than keyed: {harm}")
    print("\n".join(lines))
    fig, ax = plt.subplots(1, len(Ds), figsize=(4.6 * len(Ds), 4), sharey=True)
    col = dict(keyed=C["black"], afh=C["orange"], ucb=C["verm"], thompson=C["blue"])
    for a, D in zip(np.atleast_1d(ax), Ds):
        for p in POLICIES: a.plot(Hs, [g[(p, D, H)] for H in Hs], "-o", ms=3, color=col[p], label=p)
        a.axhline(ref, color=C["grey"], ls=":", lw=1); a.set_xscale("log"); a.set_xlabel("jammer dwell H (slots per relocation)"); a.set_title(f"feedback delay D = {D} slots")
        if D: a.axvline(D, color=C["grey"], ls="--", lw=0.8); a.text(D, 0.55, " H = D", fontsize=7, color=C["grey"])
    np.atleast_1d(ax)[0].set_ylabel("packet delivery ratio"); np.atleast_1d(ax)[0].legend(loc="lower right")
    fig.suptitle("Fast-hop jammer (k=2 of 13, open-loop) vs adaptation loops; dotted = keyed-schedule value 0.8454", fontsize=9)
    cm.save_fig(fig, "fig2_fast_hop.png")
    cm.save_json("exp2_fast_hop.json", dict(grid={f"{p}|D={D}|H={H}": v for (p, D, H), v in g.items()}, summary=summary, ref=ref))
    open(cm.os.path.join(cm.OUT, "exp2_fast_hop.txt"), "w").write("\n".join(lines) + "\n")
    return g, summary


if __name__ == "__main__":
    main()
