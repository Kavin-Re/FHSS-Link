"""Module 4 - zero-sum jammer / defender matrix game, solved exactly (own simplex, no scipy).

Model / assumptions
- Defender picks one channel i of M per packet (mixed strategy x over channels). Jammer picks a set S of exactly k
  channels (power budget = k channels) and a jammed channel delivers with probability p_jam_deliv, a clean one with
  p_clean_deliv. Payoff to the defender = packet delivery probability (zero-sum; the jammer minimises it).
  In sim/game.py the loss probabilities are 0.95 (jammed) and 0.01 (clean), i.e. delivery 0.05 and 0.99; we use those.
- Cost variant: jammer may jam any set of size <= k, paying c per jammed channel; payoff to defender = delivery + c|S|
  (the jammer's net utility is minus that).
- Quality variant: channel i has clean delivery q_i and jammed delivery r*q_i (r=0.05).
- Solver: the game is turned into the LP  max sum z  s.t. B z <= 1 (B = payoff matrix shifted to be >= 1) and solved by a
  dense tableau simplex with Bland's rule. The jammer strategy is read from the basis, the defender strategy from the
  reduced costs of the slacks (the dual). The certificate is the duality gap
  max_i (A y)_i - min_j (x^T A)_j for the returned strategies, computed on the original matrix.
  An independent check uses Hedge (multiplicative weights) for both players with its proven average-regret bound.
- Analytic: uniform hopping gives, for ANY jammed set of size k,  v = p_clean - (k/M)(p_clean - p_jam).
  The jammer using a uniform random k-subset makes the defender indifferent, so this is the game value.
  (With p_clean=1 this is 1-(k/M)(1-p_jam); the sign convention in the task text had p_jam-p_clean.)
"""
import os, time
from itertools import combinations
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "figures")


def solve_matrix_game(A, eps=1e-11, maxit=200000):
    """A: (m,n) payoff to the row maximiser. Returns (value, x_row_strategy, y_col_strategy, iterations)."""
    A = np.asarray(A, float); m, n = A.shape
    shift = 1.0 - A.min(); B = A + shift
    tab = np.zeros((m + 1, n + m + 1))
    tab[:m, :n] = B; tab[:m, n:n + m] = np.eye(m); tab[:m, -1] = 1.0; tab[m, :n] = -1.0
    basis = list(range(n, n + m)); it = 0
    while it < maxit:
        neg = np.flatnonzero(tab[m, :-1] < -eps)
        if len(neg) == 0: break
        j = neg[0]; col = tab[:m, j]
        pos = np.flatnonzero(col > eps)
        ratios = tab[pos, -1] / col[pos]; rmin = ratios.min()
        cand = pos[ratios <= rmin + 1e-13]
        i = cand[np.argmin([basis[c] for c in cand])]
        tab[i] /= tab[i, j]
        for r in range(m + 1):
            if r != i and tab[r, j] != 0: tab[r] -= tab[r, j] * tab[i]
        basis[i] = j; it += 1
    z = np.zeros(n + m)
    for i, b in enumerate(basis): z[b] = tab[i, -1]
    s = tab[m, -1]; v = 1.0 / s
    y = z[:n] * v; x = tab[m, n:n + m] * v
    x = np.maximum(x, 0); y = np.maximum(y, 0); x /= x.sum(); y /= y.sum()
    return v - shift, x, y, it


def gap(A, x, y):
    return float(np.max(A @ y) - np.min(x @ A))


def hedge(A, T, seed=0):
    """Multiplicative weights for both players; returns (avg x, avg y, gap, proven bound on the gap)."""
    m, n = A.shape; R = float(A.max() - A.min())
    ex = R * np.sqrt(np.log(m) / (2 * T)); ey = R * np.sqrt(np.log(n) / (2 * T))
    etx = np.sqrt(8 * np.log(m) / T) / R; ety = np.sqrt(8 * np.log(n) / T) / R
    lx = np.zeros(m); ly = np.zeros(n); xs = np.zeros(m); ys = np.zeros(n)
    for t in range(T):
        x = np.exp(lx - lx.max()); x /= x.sum(); y = np.exp(ly - ly.max()); y /= y.sum()
        xs += x; ys += y
        lx += etx * (A @ y); ly -= ety * (x @ A)
    xb, yb = xs / T, ys / T
    return xb, yb, gap(A, xb, yb), ex + ey


def subsets(M, sizes):
    S = []
    for s in sizes: S += list(combinations(range(M), s))
    return S


def payoff_matrix(M, k, d_jam, d_clean, cost=0.0, sizes=None, q=None, r=None):
    """Defender rows i (channel), jammer columns = subsets. Homogeneous unless q (clean delivery per channel) and r given."""
    sizes = [k] if sizes is None else sizes
    S = subsets(M, sizes)
    A = np.zeros((M, len(S)))
    for j, s in enumerate(S):
        for i in range(M):
            if q is None:
                A[i, j] = d_jam if i in s else d_clean
            else:
                A[i, j] = q[i] * r if i in s else q[i]
        A[:, j] += cost * len(s)
    return A, S


def v_analytic(M, k, d_jam, d_clean):
    return d_clean - (k / M) * (d_clean - d_jam)


def v_hetero_k1(q, r):
    """k=1 closed form: x_j ~ 1/q_j on a support of the m best channels; value = c (m-1+r), c=1/sum(1/q)."""
    qs = np.sort(q)[::-1]; best = (-1, None)
    for m in range(1, len(qs) + 1):
        c = 1.0 / np.sum(1.0 / qs[:m]); v = c * (m - 1 + r)
        # valid only if excluded channels are not worth the jammer's attention (checked by the LP anyway)
        if v > best[0]: best = (v, m)
    return best


def main():
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from _budget import step
    dj, dc = 0.05, 0.99

    def s_cases():
        print("== homogeneous channels: LP value vs analytic, delivery jammed 0.05 / clean 0.99 unless stated ==")
        print("(M,k,d_jam,d_clean) | cols | LP value | analytic | |x-unif|max | jammer marginal/channel (k/M) | LP gap | simplex it | time")
        cases = [(13, 1, .05, .99), (13, 2, .05, .99), (13, 3, .05, .99), (13, 4, .05, .99), (13, 6, .05, .99),
                 (8, 1, .05, .99), (20, 2, .05, .99), (13, 1, .5, .99), (13, 1, .05, .8), (13, 3, .5, .8)]
        out = {}
        for (M, k, a, b) in cases:
            A, S = payoff_matrix(M, k, a, b)
            t0 = time.time(); v, x, y, it = solve_matrix_game(A); dt = time.time() - t0
            marg = np.zeros(M)
            for j, s in enumerate(S):
                for c in s: marg[c] += y[j]
            va = v_analytic(M, k, a, b)
            out[(M, k, a, b)] = (v, va, gap(A, x, y))
            print(f"({M:2d},{k},{a:.2f},{b:.2f}) | {A.shape[1]:5d} | {v:.6f} | {va:.6f} | {np.max(abs(x-1/M)):.1e} | {marg.min():.4f}..{marg.max():.4f} ({k/M:.4f}) | {gap(A,x,y):.1e} | {it:4d} | {dt:.2f}s")
        return out
    cases = step("gl", "cases2", s_cases)

    def s_exp3():
        import sys
        sys.path.insert(0, os.path.join(HERE, "..", "sim"))
        from game import play
        print("\n== EXP3 simulation from sim/game.py (M=13, one-channel EXP3 jammer, 20000 slots, 3 seeds) ==")
        out = {}
        for pol in ("blind", "mixed", "ucb"):
            rs = [play(pol, seed=s)[0] for s in (1, 2, 3)]
            out[pol] = float(np.mean([r[-5000:].mean() for r in rs]))
            print(f"{pol:6s} PDR last 5000 slots = {out[pol]:.4f}")
        print(f"game value (LP) M=13 k=1: {cases[(13, 1, .05, .99)][0]:.4f}; analytic {v_analytic(13, 1, dj, dc):.4f}")
        return out
    ex3 = step("gl", "exp3", s_exp3)

    def s_cost():
        print("\n== cost variant: M=13, k<=3, jammed set size 0..3, cost c per jammed channel (defender payoff = delivery + c|S|) ==")
        print("c      | LP value | analytic | jammer E|S| | gap")
        Delta = dc - dj; M, k = 13, 3
        A0, S0 = None, None
        for c in (0.0, 0.02, 0.05, 0.0723, 0.08, 0.1):
            A, S = payoff_matrix(M, k, dj, dc, cost=c, sizes=range(0, k + 1))
            v, x, y, it = solve_matrix_game(A)
            sz = float(sum(y[j] * len(s) for j, s in enumerate(S)))
            an = dc - k * max(0.0, Delta / M - c)
            print(f"{c:6.4f} | {v:.6f} | {an:.6f} | {sz:.3f} | {gap(A,x,y):.1e}")
        print(f"break-even cost Delta/M = {Delta/M:.4f}")
    step("gl", "cost", s_cost)

    q = np.array([.99] * 5 + [.95] * 3 + [.8] * 3 + [.5, .3]); r = 0.05
    def s_het():
        print("\n== channel-quality variant: M=13, q =", q.tolist(), ", jammed delivery = 0.05*q ==")
        print("k | LP value | uniform-hop guarantee | best-channel-only | k=1 closed form | x on channels (sorted by quality) | gap")
        res = {}
        for k in (1, 2, 3):
            A, S = payoff_matrix(13, k, None, None, q=q, r=r)
            v, x, y, it = solve_matrix_game(A)
            Au = np.min(np.ones(13) / 13 @ A); Ab = np.min(A[0])
            cf = v_hetero_k1(q, r) if k == 1 else (None, None)
            res[k] = (v, x, Au, Ab)
            print(f"{k} | {v:.4f} | {Au:.4f} | {Ab:.4f} | {('%.4f (m=%d)' % cf) if k == 1 else '-'} | {np.round(x, 3).tolist()} | {gap(A, x, y):.1e}")
        return res
    het = step("gl", "het", s_het)

    def s_hedge():
        print("\n== Hedge (multiplicative weights) cross-check on the unequal-channel games: gap of averaged strategies vs proven bound ==")
        print("(the homogeneous game is symmetric, so Hedge started at uniform would be trivially exact; this one is not)")
        for k in (1, 2, 3):
            A, _ = payoff_matrix(13, k, None, None, q=q, r=r)
            for T in (1000, 10000, 100000):
                xb, yb, g, bd = hedge(A, T)
                print(f"k={k} T={T:6d}: gap {g:.2e} (bound {bd:.2e}); value estimate {0.5*(np.max(A@yb)+np.min(xb@A)):.5f} vs LP {het[k][0]:.5f}")
    step("gl", "hedge2", s_hedge)

    def s_fig():
        fig, ax = plt.subplots(1, 3, figsize=(14, 4))
        ks = [1, 2, 3, 4, 6]
        ax[0].plot(ks, [cases[(13, k, .05, .99)][0] for k in ks], "o", label="LP (simplex)")
        ax[0].plot(ks, [v_analytic(13, k, dj, dc) for k in ks], "-", label="analytic p_c-(k/M)(p_c-p_j)")
        ax[0].axhline(ex3["blind"], c="gray", ls=":", label="EXP3 sim, k=1, uniform defender")
        ax[0].set_xlabel("jammed channels k (M=13)"); ax[0].set_ylabel("game value (delivery)"); ax[0].legend(fontsize=7); ax[0].grid(alpha=.3)
        ax[0].set_title("value vs power budget")
        w = 0.4; idx = np.arange(13)
        for k, c in ((1, "#1e8449"), (3, "#2471a3")):
            ax[1].bar(idx + (w / 2 if k == 3 else -w / 2), het[k][1], w, color=c, label=f"optimal x, k={k}")
        ax[1].axhline(1 / 13, c="k", ls="--", lw=1, label="uniform")
        ax[1].set_xticks(idx); ax[1].set_xticklabels([f"{v:.2f}" for v in q], rotation=90, fontsize=7)
        ax[1].set_xlabel("channel clean delivery q_i"); ax[1].set_ylabel("probability"); ax[1].legend(fontsize=7); ax[1].set_title("optimal mix, unequal channels")
        ax[2].bar(["uniform", "best only", "LP optimum"], [het[1][2], het[1][3], het[1][0]], color=["#7f8c8d", "#c0392b", "#1e8449"])
        ax[2].set_ylabel("worst-case delivery (k=1)"); ax[2].set_title("unequal channels, k=1")
        plt.tight_layout(); plt.savefig(os.path.join(FIG, "game_lp.png"), dpi=110); print("saved figures/game_lp.png")
    step("gl", "fig", s_fig)


if __name__ == "__main__":
    main()
