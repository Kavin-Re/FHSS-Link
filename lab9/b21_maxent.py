"""B21 Maximum-entropy hopping under constraints (simulation). M=40 channels, no-go set, spectral-mask rule |next-cur| >= D (no near-adjacent
consecutive hops), optional regulatory rule: stationary occupancy of every allowed channel equal (uniform).
Compare entropy rates (bits/hop): (a) upper bound log2(#allowed); (b) 'naive redraw' (uniform i.i.d. draw, redraw until legal);
(c) Parry max-entropy Markov chain (Perron eigenvector); (d) max-entropy chain with UNIFORM occupancy (Sinkhorn balancing of the symmetric adjacency).
Adversary: learns the transition matrix from n observed hops, predicts next hop by argmax. Measured vs closed-form sum_i pi_i max_j P_ij."""
import numpy as np
from _common import *

M, D = 40, 3
NOGO = [5, 6, 7, 20, 33]        # e.g. incumbent services
def adjacency(m=M, d=D, nogo=NOGO):
    ok = np.array([c not in nogo for c in range(m)]); A = np.zeros((m, m))
    for i in range(m):
        for j in range(m):
            if ok[i] and ok[j] and abs(i - j) >= d: A[i, j] = 1
    return A, ok

def stationary(P):
    w, v = np.linalg.eig(P.T); k = np.argmin(abs(w - 1)); p = np.real(v[:, k]); p = np.abs(p); return p / p.sum()
def ent_rate(P, pi=None):
    pi = stationary(P) if pi is None else pi; L = np.where(P > 0, np.log2(np.where(P > 0, P, 1)), 0); return float(-(pi[:, None] * P * L).sum())
def chain_naive(A):
    """uniform draw over allowed channels, redraw until it satisfies |next-cur|>=D: P_ij proportional to A_ij; pure rejection from the uniform-on-allowed proposal."""
    ok = A.sum(1) > 0; P = A / np.maximum(A.sum(1, keepdims=True), 1); return P
def chain_parry(A):
    w, v = np.linalg.eigh(A); lam = w[-1]; x = np.abs(v[:, -1]); P = A * x[None, :] / (lam * np.maximum(x[:, None], 1e-300)); P[x < 1e-12] = 0
    return P, lam
def chain_uniform_occ(A, it=3000):
    S = A.copy(); idx = A.sum(1) > 0; S = S[np.ix_(idx, idx)]; d = np.ones(len(S))
    for _ in range(it): d = 1 / (S @ d)
    B = (S * d[None, :]) * d[:, None]
    for _ in range(300): B = B / B.sum(1, keepdims=True); B = B / B.sum(0, keepdims=True)
    P = np.zeros_like(A); P[np.ix_(idx, idx)] = B / B.sum(1, keepdims=True); return P
def simulate(P, n, rng):
    cum = np.cumsum(P, 1); s = np.empty(n, int); live = np.where(P.sum(1) > 0)[0]; s[0] = rng.choice(live)
    u = rng.random(n)
    for t in range(1, n): s[t] = min(np.searchsorted(cum[s[t - 1]], u[t]), len(P) - 1)
    return s
def attacker_acc(P, rng, n_obs=20000, n_test=20000):
    s = simulate(P, n_obs + n_test, rng); cnt = np.zeros_like(P)
    np.add.at(cnt, (s[:n_obs - 1], s[1:n_obs]), 1); guess = cnt.argmax(1)
    return float((guess[s[n_obs:-1]] == s[n_obs + 1:]).mean())

def count_growth(m=7, d=2, L=12):
    """brute force: number of legal length-L sequences vs lambda^L (independent check of Perron eigenvalue)."""
    A, _ = adjacency(m, d, []); v = np.ones(m); counts = []
    for _ in range(L): v = A @ v; counts.append(v.sum())
    return counts[-1] / counts[-2]

def run():
    A, ok = adjacency(); P_n = chain_naive(A); P_p, lam = chain_parry(A); P_u = chain_uniform_occ(A)
    n_allowed = int(ok.sum()); rows = {}
    for name, P in (("naive redraw", P_n), ("max-entropy (Parry)", P_p), ("max-entropy, uniform occupancy", P_u)):
        pi = stationary(P); th = float((pi * P.max(1)).sum())
        accs = [attacker_acc(P, np.random.default_rng(s)) for s in range(NSEEDS)]
        rows[name] = dict(H=ent_rate(P), occ_ratio=float(pi[ok].max() / pi[ok].min()), pred_theory=th, pred_meas=mean_ci(accs), rowsum_err=float(abs(P.sum(1)[ok] - 1).max()))
    sweep = {}
    for dd in range(1, 15):
        Ad, okd = adjacency(M, dd); Pn = chain_naive(Ad); Pp, lm = chain_parry(Ad); Pu = chain_uniform_occ(Ad); pp = stationary(Pp)
        sweep[str(dd)] = dict(naive=ent_rate(Pn), parry=ent_rate(Pp), uniform=ent_rate(Pu), log2lam=float(np.log2(lm)), occ_ratio=float(pp[okd].max() / pp[okd].min()))
    out = dict(sweep=sweep, M=M, D=D, nogo=NOGO, n_allowed=n_allowed, bound=float(np.log2(n_allowed)), log2_lambda=float(np.log2(lam)), rows=rows,
               brute_growth=count_growth(), eig_growth=float(np.linalg.eigvalsh(adjacency(7, 2, [])[0])[-1]), nseeds=NSEEDS,
               occ={n: stationary(P).tolist() for n, P in (("naive redraw", P_n), ("max-entropy (Parry)", P_p), ("max-entropy, uniform occupancy", P_u))})
    save_json("b21_maxent.json", out); return out

def plot(o):
    fig, ax = plt.subplots(1, 3, figsize=(13.5, 3.4)); cs = [C["verm"], C["blue"], C["green"]]
    for (n, v), c in zip(o["occ"].items(), cs): ax[0].plot(v, color=c, marker=".", label=n)
    ax[0].set_xlabel("channel"); ax[0].set_ylabel("stationary occupancy"); ax[0].legend(); ax[0].set_title("Channel occupancy (no-go gaps at 5-7, 20, 33)")
    names = list(o["rows"]); H = [o["rows"][n]["H"] for n in names]; ac = [o["rows"][n]["pred_meas"] for n in names]
    x = np.arange(3); ax[1].bar(x, H, color=cs); ax[1].axhline(o["bound"], color=C["grey"], ls=":"); ax[1].set_xticks(x); ax[1].set_xticklabels(["naive\nredraw", "max-ent\n(Parry)", "max-ent\nuniform occ."])
    for xi, h, a in zip(x, H, ac): ax[1].text(xi, h + 0.02, f"{h:.3f} b\nattacker {a[0]:.3f}", ha="center", fontsize=8)
    ax[1].set_ylim(min(H) - 0.3, o["bound"] + 0.3); ax[1].set_ylabel("entropy rate (bits/hop); dotted = log2(#allowed)"); ax[1].set_title("Constrained hopping entropy")
    ds = sorted(map(int, o["sweep"])); sw = lambda k: [o["sweep"][str(d)][k] for d in ds]
    for k, c, l in (("naive", C["verm"], "naive redraw"), ("parry", C["blue"], "max-entropy (Parry)"), ("uniform", C["green"], "max-ent, uniform occupancy")): ax[2].plot(ds, sw(k), color=c, marker="o", label=l)
    ax[2].set_xlabel("minimum hop separation D (channels)"); ax[2].set_ylabel("entropy rate (bits/hop)"); ax[2].legend(); ax[2].set_title("Cost of the spectral-mask rule")
    save_fig(fig, "b21_maxent.png")

if __name__ == "__main__":
    o = run(); plot(o); r = o["rows"]
    sw = o["sweep"]["10"]; key("B21", f"D=10: naive {sw['naive']:.3f}, Parry {sw['parry']:.3f} (+{sw['parry']-sw['naive']:.3f}), uniform-occupancy {sw['uniform']:.3f}, occupancy ratio Parry {sw['occ_ratio']:.2f}; at D={o['D']}: {o['n_allowed']} allowed channels, bound {o['bound']:.3f} b/hop; naive redraw {r['naive redraw']['H']:.3f} (attacker {fmt(r['naive redraw']['pred_meas'])}), Parry {r['max-entropy (Parry)']['H']:.3f} (attacker {fmt(r['max-entropy (Parry)']['pred_meas'])}, occupancy max/min {r['max-entropy (Parry)']['occ_ratio']:.2f}), uniform-occupancy max-ent {r['max-entropy, uniform occupancy']['H']:.3f} (occ ratio {r['max-entropy, uniform occupancy']['occ_ratio']:.2f})")
