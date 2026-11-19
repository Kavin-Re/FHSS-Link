"""Module 7 - co-evolution of hop strategies (defender) and jamming strategies (jammer), 13 channels.

Model / assumptions
- Defender genome: finite-state automaton with S states. State s emits a channel from a probability vector
  softmax(E[s]); the next state depends on the ACK outcome (ok / fail): T[s, ok]. S=1 is a plain probability vector.
- Jammer genome: FSA with S states; state emits ONE jammed channel (k=1, as sim/game.py) from softmax(Ej[s]); the next
  state depends on the channel the defender just used (the jammer can sense our emission after the fact): Tj[s, c].
  A restricted jammer can only emit on a channel subset W (narrow-band hardware): logits outside W are -inf.
- Payoff per slot (zero-sum): defender delivery 0.05 if channel == jammed channel else 0.99 (as in sim/game.py: loss
  probabilities 0.95 / 0.01). Fitness of an individual = mean expected delivery over a full round-robin against the whole
  opposing population (120 slots per pair, pairs simulated in parallel with numpy); jammer fitness = -delivery.
- GA (both populations, 40 each): 2 elites, tournament selection (size 3), uniform per-state crossover (p=0.7),
  Gaussian mutation on logits (sigma 0.5, per gene prob 0.2), transition mutation (prob 0.03). Initial logits N(0,1),
  i.e. initially biased, non-uniform strategies.
- Variant D ('population = mixed strategy'): genomes are single channels (pure strategies), 500 individuals per side,
  fitness-proportional selection on expected delivery against the OTHER population's channel frequencies (replicator-like),
  mutation = redraw a uniformly random channel with prob 0.02 (jammer: random channel inside W), 600 generations.
  The population frequency vector is the mixed strategy.
- Measures: entropy (bits, max log2 13 = 3.70) of the population-average defender channel usage and the mean
  per-individual entropy; mean realised delivery in the last 20 generations; and for S=1 the exact worst-case
  ('guaranteed') delivery of the best defender, 0.99 - 0.94 max_c p_c, to compare with the game value 0.9177 (module 4).
  For FSA defenders the worst case is estimated by evolving a fresh jammer population against the frozen defender.
- Caveats: finite populations/generations (no convergence proof; co-evolution can cycle), stochastic fitness,
  jammer limited to k=1 and to the FSA family above, results are averages over 5 seeds.
"""
import os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FIG = os.path.join(HERE, "figures")
M = 13
D_JAM, D_CLEAN = 0.05, 0.99
FRAC = 0.25
V_UNI = D_CLEAN - (D_CLEAN - D_JAM) / M


def softmax_cdf(E):
    z = E - E.max(axis=-1, keepdims=True); p = np.exp(z); p /= p.sum(axis=-1, keepdims=True)
    return p, np.cumsum(p, axis=-1)


def rand_pop(P, S, rng, kind, W=None):
    E = rng.normal(size=(P, S, M))
    if W is not None:
        mask = np.full(M, -1e9); mask[list(W)] = 0.0; E = E + mask
    T = rng.integers(0, S, size=(P, S, 2 if kind == "d" else M))
    return [E, T]


def play(dpop, jpop, rng, slots=200):
    """Round robin. Returns (delivery matrix (Pd,Pj), usage (Pd,M) channel counts)."""
    Ed, Td = dpop; Ej, Tj = jpop
    Pd, S, _ = Ed.shape; Pj = Ej.shape[0]; Sj = Ej.shape[1]
    _, cd = softmax_cdf(Ed); _, cj = softmax_cdf(Ej)
    sa = np.zeros((Pd, Pj), int); sb = np.zeros((Pd, Pj), int)
    ia = np.arange(Pd)[:, None]; ib = np.arange(Pj)[None, :]
    tot = np.zeros((Pd, Pj)); use = np.zeros((Pd, M))
    for _ in range(slots):
        c = (cd[ia, sa] < rng.random((Pd, Pj))[..., None]).sum(-1).clip(max=M - 1)
        j = (cj[ib, sb] < rng.random((Pd, Pj))[..., None]).sum(-1).clip(max=M - 1)
        d = np.where(c == j, D_JAM, D_CLEAN); tot += d
        ok = (rng.random((Pd, Pj)) < d).astype(int)
        use += np.bincount((ia * M + c).ravel(), minlength=Pd * M).reshape(Pd, M)
        sa = Td[ia, sa, ok]; sb = Tj[ib, sb, c]
    return tot / slots, use


def next_gen(pop, fit, rng, S, kind, W=None, elites=2):
    E, T = pop; P = len(fit); order = np.argsort(-fit)
    newE = [E[order[i]].copy() for i in range(elites)]; newT = [T[order[i]].copy() for i in range(elites)]
    while len(newE) < P:
        def tour():
            idx = rng.integers(0, P, 3); return idx[np.argmax(fit[idx])]
        a, b = tour(), tour()
        e, t = E[a].copy(), T[a].copy()
        if rng.random() < 0.7:
            m = rng.random(S) < 0.5; e[m] = E[b][m]; t[m] = T[b][m]
        mut = rng.random(e.shape) < 0.2
        e = e + mut * rng.normal(0, 0.5, e.shape)
        if W is not None:
            mask = np.full(M, -1e9); mask[list(W)] = 0.0; e = np.where(mask < -1, -1e9, e)
        tm = rng.random(t.shape) < 0.03
        t = np.where(tm, rng.integers(0, S, t.shape), t)
        newE.append(e); newT.append(t)
    return [np.array(newE), np.array(newT)]


def entropy_bits(p):
    p = p[p > 0]; return float(-(p * np.log2(p)).sum())


def score(A, axis, mode, defender, frac=None):
    frac = FRAC if frac is None else frac
    """Fitness from a payoff matrix (defender rows, jammer cols). mode 'mean' = average delivery; 'cvar' = robust fitness:
    defender -> mean of its worst 25% opponents, jammer -> minus the mean of the 25% defenders that escape it best."""
    X = A if axis == 1 else A.T  # rows = the individual being scored
    k = max(1, int(round(frac * X.shape[1])))
    srt = np.sort(X, axis=1)
    if mode == "mean": v = X.mean(axis=1)
    elif defender: v = srt[:, :k].mean(axis=1)
    else: v = srt[:, -k:].mean(axis=1)
    return v if defender else -v


def cat(pop, extra):
    if extra is None: return pop
    return [np.concatenate([pop[0], extra[0]]), np.concatenate([pop[1], extra[1]])]


def evolve(seed, Sd=1, Sj=1, W=None, gens=150, P=40, slots=120, archive=0, dmode='mean', jmode='mean'):
    """archive>0: hall-of-fame variant, fitness is also measured against `archive` stored past opponents
    (3 elites + 3 random individuals added per generation, oldest dropped)."""
    rng = np.random.default_rng(seed)
    dpop = rand_pop(P, Sd, rng, "d"); jpop = rand_pop(P, Sj, rng, "j", W)
    ad = aj = None
    hist = dict(deliv=[], ent_pop=[], ent_ind=[], pmax=[], upop=[])
    for g in range(gens):
        A, use = play(dpop, cat(jpop, aj), rng, slots)
        fd = score(A, 1, dmode, True)
        if archive:
            Aj, _ = play(cat(dpop, ad), jpop, rng, slots); fj = score(Aj, 0, jmode, False)
            A = A[:, :P]
        else:
            fj = score(A, 0, jmode, False)
        u = use / use.sum(axis=1, keepdims=True)
        hist["deliv"].append(float(A.mean())); hist["ent_pop"].append(entropy_bits(u.mean(axis=0)))
        hist["ent_ind"].append(float(np.mean([entropy_bits(r) for r in u]))); hist["pmax"].append(float(u.max(axis=1).mean())); hist["upop"].append(u.mean(axis=0))
        if archive:
            def pick(pop, f):
                idx = np.concatenate([np.argsort(-f)[:3], rng.integers(0, P, 3)]); return [pop[0][idx], pop[1][idx]]
            nd, nj = pick(dpop, fd), pick(jpop, fj)
            ad = nd if ad is None else [np.concatenate([ad[0], nd[0]])[-archive:], np.concatenate([ad[1], nd[1]])[-archive:]]
            aj = nj if aj is None else [np.concatenate([aj[0], nj[0]])[-archive:], np.concatenate([aj[1], nj[1]])[-archive:]]
        dpop = next_gen(dpop, fd, rng, Sd, "d"); jpop = next_gen(jpop, fj, rng, Sj, "j", W)
    return dpop, jpop, hist, fd


def worst_case_vector(dpop):
    E = dpop[0][:, 0, :]; p, _ = softmax_cdf(E)
    return D_CLEAN - (D_CLEAN - D_JAM) * p.max(axis=1), p


def exploit_test(defender, seed, gens=100, Sj=4, P=40):
    """Evolve a fresh FSA-jammer population against one frozen defender; return delivery achieved by the best jammer."""
    rng = np.random.default_rng(seed)
    dpop = [defender[0][None], defender[1][None]]
    jpop = rand_pop(P, Sj, rng, "j"); best = []
    for g in range(gens):
        A, _ = play(dpop, jpop, rng, 300)
        fj = -A[0]; best.append(float(A[0].min()))
        jpop = next_gen(jpop, fj, rng, Sj, "j")
    return float(np.mean(best[-10:]))


def popgame(seed, W=None, N=500, gens=600, mu=0.02):
    rng = np.random.default_rng(seed)
    Wl = np.arange(M) if W is None else np.array(list(W))
    xd = rng.dirichlet(np.ones(M)); xj = np.zeros(M); xj[Wl] = rng.dirichlet(np.ones(len(Wl)))
    dl, ent, pmax, ups = [], [], [], []
    for g in range(gens):
        fd = D_CLEAN - (D_CLEAN - D_JAM) * xj; fj = 1.0 - D_CLEAN + (D_CLEAN - D_JAM) * xd; fj = fj * (np.arange(M)[:, None] == Wl[None, :]).any(axis=1)
        dl.append(float(xd @ fd)); ent.append(entropy_bits(xd)); pmax.append(float(xd.max())); ups.append(xd.copy())
        pd = xd * fd; pd /= pd.sum(); pj = xj * fj; pj /= pj.sum()
        nd = rng.multinomial(N, pd).astype(float); nj = rng.multinomial(N, pj).astype(float)
        md = rng.binomial(nd.astype(int), mu); nd = nd - md + rng.multinomial(int(md.sum()), np.ones(M) / M)
        mj = rng.binomial(nj.astype(int), mu); back = np.zeros(M); back[Wl] = rng.multinomial(int(mj.sum()), np.ones(len(Wl)) / len(Wl))
        nj = nj - mj + back
        xd = nd / nd.sum(); xj = nj / nj.sum()
    return dict(deliv=dl, ent=ent, pmax=pmax, upop=ups)


def main():
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from _budget import step
    from game_lp import solve_matrix_game
    seeds = [1, 2, 3, 4, 5]
    print(f"game value M=13, k=1 (module 4 / analytic): {V_UNI:.4f}; max entropy {np.log2(M):.3f} bits")
    LAST = 150

    def runA(sd, dmode="mean", gens=300, tag="A"):
        def f():
            dpop, jpop, h, fd = evolve(sd, gens=gens, dmode=dmode)
            wc, p = worst_case_vector(dpop); b = int(np.argmax(wc))
            up = np.array(h['upop'])[-LAST:]
            r = dict(h=h, wc_best=float(wc.max()), wc_med=float(np.median(wc)), tavg_ent=entropy_bits(up.mean(axis=0)))
            print(f"{tag} seed {sd}: deliv(last{LAST})={np.mean(h['deliv'][-LAST:]):.4f} instantaneous pop entropy={np.mean(h['ent_pop'][-LAST:]):.3f} "
                  f"time-averaged entropy={r['tavg_ent']:.3f} individual entropy={np.mean(h['ent_ind'][-LAST:]):.3f} best-defender worst-case={wc.max():.4f} (max p={p[b].max():.3f}) median worst-case={np.median(wc):.4f}")
            return r
        return f
    print("\n== A. genome = probability vector, GA on mean delivery (S=1 both sides, unrestricted jammer), 300 generations ==")
    runsA = [step("ev3", f"A{sd}", runA(sd)) for sd in seeds]
    g = lambda fn: np.mean([fn(r) for r in runsA])
    print(f"A mean over 5 seeds: deliv {g(lambda r: np.mean(r['h']['deliv'][-LAST:])):.4f}  inst. entropy {g(lambda r: np.mean(r['h']['ent_pop'][-LAST:])):.3f}  time-avg entropy {g(lambda r: r['tavg_ent']):.3f}  "
          f"indiv entropy {g(lambda r: np.mean(r['h']['ent_ind'][-LAST:])):.3f}  best worst-case {g(lambda r: r['wc_best']):.4f}  median worst-case {g(lambda r: r['wc_med']):.4f}")
    print(f"A first generation: delivery {g(lambda r: r['h']['deliv'][0]):.4f}, individual entropy {g(lambda r: r['h']['ent_ind'][0]):.3f}")

    print("\n== A2. same, but defender fitness is robust (mean of its worst 25% opponents) instead of the mean, 150 generations ==")
    runsA2 = [step("ev3", f"A2_{sd}", runA(sd, "cvar", 150, "A2")) for sd in seeds[:3]]

    def runB(sd):
        def f():
            dpop, jpop, h, fd = evolve(100 + sd, Sd=4, Sj=4, gens=150)
            b = int(np.argmax(fd)); ex = exploit_test([dpop[0][b], dpop[1][b]], 500 + sd)
            print(f"B seed {sd}: deliv(last20)={np.mean(h['deliv'][-20:]):.4f} ent_pop={np.mean(h['ent_pop'][-20:]):.3f} ent_ind={np.mean(h['ent_ind'][-20:]):.3f} "
                  f"best defender vs fresh evolved jammers = {ex:.4f}")
            return dict(h=h, ex=ex)
        return f
    print("\n== B. 4-state FSA defenders (ACK-driven) vs 4-state FSA jammers (sense our last channel), 150 generations ==")
    resB = [step("ev3", f"B{sd}", runB(sd)) for sd in seeds]
    print(f"B mean: deliv {np.mean([np.mean(r['h']['deliv'][-20:]) for r in resB]):.4f}; fresh-jammer exploit delivery {np.mean([r['ex'] for r in resB]):.4f}")

    def runD(w, sd):
        def f():
            r = popgame(sd, W=range(w) if w < 13 else None)
            r['tavg_ent'] = entropy_bits(np.array(r['upop'])[-300:].mean(axis=0))
            return r
        return f
    print("\n== D. population = mixed strategy (pure-channel genomes, 500 individuals/side, selection+mutation), 600 generations, last 300 averaged, 5 seeds ==")
    print("|W| | LP game value | deliv | inst. entropy | time-avg entropy | max channel share | mass on W | log2(13-|W|)")
    outD = {}
    for w in (13, 9, 5, 3):
        rows = [step("ev3", f"D{w}_{sd}", runD(w, sd)) for sd in seeds]; outD[w] = rows
        A = np.full((M, w), D_CLEAN)
        for jx in range(w): A[jx, jx] = D_JAM
        lp = solve_matrix_game(A)[0]
        mass = np.mean([np.array(r['upop'])[-300:, :w].sum(axis=1).mean() for r in rows])
        print(f"{w:3d} | {lp:.4f} | {np.mean([np.mean(r['deliv'][-300:]) for r in rows]):.4f} | {np.mean([np.mean(r['ent'][-300:]) for r in rows]):.3f} | "
              f"{np.mean([r['tavg_ent'] for r in rows]):.3f} | {np.mean([np.mean(r['pmax'][-300:]) for r in rows]):.3f} | {mass:.3f} | {np.log2(13-w) if w < 13 else float('nan'):.3f}")

    def runC(w, sd):
        def f():
            W = range(w)
            dpop, jpop, h, fd = evolve(300 + sd, W=W, gens=150)
            wc, p = worst_case_vector(dpop)
            return (np.mean(h['deliv'][-20:]), np.mean(h['ent_pop'][-20:]), float(p[:, :w].sum(axis=1).mean()), float(wc.max()))
        return f
    print("\n== C. vector GA of A with a restricted jammer (can only emit on |W| channels), 150 generations, 3 seeds ==")
    print("|W| | deliv(last20) | inst. entropy | defender mass on W | best worst-case")
    for w in (13, 5, 3):
        rows = [step("ev3", f"C{w}_{sd}", runC(w, sd)) for sd in seeds[:3]]
        r = np.mean(rows, axis=0); print(f"{w:3d} | {r[0]:.4f} | {r[1]:.3f} | {r[2]:.3f} | {r[3]:.4f}")

    def s_fig():
        fig, ax = plt.subplots(1, 3, figsize=(14, 4))
        for r in runsA: ax[0].plot(r["h"]["deliv"], c="#c0392b", alpha=.4)
        for r in outD[13]: ax[0].plot(np.linspace(0, 300, len(r["deliv"])), r["deliv"], c="#1e8449", alpha=.4)
        ax[0].plot([], [], c="#c0392b", label="A: vector GA (5 seeds)"); ax[0].plot([], [], c="#1e8449", label="D: population-as-strategy")
        ax[0].axhline(V_UNI, c="k", ls="--", label="game value 0.9177"); ax[0].set_xlabel("generation (D rescaled to 300)"); ax[0].set_ylabel("expected / mean delivery")
        ax[0].legend(fontsize=7); ax[0].grid(alpha=.3); ax[0].set_title("unrestricted jammer")
        for r in runsA: ax[1].plot(r["h"]["ent_pop"], c="#c0392b", alpha=.4)
        for r in outD[13]: ax[1].plot(np.linspace(0, 300, len(r["ent"])), r["ent"], c="#1e8449", alpha=.4)
        ax[1].axhline(np.log2(13), c="k", ls="--"); ax[1].set_xlabel("generation"); ax[1].set_ylabel("defender population entropy [bits]"); ax[1].grid(alpha=.3); ax[1].set_title("entropy (max 3.70)")
        cols = {13: "#c0392b", 9: "#e67e22", 5: "#2471a3", 3: "#1e8449"}
        for w, rows in outD.items(): ax[2].plot(np.mean([r["deliv"] for r in rows], axis=0), c=cols[w], label=f"|W|={w}")
        ax[2].set_xlabel("generation"); ax[2].set_ylabel("expected delivery (variant D)"); ax[2].legend(fontsize=7); ax[2].grid(alpha=.3); ax[2].set_title("restricted jammer band |W|")
        plt.tight_layout(); plt.savefig(os.path.join(FIG, "evolve.png"), dpi=110); print("saved figures/evolve.png")
    step("ev3", "fig", s_fig)


if __name__ == "__main__":
    main()
