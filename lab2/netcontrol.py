"""Module 1 - networked control over the lossy hopping link.

Model / assumptions
- Plant: discrete-time unstable LTI x+ = A x + B u + w (w Gaussian process noise). Main plant: inverted pendulum
  linearised about upright (g=9.81, l=0.5 m, m=1 kg, exact zero-order-hold discretisation, dt=0.05 s), plus scalar
  unstable plants x+ = a x + u + w for the textbook bound.
- Sensor -> controller is ideal (co-located); only the controller -> actuator command packet crosses the lossy link.
  One command packet per control period. The packet is either delivered (d=1) or lost (d=0).
- Gains: LQR from a numpy Riccati iteration (Q=diag(10,1), R=1) for the pendulum; deadbeat for the scalar plant.
- Loss-handling policies at the actuator:
    zero : u=0 on loss
    hold : u = last received command on loss
    pred : model-based predictor. The packet carries the controller state x_k; the actuator keeps a nominal model
           xh+ = (A-BK) xh and applies u=-K xh while no packet arrives (packetised-predictive-control style).
- Loss processes: (a) i.i.d. with delivery probability p. (b) Gilbert-Elliott derived from hopping against a jammer:
  the defender stays D packets per hop (geometric dwell, mean D), a hop lands on a jammed channel with probability
  q=k/M, a jammed channel delivers with prob dB=0.05, a clean one dG=0.99. State persists within a dwell, so
  P(G->B)=q/D, P(B->G)=(1-q)/D. D=1 reduces exactly to i.i.d. loss with p=(1-q)dG+q dB.
- Theory: all cases are Markov jump linear systems; mean-square stability (MSS) holds iff the spectral radius of
  (P^T kron I) blockdiag(A_i kron A_i) is < 1 (Costa/Fragoso). For the scalar plant with u=0 on loss and deadbeat
  gain this gives (1-p)a^2 < 1, i.e. p_c = 1 - 1/a^2.
- Empirical stability: slope of log(ensemble mean |x|^2) over the late window; ensemble means of heavy-tailed
  quantities under-sample rare large excursions, so the empirical threshold is biased slightly low (optimistic).
"""
import os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "figures")


def c2d(Ac, Bc, dt, terms=40):
    n = Ac.shape[0]
    Ad = np.eye(n); Bd = np.zeros_like(Bc, dtype=float)
    term = np.eye(n)
    for k in range(terms):
        Bd = Bd + term @ Bc * dt ** (k + 1) / _fact(k + 1)
        term = term @ Ac
        Ad = Ad + term * dt ** (k + 1) / _fact(k + 1)
    return Ad, Bd


def _fact(n):
    r = 1.0
    for i in range(2, n + 1): r *= i
    return r


def dlqr(A, B, Q, R, iters=100000, tol=1e-13):
    P = Q.copy()
    for _ in range(iters):
        K = np.linalg.solve(R + B.T @ P @ B, B.T @ P @ A)
        Pn = Q + A.T @ P @ (A - B @ K)
        if np.max(np.abs(Pn - P)) < tol: P = Pn; break
        P = Pn
    K = np.linalg.solve(R + B.T @ P @ B, B.T @ P @ A)
    return K, P


def pendulum(dt=0.05, g=9.81, l=0.5, m=1.0):
    Ac = np.array([[0, 1.0], [g / l, 0]]); Bc = np.array([[0], [1.0 / (m * l * l)]])
    return c2d(Ac, Bc, dt)


def aug_mats(A, B, K, policy):
    """(A_success, A_fail) of the augmented state; first n coordinates are the plant state."""
    n, m = B.shape; Acl = A - B @ K
    if policy == "zero":
        return Acl, A
    if policy == "hold":
        As = np.block([[Acl, np.zeros((n, m))], [-K, np.zeros((m, m))]])
        Af = np.block([[A, B], [np.zeros((m, n)), np.eye(m)]])
        return As, Af
    if policy == "pred":
        Z = np.zeros((n, n))
        As = np.block([[Acl, Z], [Acl, Z]])
        Af = np.block([[A, -B @ K], [Z, Acl]])
        return As, Af
    raise ValueError(policy)


def mss_rho(mats, T):
    m = len(mats); d = mats[0].shape[0]; dd = d * d
    blk = np.zeros((m * dd, m * dd))
    for i, M in enumerate(mats):
        blk[i * dd:(i + 1) * dd, i * dd:(i + 1) * dd] = np.kron(M, M)
    return float(max(abs(np.linalg.eigvals(np.kron(T.T, np.eye(dd)) @ blk))))


def ge_chain(q, D, dG=0.99, dB=0.05):
    P = np.array([[1 - q / D, q / D], [(1 - q) / D, 1 - (1 - q) / D]])
    mean = (1 - q) * dG + q * dB
    return P, mean


def rho_iid(A, B, K, policy, p):
    As, Af = aug_mats(A, B, K, policy)
    return mss_rho([As, Af], np.array([[p, 1 - p], [p, 1 - p]]))


def rho_ge(A, B, K, policy, q, D, dG=0.99, dB=0.05):
    As, Af = aug_mats(A, B, K, policy)
    P, _ = ge_chain(q, D, dG, dB)
    dl = [dG, dB]
    T = np.zeros((4, 4))
    for i in range(4):
        s = i // 2
        for j in range(4):
            s2, d2 = j // 2, (j % 2 == 0)
            T[i, j] = P[s, s2] * (dl[s2] if d2 else 1 - dl[s2])
    return mss_rho([As, Af, As, Af], T)


def bisect_pc(fn, lo=0.0, hi=1.0, it=50):
    """fn(p) = rho; rho decreases with p; returns p with rho=1 (None if never unstable / always unstable)."""
    if fn(hi) >= 1: return None
    if fn(lo) < 1: return 0.0
    for _ in range(it):
        mid = 0.5 * (lo + hi)
        if fn(mid) >= 1: lo = mid
        else: hi = mid
    return 0.5 * (lo + hi)


# ---------------- loss processes ----------------
def deliv_iid(N, T, p, rng):
    return rng.random((N, T)) < p


def deliv_ge(N, T, q, D, rng, dG=0.99, dB=0.05):
    P, _ = ge_chain(q, D, dG, dB)
    s = (rng.random(N) < q).astype(int)  # stationary: P(B)=q
    out = np.zeros((N, T), dtype=bool)
    for t in range(T):
        dl = np.where(s == 1, dB, dG)
        out[:, t] = rng.random(N) < dl
        pb = np.where(s == 1, 1 - P[1, 0], P[0, 1])
        s = (rng.random(N) < pb).astype(int)
    return out


# ---------------- simulation ----------------
def simulate(policy, A, B, K, deliv, wstd, rng, x0=None, lim=0.35):
    N, T = deliv.shape; n = A.shape[0]; m = B.shape[1]
    x = np.tile(np.zeros(n) if x0 is None else x0, (N, 1)).astype(float)
    uprev = np.zeros((N, m)); xh = x.copy(); Acl = A - B @ K
    ms = np.zeros(T); th2 = np.zeros(T); fell = np.zeros(N, dtype=bool)
    with np.errstate(all="ignore"):
        for k in range(T):
            d = deliv[:, k][:, None]
            if policy == "zero":
                u = np.where(d, -x @ K.T, 0.0)
            elif policy == "hold":
                u = np.where(d, -x @ K.T, uprev); uprev = u
            else:
                xh = np.where(d, x, xh); u = -xh @ K.T; xh = xh @ Acl.T
            x = x @ A.T + u @ B.T + rng.normal(size=(N, n)) * wstd
            x = np.clip(x, -1e100, 1e100)
            ms[k] = np.mean(np.sum(x * x, axis=1)); th2[k] = np.mean(x[:, 0] ** 2)
            fell |= np.abs(x[:, 0]) > lim
    return ms, th2, float(fell.mean())


def fail_critical(A, B, K, policy, wstd, gen, grid, lim, N=3000, T=200, thr=0.01, seed=0):
    """Practical (sample-path) threshold: first level (grid ordered benign -> harsh) where the fraction of
    trajectories whose |x1| ever exceeds `lim` within T steps is > thr; linear interpolation. Returns (level, pfail list)."""
    pf = []
    for lv in grid:
        rng = np.random.default_rng(seed)
        x0 = np.array([0.05] + [0.0] * (A.shape[0] - 1))
        pf.append(simulate(policy, A, B, K, gen(lv, N, T, rng), wstd, rng, x0=x0, lim=lim)[2])
    pf = np.array(pf)
    for i in range(len(grid)):
        if pf[i] > thr:
            if i == 0: return grid[0], pf
            f = (thr - pf[i - 1]) / (pf[i] - pf[i - 1])
            return grid[i - 1] + f * (grid[i] - grid[i - 1]), pf
    return None, pf


def stationary_ms(A, B, K, policy, p, wstd):
    """Analytic stationary E[x1^2] for i.i.d. loss (second-moment Lyapunov equation of the jump system)."""
    As, Af = aug_mats(A, B, K, policy); d = As.shape[0]; n = A.shape[0]
    W = np.zeros((d, d)); W[:n, :n] = np.diag(np.asarray(wstd) ** 2)
    L = p * np.kron(As, As) + (1 - p) * np.kron(Af, Af)
    S = np.linalg.solve(np.eye(d * d) - L, W.reshape(-1)).reshape(d, d)
    return float(S[0, 0])


def rms_deg(th2, T0):
    return float(np.sqrt(np.mean(th2[T0:])))


def main():
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from _budget import step
    pols = ["zero", "hold", "pred"]
    A, B = pendulum(0.05)
    K, P = dlqr(A, B, np.diag([10.0, 1.0]), np.array([[1.0]]))
    wstd = np.array([0.002, 0.02])
    grid = np.round(np.arange(1.0, 0.0, -0.02), 3)
    N, T = 3000, 300

    def s_head():
        ev = np.linalg.eigvals(A)
        print("== pendulum dt=0.05 ==")
        print("open-loop discrete eigenvalues", np.round(ev, 4), " unstable |a| =", round(float(max(abs(ev))), 4))
        print("LQR K =", np.round(K, 4), " closed-loop |eig| =", np.round(abs(np.linalg.eigvals(A - B @ K)), 4))
        a_un = float(max(abs(ev)))
        print("scalar-style bound with a=|unstable pole|: p_c = 1-1/a^2 =", round(1 - 1 / a_un ** 2, 4))
        return a_un
    a_un = step("nc2", "head", s_head)

    def s_scalar():
        print("\n== scalar plant x+=a x+u+w, deadbeat K=a, i.i.d. loss ==")
        print("a    bound 1-1/a^2 | theory p_c zero  hold  pred | sample-path p (1% of runs exceed |x|>2 in 200 steps, zero)")
        g2 = np.round(np.arange(1.0, 0.0, -0.02), 3)
        for a in (1.2, 1.5, 2.0):
            As_, Bs_ = np.array([[a]]), np.array([[1.0]]); Ks_ = np.array([[a]])
            th = {pl: bisect_pc(lambda p, pl=pl: rho_iid(As_, Bs_, Ks_, pl, p)) for pl in pols}
            emp, _ = fail_critical(As_, Bs_, Ks_, "zero", np.array([0.1]), lambda lv, N, T, r: deliv_iid(N, T, lv, r), g2, 2.0, N=4000, T=200)
            print(f"{a:3.1f}  {1-1/a**2:8.4f}      | {th['zero']:.4f}   {th['hold']:.4f}  {th['pred']:.4f} | {emp:.3f}")
    step("nc2", "scalar", s_scalar)

    def s_pc():
        print("\n== pendulum (LQR), i.i.d. loss: MSS threshold p_c ==")
        pcs = {pl: bisect_pc(lambda p, pl=pl: rho_iid(A, B, K, pl, p)) for pl in pols}
        for pl in pols:
            e, _ = fail_critical(A, B, K, pl, wstd, lambda lv, N, T, r: deliv_iid(N, T, lv, r), grid, 0.35, N=3000, T=200)
            print(f"{pl:5s} MSS theory p_c = {pcs[pl]:.4f}   sample-path p (1% of runs exceed 0.35 rad within 200 steps = 10 s) = {e:.3f}")
        print("validation of the second-moment theory where Monte Carlo is reliable (stationary E[theta^2], p high):")
        for pl in pols:
            for p in (0.95, 0.85):
                rng = np.random.default_rng(5)
                _, th2, _f = simulate(pl, A, B, K, deliv_iid(6000, 300, p, rng), wstd, rng)
                print(f"  {pl:5s} p={p}: analytic {stationary_ms(A, B, K, pl, p, wstd):.4e}   Monte Carlo {np.mean(th2[150:]):.4e}")
        return pcs
    pcs = step("nc2", "pc", s_pc)

    ps = np.round(np.concatenate([np.arange(0.3, 0.9, 0.05), np.arange(0.9, 1.0001, 0.02)]), 3)

    def s_rms():
        rms = {pl: [] for pl in pols}
        for pl in pols:
            for p in ps:
                rng = np.random.default_rng(1)
                _, th2, _f = simulate(pl, A, B, K, deliv_iid(N, T, p, rng), wstd, rng)
                rms[pl].append(rms_deg(th2, 150))
        print("\n== pendulum RMS angle (rad), i.i.d. loss (huge values = diverging) ==")
        print("p      " + "  ".join(f"{pl:>10s}" for pl in pols) + "   theory rho(zero/hold/pred)")
        for i, p in enumerate(ps):
            rh = [rho_iid(A, B, K, pl, p) for pl in pols]
            print(f"{p:5.2f}  " + "  ".join(f"{rms[pl][i]:10.4g}" for pl in pols) + "   " + "/".join(f"{r:.3f}" for r in rh))
        base = {pl: rms[pl][-1] for pl in pols}
        print("lossless RMS (p=1):", {k: round(v, 5) for k, v in base.items()})
        p2 = {}
        for pl in pols:
            r = np.array(rms[pl]); idx = None
            for i in range(len(ps) - 1, -1, -1):
                if r[i] > 2 * base[pl]: idx = i; break
            p2[pl] = None if idx is None else float(ps[idx])
        print("highest grid p at which RMS exceeds 2x lossless RMS (i.i.d.):", p2)
        return rms, p2
    rms, p2 = step("nc2", "rms", s_rms)

    Ds = [1, 2, 5]

    def s_get():
        print("\n== burstiness (Gilbert-Elliott from hopping; dG=0.99 dB=0.05; M=13: k=1 -> q=0.077, k=3 -> q=0.23) ==")
        print("theory: MSS spectral radius rho at q=1/13 (mean delivery 0.93) vs mean dwell D (rho<1 = mean-square stable)")
        Dl = [1, 1.5, 2, 3, 5, 10, 20]
        print("D      " + "  ".join(f"{D:>6}" for D in Dl))
        for pl in pols:
            print(f"{pl:5s}  " + "  ".join(f"{rho_ge(A, B, K, pl, 1 / 13, D):6.3f}" for D in Dl))
        pc_ge = {}
        print("theory: MSS threshold on MEAN delivery rate (bisect over q; n/a = unstable for every q>0)")
        for pl in pols:
            row = []
            for D in (1, 1.5, 2, 3):
                def fq(mean, pl=pl, D=D):
                    q = (0.99 - mean) / (0.99 - 0.05)
                    return rho_ge(A, B, K, pl, min(max(q, 1e-4), 1), D)
                pc = bisect_pc(fq, 0.05, 0.99); pc_ge[(pl, D)] = pc; row.append(pc)
            print(f"{pl:5s} " + "  ".join(f"D={D}: {('%.3f' % v) if v is not None else 'n/a'}" for D, v in zip((1, 1.5, 2, 3), row)))
        return pc_ge
    pc_ge = step("nc2", "ge_theory2", s_get)

    def s_ge_rms():
        means = [0.95, 0.9, 0.85, 0.8, 0.7]
        print("empirical RMS angle (rad) at fixed mean delivery (huge = diverging):")
        print("mean  " + "  ".join(f"{pl}/D={D}".rjust(11) for pl in pols for D in Ds))
        for mean in means:
            q = (0.99 - mean) / 0.94; vals = []
            for pl in pols:
                for D in Ds:
                    rng = np.random.default_rng(2)
                    _, th2, _f = simulate(pl, A, B, K, deliv_ge(2000, 300, q, D, rng), wstd, rng)
                    vals.append(rms_deg(th2, 150))
            print(f"{mean:4.2f}  " + "  ".join(f"{v:11.4g}" for v in vals))
    step("nc2", "ge_rms2", s_ge_rms)

    def s_pfall():
        print("\nfraction of runs that exceed 0.35 rad within 200 steps (10 s), N=2000:")
        print("q (k/M)  mean   D   " + "  ".join(f"{pl:>6}" for pl in pols))
        for q in (1 / 13, 3 / 13):
            for D in (1, 2, 5, 20):
                row = []
                for pl in pols:
                    rng = np.random.default_rng(4)
                    row.append(simulate(pl, A, B, K, deliv_ge(2000, 200, q, D, rng), wstd, rng, x0=np.array([0.05, 0.0]))[2])
                print(f"{q:6.3f}  {ge_chain(q, D)[1]:.3f}  {D:3d}  " + "  ".join(f"{v:6.3f}" for v in row))
    step("nc2", "pfall", s_pfall)

    def s_ge_emp():
        qgrid = np.round(np.arange(0.0, 1.0001, 0.08), 3)
        out = {}
        for pl in ("zero", "pred"):
            for D in (1, 5):
                lv, _ = fail_critical(A, B, K, pl, wstd, lambda q, N, T, r, D=D: deliv_ge(N, T, q, D, r), qgrid, 0.35, N=1500, T=200)
                out[(pl, D)] = None if lv is None else 0.99 - 0.94 * lv
                print(f"sample-path critical MEAN delivery (1% fall in 10 s, q grid step 0.08) {pl} D={D}: " + ("never" if lv is None else f"{out[(pl, D)]:.3f}"))
        return out
    step("nc2", "ge_emp2", s_ge_emp)

    def s_fig():
        fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
        col = {"zero": "#c0392b", "hold": "#2471a3", "pred": "#1e8449"}
        for pl in pols:
            ax[0].semilogy(ps, np.clip(rms[pl], 1e-4, 1e3), "o-", color=col[pl], label=pl, ms=3)
            ax[0].axvline(pcs[pl], color=col[pl], ls=":", lw=1)
        ax[0].set_xlabel("delivery probability p (i.i.d.)"); ax[0].set_ylabel("RMS pendulum angle [rad] (clipped at 1e3)")
        ax[0].set_title("RMS error vs delivery, dotted = MSS threshold"); ax[0].legend(); ax[0].grid(alpha=.3)
        mm = np.linspace(0.6, 0.99, 12)
        for D, ls in zip(Ds, ["-", "--", ":"]):
            for pl in ("pred", "zero"):
                vals = []
                for mean in mm:
                    q = (0.99 - mean) / 0.94; rng = np.random.default_rng(3)
                    _, th2, _f = simulate(pl, A, B, K, deliv_ge(1500, 300, q, D, rng), wstd, rng); vals.append(rms_deg(th2, 150))
                ax[1].semilogy(mm, np.clip(vals, 1e-4, 1e3), ls, color=col[pl], label=f"{pl}, D={D}")
        ax[1].set_xlabel("MEAN delivery rate"); ax[1].set_title("burstiness (Gilbert-Elliott) at equal mean delivery")
        ax[1].legend(fontsize=7); ax[1].grid(alpha=.3)
        plt.tight_layout(); plt.savefig(os.path.join(FIG, "netcontrol_rms.png"), dpi=110)
        print("\nsaved figures/netcontrol_rms.png")
        print("\n== summary of thresholds ==")
        print("pendulum a=%.3f: MSS floor (i.i.d.) zero %.3f / hold %.3f / pred %.3f" % (a_un, pcs['zero'], pcs['hold'], pcs['pred']))
        print("bursty MSS floor on mean delivery, D=2: zero %s / hold %s / pred %s" % (pc_ge[('zero', 2)], pc_ge[('hold', 2)], pc_ge[('pred', 2)]))
        print("2x-RMS point (i.i.d.):", p2)
    step("nc2", "fig", s_fig)


if __name__ == "__main__":
    main()
