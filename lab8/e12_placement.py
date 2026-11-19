"""E12 (RED_TEAM idea 12): worst-case jammer placement against a patrol path, and the defender's relay placement (Stackelberg).
Model: _common.py/_spatial.py (log-distance path loss n=3, jammer 0 dBm per jammed channel, k=3 of 13 channels, jammer must stay >= STANDOFF m
from every path point). Follower (jammer) picks position J to minimise path-mean delivery; leader (defender) picks a second transmitter ("relay",
selection diversity) position R to maximise that minimum. Grid search, then continuous refinement to check the grid is adequate.
Validation against model mismatch: the optimisation is deterministic (mean path loss); the check re-evaluates the chosen J by Monte Carlo WITH
Rayleigh fading + 4 dB log-normal shadowing, which the optimiser never saw.
Defensive lesson: where the relay goes and how much margin to leave. Simulation only."""
import sys
import numpy as np
from _spatial import *

PJ_DBM, STANDOFF = 0.0, 10.0
G_R = 12

def allowed_mask(inst, standoff=STANDOFF):
    return dist(inst["cand"], inst["path"]).min(1) >= standoff

def jam_interference(inst, pj=PJ_DBM, n=None):
    return rx_mw(pj, dist(inst["cand"], inst["path"]), n)          # (G, m)

def delivery_grid(inst, txs, pj=PJ_DBM, n=None):
    """mean-path delivery for every jammer candidate position, given transmitters txs (T,2)"""
    S = tx_signal_mw(txs, inst["path"], n)                          # (T, m)
    I = jam_interference(inst, pj, n)                               # (G, m)
    return delivery_points(S, I).mean(1)                            # (G,)

def worst_spot(inst, txs, **kw):
    dg = delivery_grid(inst, txs, **kw); mask = allowed_mask(inst)
    dm = np.where(mask, dg, np.inf); i = int(np.argmin(dm))
    return i, float(dm[i]), dg

def refine_jammer(inst, txs, j0, pj=PJ_DBM, iters=60, seed=0):
    """continuous random-direction hill climb from a grid cell; returns best mean delivery found (respecting standoff)"""
    rng = np.random.default_rng(seed); S = tx_signal_mw(txs, inst["path"])
    def f(p):
        if dist(p[None], inst["path"]).min() < STANDOFF or not (0 <= p[0] <= ARENA and 0 <= p[1] <= ARENA): return np.inf
        return float(delivery_points(S, rx_mw(pj, dist(p[None], inst["path"]))[0]).mean())
    p = inst["cand"][j0].copy(); best = f(p); step = 3.0
    for _ in range(iters):
        for _ in range(8):
            q = p + rng.normal(0, step, 2); v = f(q)
            if v < best: p, best = q, v
        step *= 0.9
    return best

def relay_candidates():
    return grid_points(G_R, 5.0, ARENA - 5.0)

def stackelberg(inst, pj=PJ_DBM):
    """returns (best relay index, V(R) over relay candidates, V0 without relay)"""
    Rc = relay_candidates(); path = inst["path"]; mask = allowed_mask(inst)
    I = jam_interference(inst, pj)[mask]                             # (G', m)
    SB = tx_signal_mw(inst["base"][None], path)
    V = np.empty(len(Rc))
    for r in range(len(Rc)):
        S = np.vstack([SB, tx_signal_mw(Rc[r][None], path)])
        V[r] = delivery_points(S, I).mean(1).min()
    V0 = delivery_points(SB, I).mean(1).min()
    return int(np.argmax(V)), V, float(V0), Rc

def mc_path_delivery(inst, txs, jpos, rng, pj=PJ_DBM, nslot=160, sh_db=4.0, n=None):
    """Monte Carlo delivery with Rayleigh fading + log-normal shadowing, jammer at jpos; mean over path points"""
    path = inst["path"]; m = len(path); T = len(txs)
    sig = tx_signal_mw(txs, path, n) * 10 ** (rng.normal(0, sh_db, (T, m)) / 10)             # static shadow per link/point
    jam = rx_mw(pj, dist(np.atleast_2d(jpos), path), n)[0] * 10 ** (rng.normal(0, sh_db, m) / 10)
    fs = rng.exponential(1.0, (nslot, T, m)); fj = rng.exponential(1.0, (nslot, m))
    jammed = rng.random((nslot, 1)) < Q_JAM
    ok_t = rng.random((nslot, T, m)) < prr_from_mw(sig[None] * fs, np.where(jammed, jam[None] * fj, 0.0)[:, None, :])
    return float(ok_t.any(1).mean())

def run_seed(seed, check_mc=True):
    inst = random_instance(seed); path, base = inst["path"], inst["base"]
    j0, v0, dg = worst_spot(inst, base[None])
    ref = min(refine_jammer(inst, base[None], j0, seed=seed), v0)       # jammer's continuous polish of the grid optimum
    r_best, V, V0, Rc = stackelberg(inst)
    rng = np.random.default_rng(1000 + seed)
    rand_r = rng.integers(0, len(Rc), 10)
    V_rand = float(np.mean(V[rand_r]))
    centroid = path.mean(0); r_cent = int(np.argmin(dist(Rc, centroid[None])[:, 0]))
    r_base = int(np.argmin(dist(Rc, base[None])[:, 0]))
    out = dict(seed=seed, v_clean=float(delivery_points(tx_signal_mw(base[None], path), 0.0).mean()), v_norelay=v0, V0_check=V0,
               v_refined=ref, v_stack=float(V[r_best]), v_randrelay=V_rand, v_centroid=float(V[r_cent]), v_colocated=float(V[r_base]),
               worst_j=inst["cand"][j0].tolist(), j_to_path=float(dist(inst["cand"][j0][None], path).min()),
               j_to_base=float(np.linalg.norm(inst["cand"][j0] - base)), relay=Rc[r_best].tolist(),
               relay_to_base=float(np.linalg.norm(Rc[r_best] - base)))
    if check_mc:
        mask = allowed_mask(inst); allowed = np.where(mask)[0]
        pick = rng.choice(allowed, 60, replace=False)
        mc_star = np.mean([mc_path_delivery(inst, base[None], inst["cand"][j0], np.random.default_rng(seed * 7 + k)) for k in range(3)])
        mc_rand = np.array([mc_path_delivery(inst, base[None], inst["cand"][p], np.random.default_rng(seed * 11 + int(p))) for p in pick])
        out["mc_star"] = float(mc_star); out["mc_rank"] = float((mc_rand > mc_star).mean())   # share of random positions that hurt LESS than J*
        out["mc_rand_mean"] = float(mc_rand.mean())
        txs2 = np.vstack([base, Rc[r_best]]); j1, v1, _ = worst_spot(inst, txs2)
        out["mc_stack"] = float(np.mean([mc_path_delivery(inst, txs2, inst["cand"][j1], np.random.default_rng(seed * 13 + k)) for k in range(3)]))
        out["v_stack_check"] = v1
        out["v_stack_ref"] = min(v1, refine_jammer(inst, txs2, j1, seed=seed))
    return out, inst, dg, V, Rc

def main(nseeds=30):
    rows, keep = [], None
    for s in range(nseeds):
        r, inst, dg, V, Rc = run_seed(s); rows.append(r)
        if s == 3: keep = (inst, dg, V, Rc, r)
    g = lambda k: np.array([r[k] for r in rows])
    print(f"E12 {nseeds} random patrol/base instances (seed = instance)")
    print(f"  clean delivery {fmt(g('v_clean'),4)}")
    print(f"  worst-spot jammer, no relay      : grid {fmt(g('v_norelay'))}, after continuous refinement {fmt(g('v_refined'))} (max refinement gain {np.max(g('v_norelay')-g('v_refined')):.4f})")
    print(f"  ... random relay (mean of 10)    : {fmt(g('v_randrelay'))}")
    print(f"  ... relay at path centroid       : {fmt(g('v_centroid'))}")
    print(f"  ... relay colocated with base    : {fmt(g('v_colocated'))}")
    print(f"  ... Stackelberg relay            : {fmt(g('v_stack'))}")
    d, h = paired_ci(g('v_stack'), g('v_norelay')); print(f"  paired gain Stackelberg - no relay : {d:.3f} +/- {h:.3f}")
    d2, h2 = paired_ci(g('v_stack'), g('v_randrelay')); print(f"  paired gain Stackelberg - random   : {d2:.3f} +/- {h2:.3f}")
    print(f"  worst jammer spot: {fmt(g('j_to_path'),1)} m from nearest path point (standoff {STANDOFF:.0f} m), {fmt(g('j_to_base'),1)} m from base")
    print(f"  relay-to-base distance {fmt(g('relay_to_base'),1)} m")
    print(f"  MC with fading+shadowing: delivery at J* {fmt(g('mc_star'))}, random positions {fmt(g('mc_rand_mean'))}; share of random positions hurting LESS than J* {fmt(g('mc_rank'))}")
    d3, h3 = paired_ci(g('mc_stack'), g('mc_star'))
    print(f"  MC (fading+shadowing) at each side's best-response spot: no relay {fmt(g('mc_star'))}, Stackelberg relay {fmt(g('mc_stack'))}, paired gain {d3:.3f} +/- {h3:.3f}")
    print(f"  Stackelberg relay, jammer refined: {fmt(g('v_stack_ref'))}")
    d4, h4 = paired_ci(g('v_stack_ref'), g('v_refined')); print(f"  paired gain (both refined) {d4:.3f} +/- {h4:.3f}")
    key("worst-spot delivery no relay (refined jammer)", fmt(g('v_refined')))
    key("worst-spot delivery with Stackelberg relay (refined jammer)", fmt(g('v_stack_ref')))
    save_json("e12_placement.json", dict(rows=rows))
    inst, dg, V, Rc, r = keep
    fig, ax = plt.subplots(1, 3, figsize=(12.5, 3.9))
    a = ax[0]; G = int(round(len(inst["cand"]) ** .5))
    im = a.imshow(dg.reshape(G, G), origin="lower", extent=[0, ARENA, 0, ARENA], cmap="viridis"); plt.colorbar(im, ax=a, label="path-mean delivery")
    a.plot(*inst["path"].T, "w-", lw=2); a.plot(*inst["base"], "s", c=C["orange"], ms=8, label="base"); a.plot(*r["worst_j"], "x", c=C["verm"], ms=10, mew=2.5, label="worst jammer spot")
    a.set_title("seed 3: jammer position vs delivery"); a.legend(loc="lower right"); a.grid(False)
    a = ax[1]; Gr = G_R
    im = a.imshow(V.reshape(Gr, Gr), origin="lower", extent=[5, ARENA - 5, 5, ARENA - 5], cmap="magma"); plt.colorbar(im, ax=a, label="worst-case delivery V(R)")
    a.plot(*inst["path"].T, "w-", lw=2); a.plot(*inst["base"], "s", c=C["orange"], ms=8); a.plot(*r["relay"], "*", c=C["sky"], ms=14, label="Stackelberg relay"); a.legend(loc="lower right")
    a.set_title("relay position vs worst-case delivery"); a.grid(False)
    a = ax[2]
    labs = ["no relay", "colocated", "random", "centroid", "Stackelberg"]
    cols = [g('v_norelay'), g('v_colocated'), g('v_randrelay'), g('v_centroid'), g('v_stack')]
    for i, c in enumerate(cols):
        m_, h_ = ci95(c); a.bar(i, m_, yerr=h_, color=[C["grey"], C["grey"], C["sky"], C["blue"], C["green"]][i], capsize=3)
    a.set_xticks(range(5)); a.set_xticklabels(labs, rotation=20); a.set_ylim(0.6, 1.0); a.set_ylabel("worst-spot delivery (mean, 95% CI, 30 seeds)")
    save_fig(fig, "e12_placement.png")

if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 30)
