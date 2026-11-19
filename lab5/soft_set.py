"""Experiment 4 - soft-set hopping vs a delayed reactive jammer (simulation only).

Reactive jammer: it senses the channel the defender uses in slot s and starts jamming it d slots later, and it can hold at most B channels
at once, so at slot t the jammed set is {c_s : t-d-B+1 <= s <= t-d} (the channels used in the B slots it saw most recently). d=0 means it reacts inside the slot.
PHY: lost with prob 0.95 on a jammed channel, 0.01 otherwise (sim/adaptive.py constants). M=13, B=3. One packet per slot; the defender changes channel every L slots (dwell).
Defenders:
  blind     uniform over all channels each dwell (the keyed schedule)
  hardset   uniform inside a fixed keyed subset of 6 channels (a 'hard' small set)
  soft(w)   'soft set': uniform among channels NOT used in the last w slots (cool-down). w = d+B makes every channel the jammer still holds
            ineligible (matched), w=6 is a mismatched fixed choice.
  thompson  discounted Thompson sampling from sim/adaptive.py (learning reference)
Second jammer ('rule-aware'): knows the soft-set rule and w, sees history up to t-d, and spends its B channels on channels that are still eligible.
Worst-case PDR = min over the two jammers. A soft set trades entropy for avoidance; the rule-aware jammer shows the price.
"""
import numpy as np
import _common as cm
from _common import C, plt
import adaptive

M, B = 13, 3


def simulate(policy, d, L=1, w=None, jammer="reactive", slots=6000, seed=1, Bj=B):
    rng = np.random.default_rng(seed); jr = np.random.default_rng(seed + 7); pr = np.random.default_rng(seed + 11)
    hist = []; ok_sum = 0; cur = 0
    hs = pr.choice(M, 6, replace=False); ts = adaptive.Thompson(M, np.random.default_rng(seed + 13)); elig_sum = 0.0
    wm = (d + Bj) if (policy == "soft" and w is None) else w
    for t in range(slots):
        if t % L == 0:
            if policy == "blind": cur = int(pr.integers(M))
            elif policy == "hardset": cur = int(pr.choice(hs))
            elif policy == "thompson": cur = ts.pick()
            else:
                recent = set(hist[max(0, t - wm):t]); el = [x for x in range(M) if x not in recent] or list(range(M))
                elig_sum += len(el) * L; cur = int(pr.choice(el))
        hist.append(cur)
        if jammer == "reactive": J = set(hist[max(0, t - d - Bj + 1): t - d + 1]) if t - d >= 0 else set()
        else:   # rule-aware: still-eligible channels given what it has seen (history up to t-d) and the cool-down rule
            seen = hist[: max(0, t - d + 1)]; recent = set(seen[max(0, t - wm):]) if policy == "soft" else set()
            cand = [x for x in range(M) if x not in recent]
            J = set(jr.choice(cand, min(Bj, len(cand)), replace=False).tolist())
        ok = rng.random() > (cm.P_JAM if cur in J else cm.P_CLEAN)
        ok_sum += ok; ts.update(cur, float(ok))
    return dict(pdr=ok_sum / slots, elig=(elig_sum / slots if policy == "soft" else float(M)))


def pdr(policy, d, L=1, w=None, jammer="reactive", seeds=(1, 2, 3), slots=6000):
    r = [simulate(policy, d, L, w, jammer, slots, s) for s in seeds]
    return float(np.mean([x["pdr"] for x in r])), float(np.mean([x["elig"] for x in r]))


def theory_blind(d, Bj=B, M=M):
    """Blind uniform vs reactive, L=1, d>=1: P(c_t in last-B-slots set) = 1-(1-1/M)^B (independent uniform draws)."""
    p = 1 - (1 - 1 / M) ** Bj
    return (1 - p) * (1 - cm.P_CLEAN) + p * (1 - cm.P_JAM)


def main(seeds=(1, 2, 3), slots=4000):
    ds = list(range(0, 13)); lines = []; res = {}
    pol = {"blind (keyed)": ("blind", None), "hard set of 6": ("hardset", None), "soft set, matched w=d+B": ("soft", None), "soft set, fixed w=6": ("soft", 6), "thompson": ("thompson", None)}
    for name, (p, w) in pol.items():
        for jm in ("reactive", "rule-aware"):
            if jm == "rule-aware" and p not in ("soft", "blind"): continue
            res[(name, jm)] = [pdr(p, d, 1, w, jm, seeds, slots) for d in ds]
            lines.append(f"{name:26s} {jm:11s} PDR vs d={ds[0]}..{ds[-1]}: " + " ".join(f"{v[0]:.3f}" for v in res[(name, jm)]))
    lines.append("soft(matched) eligible-set size vs d: " + " ".join(f"{v[1]:.1f}" for v in res[("soft set, matched w=d+B", "reactive")]))
    # dwell sweep at d=2
    Ls = [1, 2, 3, 4, 6, 8]; dw = {}
    for name, (p, w) in pol.items():
        if p in ("hardset",): continue
        dw[name] = [pdr(p, 2, L, w, "reactive", seeds, slots)[0] for L in Ls]; lines.append(f"dwell sweep d=2 {name:26s} L={Ls}: " + " ".join(f"{v:.3f}" for v in dw[name]))
    lines.append(f"theory blind vs reactive (L=1, d>=1, B=3): {theory_blind(1):.4f}; entropy cost: matched soft set leaves M-B-d eligible channels (10 at d=0, 1 at d=9; beyond d=9 w>12 cannot be honoured)")
    print("\n".join(lines))
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.2))
    cols = {"blind (keyed)": C["black"], "hard set of 6": C["grey"], "soft set, matched w=d+B": C["blue"], "soft set, fixed w=6": C["sky"], "thompson": C["orange"]}
    for name in pol:
        ax[0].plot(ds, [v[0] for v in res[(name, "reactive")]], "-o", ms=3, color=cols[name], label=name)
    for name in ("blind (keyed)", "soft set, matched w=d+B", "soft set, fixed w=6"):
        ax[1].plot(ds, [v[0] for v in res[(name, "rule-aware")]], "--s", ms=3, color=cols[name], label=name + " vs rule-aware")
        ax[1].plot(ds, [v[0] for v in res[(name, "reactive")]], ":", color=cols[name], alpha=0.6)
    ax[0].set_xlabel("jammer reaction delay d (slots)"); ax[0].set_ylabel("PDR"); ax[0].set_title("reactive jammer, B=3 held channels, dwell 1"); ax[0].legend(fontsize=7, loc="lower right")
    ax[1].set_xlabel("jammer reaction delay d (slots)"); ax[1].set_title("rule-aware jammer (dashed) vs reactive (dotted)"); ax[1].legend(fontsize=7, loc="lower right")
    for name in dw: ax[2].plot(Ls, dw[name], "-o", ms=3, color=cols[name], label=name)
    ax[2].set_xlabel("defender dwell L (slots per hop), d = 2"); ax[2].set_title("longer dwell hands the jammer its delay back"); ax[2].legend(fontsize=7)
    fig.suptitle("Soft-set hopping vs delayed reactive jammer (M=13)", fontsize=9)
    cm.save_fig(fig, "fig4_soft_set.png")
    cm.save_json("exp4_soft_set.json", {f"{k[0]}|{k[1]}": [v[0] for v in vs] for k, vs in res.items()} | {"dwell": dw, "ds": ds, "Ls": Ls})
    open(cm.os.path.join(cm.OUT, "exp4_soft_set.txt"), "w").write("\n".join(lines) + "\n")
    return res, dw


if __name__ == "__main__":
    main()
