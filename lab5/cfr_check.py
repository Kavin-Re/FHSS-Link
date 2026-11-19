"""Experiment 7 - regret-matching(+) solver cross-checking the exact game value 0.9177 (M=13, k=1) and the EXP3 results of sim/game.py.

Game: defender picks a channel i of 13, jammer picks a set S of k channels; defender payoff = 0.99 if i not in S, 0.05 if i in S (sim/game.py constants).
Normal-form CFR with one information set per player IS regret matching, so this file implements regret matching+ (RM+, clipped cumulative regrets,
linear averaging) for both players with simultaneous updates; no LP, no scipy. Certificates: exploitability gap = max_j (x_avg^T A)_j... see gap().
Cross-checks: (a) RM+ value -> 0.91769 (k=1), 0.84538 (k=2); (b) average defender strategy -> uniform;
(c) the delivery that sim/game.py's EXP3 jammer extracts from each defender policy is compared with the guarantee min_j u^T A of the defender's EMPIRICAL channel usage u.
"""
from itertools import combinations
import numpy as np
import _common as cm
from _common import C, plt
import game as simgame      # existing sim/game.py (EXP3 jammer + play)

DEL_OK, DEL_JAM = 1 - cm.P_CLEAN, 1 - cm.P_JAM


def payoff(M=13, k=1):
    sets = list(combinations(range(M), k)); A = np.full((M, len(sets)), DEL_OK)
    for j, S in enumerate(sets):
        for i in S: A[i, j] = DEL_JAM
    return A


def gap(A, x, y):
    """Defender maximises x^T A y. lower = min_j x^T A_j (what x guarantees), upper = max_i (A y)_i (what y concedes). value in [lower, upper]."""
    return float((x @ A).min()), float((A @ y).max())


def rm_plus(A, T=20000, seed=0, checkpoints=None):
    m, n = A.shape; Rx, Ry = np.zeros(m), np.zeros(n); sx, sy = np.zeros(m), np.zeros(n)
    x, y = np.ones(m) / m, np.ones(n) / n; rng = np.random.default_rng(seed)
    Rx += rng.random(m) * 1e-3; Ry += rng.random(n) * 1e-3      # break symmetry slightly (the uniform fixed point is otherwise trivial)
    trace = []; cps = set(checkpoints or [])
    for t in range(1, T + 1):
        x = Rx / Rx.sum() if Rx.sum() > 0 else np.ones(m) / m; y = Ry / Ry.sum() if Ry.sum() > 0 else np.ones(n) / n
        ux = A @ y; uy = -(x @ A)                                   # utilities for the maximiser / the minimiser (zero-sum)
        Rx = np.maximum(Rx + ux - x @ ux, 0); Ry = np.maximum(Ry + uy - y @ uy, 0)
        sx += t * x; sy += t * y
        if t in cps:
            xa, ya = sx / sx.sum(), sy / sy.sum(); lo, up = gap(A, xa, ya); trace.append((t, lo, up))
    return sx / sx.sum(), sy / sy.sum(), trace


def empirical_guarantee(u, k=1):
    """Worst-case delivery the defender's empirical usage u gives against a k-set jammer who knows u: sort u, jam the k most used."""
    top = np.sort(u)[::-1][:k].sum(); return DEL_OK - (DEL_OK - DEL_JAM) * top


def exp3_vs_uniform(T=60000, seed=1, M=13, gamma=0.07):
    rng = np.random.default_rng(seed); jam = simgame.Exp3Jammer(M, np.random.default_rng(seed + 2), gamma=gamma)
    pay = np.zeros(T); pavg = np.zeros(M); n = 0
    for t in range(T):
        j = jam.pick(); c = int(rng.integers(M)); ok = rng.random() > (cm.P_JAM if c == j else cm.P_CLEAN); jam.feedback(1.0 - ok); pay[t] = ok
        if t >= T - 10000: pavg += jam.p; n += 1
    return pay, pavg / n


def main(T=20000):
    lines = []; out = {}
    cps = np.unique(np.round(np.logspace(1, np.log10(T), 25)).astype(int)).tolist()
    traces = {}
    for k in (1, 2):
        A = payoff(13, k); x, y, tr = rm_plus(A, T, checkpoints=cps); lo, up = gap(A, x, y); v = cm.game_value(13, k); traces[k] = tr
        out[f"k={k}"] = dict(value_formula=v, rm_lower=lo, rm_upper=up, gap=up - lo, max_dev_from_uniform=float(np.abs(x - 1 / 13).max()), n_jammer_sets=A.shape[1])
        lines.append(f"RM+ T={T} k={k}: formula value {v:.5f}; defender guarantees {lo:.5f}, jammer concedes at most {up:.5f}, gap {up - lo:.2e}; max |x_avg - 1/13| = {out[f'k={k}']['max_dev_from_uniform']:.2e}")
    # EXP3 cross-check
    pay, pavg = exp3_vs_uniform(); v1 = cm.game_value(13, 1)
    H = float(-(pavg * np.log2(pavg)).sum())
    out["exp3_vs_uniform"] = dict(mean_last10000=float(pay[-10000:].mean()), mean_all=float(pay.mean()), entropy_p_last10000=H, max_p=float(pavg.max()))
    lines.append(f"EXP3 (gamma=0.07) vs uniform hopping, 60000 slots: mean delivery {pay.mean():.4f} (value {v1:.4f}); EXP3 mixed strategy entropy {H:.3f} of {np.log2(13):.3f} bits, max p {pavg.max():.3f}")
    # sim/game.py policies: realised EXP3 delivery vs empirical guarantee
    rows = []
    for p in ("blind", "afh", "ucb", "thompson", "mixed"):
        rs = [simgame.play(p, slots=20000, seed=s) for s in (1, 2, 3)]
        last = float(np.mean([r[0][-5000:].mean() for r in rs])); u = np.mean([r[1] for r in rs], axis=0)
        g = empirical_guarantee(u, 1); rows.append((p, last, g, float(-(u[u > 0] * np.log2(u[u > 0])).sum())))
        lines.append(f"sim/game.py {p:9s} EXP3-extracted delivery (last 5000, 3 seeds) {last:.4f} | guarantee of its empirical usage {g:.4f} | value {v1:.4f} | usage entropy {rows[-1][3]:.2f}")
    out["policies"] = {r[0]: dict(exp3_delivery=r[1], guarantee=r[2], entropy=r[3]) for r in rows}
    print("\n".join(lines))
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.2))
    for k, c in ((1, C["blue"]), (2, C["verm"])):
        t = [a for a, _, _ in traces[k]]; g_ = [u - l for _, l, u in traces[k]]; ax[0].loglog(t, np.maximum(g_, 1e-9), "-o", ms=3, color=c, label=f"RM+ gap, k={k}")
    t = np.array(cps); ax[0].loglog(t, 1.0 / np.sqrt(t), "--", color=C["grey"], label="1/sqrt(T) reference"); ax[0].set_xlabel("iterations T"); ax[0].set_ylabel("exploitability gap (upper - lower bound)"); ax[0].legend(); ax[0].set_title("regret-matching+ convergence (13 x C(13,k))")
    for k, c in ((1, C["blue"]), (2, C["verm"])):
        ax[1].semilogx([a for a, _, _ in traces[k]], [l for _, l, _ in traces[k]], "-", color=c, label=f"defender guarantee k={k}"); ax[1].semilogx([a for a, _, _ in traces[k]], [u for _, _, u in traces[k]], "--", color=c, label=f"jammer concedes k={k}"); ax[1].axhline(cm.game_value(13, k), color="k", lw=0.6, ls=":")
    ax[1].set_ylim(0.8, 0.99); ax[1].set_xlabel("iterations T"); ax[1].set_ylabel("delivery"); ax[1].legend(fontsize=6); ax[1].set_title("bounds squeeze onto 0.9177 (k=1) and 0.8454 (k=2)")
    names = [r[0] for r in rows]; xx = np.arange(len(rows)); ax[2].bar(xx - 0.2, [r[1] for r in rows], 0.4, color=C["blue"], label="delivery extracted by EXP3 (sim/game.py)"); ax[2].bar(xx + 0.2, [r[2] for r in rows], 0.4, color=C["orange"], label="guarantee vs best-responding jammer")
    ax[2].axhline(v1, color="k", ls="--", lw=0.8); ax[2].text(len(rows) - 0.5, v1 + 0.004, "game value 0.9177", ha="right", fontsize=7); ax[2].set_xticks(xx); ax[2].set_xticklabels(names); ax[2].set_ylim(0.6, 1.0); ax[2].legend(fontsize=7, loc="lower left"); ax[2].set_title("EXP3 is not a best response; the guarantee is")
    cm.save_fig(fig, "fig7_cfr_check.png"); cm.save_json("exp7_cfr_check.json", out)
    open(cm.os.path.join(cm.OUT, "exp7_cfr_check.txt"), "w").write("\n".join(lines) + "\n")
    return out


if __name__ == "__main__":
    main()
