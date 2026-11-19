"""E14 (RED_TEAM idea 14): energy-optimal jammer. Minimise the jammer's own battery energy for a target damage, then price it against the defender.
Link: transmitter 15 dBm, 30 m to the receiver; jammer 20 m from the receiver (same path-loss model as E12). Rayleigh fading on signal and jammer.
Jammer energy per transmitting slot  c(P) = P_mW/ETA + P_FIX  (power-amplifier efficiency ETA = 0.3, always-on radio overhead P_FIX = 30 mW, 1 ms slots,
so mW = microjoule per slot). Strategies: BLIND (k parallel radios, each jamming one random channel; duty d) and REACTIVE (listens every slot at
P_LISTEN, detects the active channel with prob A_DET and jams it with duty d). Target: delivery loss DELTA = 0.30 versus the unjammed link.
Search: P in 41 levels x k in 1..13 x d in 20 levels, damage per jammed slot D(P) estimated by Monte Carlo (20 seeds x 20000 fade draws);
the chosen configuration is then re-played in an independent slot-level simulation (random hop, random jam channels) to confirm damage and energy.
Defender pricing: ARQ energy per delivered packet, and the price of buying margin (+dB transmit power) versus the jammer's extra energy. Simulation only."""
import sys
import numpy as np
from _common import *

PT_DBM, D_TX, D_JAM = 15.0, 30.0, 20.0
ETA, P_FIX, P_LISTEN, A_DET = 0.3, 30.0, 60.0, 0.9
DELTA = 0.30
P_GRID = np.arange(-10, 31, 1.0)                  # dBm
K_GRID = np.arange(1, 14); DUTY = np.linspace(0.05, 1.0, 20)
NF = 20000

def cost(p_dbm): return dbm2mw(p_dbm) / ETA + P_FIX                        # uJ per transmitting slot
def sig_mw(margin=0.0): return float(rx_mw(PT_DBM + margin, D_TX))
JAM_GAIN_DB = -float(path_loss_db(D_JAM))

def damage_table(rng, margin_db=(0.0,), nf=NF):
    """D[m, p] = 1 - E[PRR] under jamming at power P_GRID[p] (Rayleigh on both links) minus clean loss; same fade draws for all P"""
    fs = rng.exponential(1.0, nf); fj = rng.exponential(1.0, nf); out = np.empty((len(margin_db), len(P_GRID)))
    for mi, m in enumerate(margin_db):
        S = sig_mw(m) * fs
        clean = prr_from_mw(S, 0.0).mean()
        for pi, p in enumerate(P_GRID):
            out[mi, pi] = clean - prr_from_mw(S, dbm2mw(p + JAM_GAIN_DB) * fj).mean()
    return out

def best_blind(D, delta=DELTA, pl=0.0):
    """min over (P,k,d) of energy per slot  k*d*c(P)  s.t. (k/13)*d*D(P) >= delta"""
    best = (np.inf, None)
    for pi, p in enumerate(P_GRID):
        Dp = D[pi]
        if Dp <= 0: continue
        for k in K_GRID:
            dmin = delta / ((k / 13) * Dp)
            if dmin > 1: continue
            d = DUTY[DUTY >= dmin - 1e-12][0] if (DUTY >= dmin - 1e-12).any() else None
            if d is None: continue
            e = k * d * cost(p)
            if e < best[0]: best = (e, dict(P=float(p), k=int(k), d=float(d)))
    return best

def best_reactive(D, delta=DELTA, p_listen=P_LISTEN):
    best = (np.inf, None)
    for pi, p in enumerate(P_GRID):
        Dp = D[pi]
        if Dp <= 0: continue
        dmin = delta / (A_DET * Dp)
        if dmin > 1: continue
        d = DUTY[DUTY >= dmin - 1e-12][0] if (DUTY >= dmin - 1e-12).any() else None
        if d is None: continue
        e = p_listen + d * A_DET * cost(p)                      # pays for a transmission only when it detects and jams
        if e < best[0]: best = (e, dict(P=float(p), d=float(d)))
    return best

def slot_sim(cfg, kind, rng, nslot=100000, p_listen=P_LISTEN):
    """independent slot-level replay: random hop channel, jammer chooses channels/slots, fading drawn per slot. Returns (loss, energy/slot)."""
    hop = rng.integers(0, 13, nslot); fs = rng.exponential(1.0, nslot); fj = rng.exponential(1.0, nslot)
    S = sig_mw() * fs; clean = prr_from_mw(S, 0.0)
    jam_p = dbm2mw(cfg["P"] + JAM_GAIN_DB) * fj
    if kind == "blind":
        on = rng.random(nslot) < cfg["d"]
        r = rng.random((nslot, 13)); chans = np.argsort(r, axis=1)[:, :cfg["k"]]
        hit = on & (chans == hop[:, None]).any(1)
        energy = (on.sum() * cfg["k"] * cost(cfg["P"])) / nslot
    else:
        att = rng.random(nslot) < cfg["d"]; det = att & (rng.random(nslot) < A_DET); hit = det
        energy = p_listen + det.sum() * cost(cfg["P"]) / nslot
    got = np.where(hit, prr_from_mw(S, jam_p), clean)
    # delivery estimated by the expectation over the PRR, sample-wise; loss relative to the same slots without jamming
    return float((clean - got).mean()), float(energy)

def run_seed(seed):
    rng = np.random.default_rng(seed)
    margins = (0.0, 3.0, 6.0, 9.0, 12.0)
    Dm = damage_table(rng, margins); D0 = Dm[0]
    eb, cb = best_blind(D0); er, cr = best_reactive(D0)
    # naive alternatives for comparison: "just enough on average" (mean SINR = threshold) and "full power"
    p_naive = float(P_GRID[np.argmin(np.abs(P_GRID - (10 * np.log10(sig_mw() / NOISE_MW) + 10 * np.log10(NOISE_MW) - JAM_GAIN_DB + THETA)))])
    p_full = float(P_GRID[-1])
    def blind_at(p):
        pi = int(np.where(P_GRID == p)[0][0]); b = best_blind_fixedP(D0[pi], p); return b
    out = dict(seed=seed, e_blind=eb, cfg_blind=cb, e_react=er, cfg_react=cr, p_naive=p_naive,
               e_blind_naive=blind_at(p_naive), e_blind_full=blind_at(p_full))
    # reactive cross-over by scanning the listening power
    pls = np.arange(0, 400, 2.0)
    out["listen_crossover_mw"] = float(next((pl for pl in pls if best_reactive(D0, p_listen=pl)[0] >= eb), np.nan))
    # sweep of P* with listening cost (should increase / stay)
    out["pstar_vs_listen"] = {str(pl): best_reactive(D0, p_listen=pl)[1]["P"] if best_reactive(D0, p_listen=pl)[1] else None for pl in (0, 30, 60, 120, 240)}
    # margin pricing: jammer energy for the same target when the defender adds margin dB
    out["margin"] = []
    for mi, m in enumerate(margins):
        e_m, c_m = best_blind(Dm[mi]); e_r, _ = best_reactive(Dm[mi])
        out["margin"].append(dict(margin_db=m, e_blind=e_m, e_react=e_r, defender_uJ_per_slot=float(dbm2mw(PT_DBM + m) / ETA + P_FIX)))
    out["curve_D"] = D0.tolist()
    return out

def best_blind_fixedP(Dp, p, delta=DELTA):
    if Dp <= 0: return float("nan")
    e = np.inf
    for k in K_GRID:
        dmin = delta / ((k / 13) * Dp)
        ok = DUTY[DUTY >= dmin - 1e-12]
        if dmin <= 1 and len(ok): e = min(e, k * ok[0] * cost(p))
    return float(e) if np.isfinite(e) else float("nan")

def main(nseeds=20):
    rows = [run_seed(s) for s in range(nseeds)]
    g = lambda k: np.array([r[k] for r in rows], dtype=float)
    print(f"E14 {nseeds} seeds. target delivery loss {DELTA}; uJ per 1 ms slot; c(P)=P/{ETA}+{P_FIX:.0f}")
    print(f"  blind optimum: {fmt(g('e_blind'),1)} uJ/slot ; typical config {rows[0]['cfg_blind']}")
    print(f"  reactive optimum (listen {P_LISTEN:.0f} mW): {fmt(g('e_react'),1)} uJ/slot ; typical config {rows[0]['cfg_react']}")
    print(f"  blind at 'just enough on average' P={rows[0]['p_naive']:.0f} dBm: {fmt(g('e_blind_naive'),1)} ; at full power 30 dBm: {fmt(g('e_blind_full'),1)}")
    Pstar = np.array([r["cfg_blind"]["P"] for r in rows]); print(f"  blind optimal P* = {fmt(Pstar,2)} dBm (grid 1 dB)")
    print(f"  reactive beats blind while listening power < {fmt(g('listen_crossover_mw'),0)} mW")
    # slot-level confirmation
    rng = np.random.default_rng(99); lb, eb_s, lr, er_s = [], [], [], []
    for s in range(nseeds):
        a, b = slot_sim(rows[s]["cfg_blind"], "blind", rng); lb.append(a); eb_s.append(b)
        a, b = slot_sim(rows[s]["cfg_react"], "react", rng); lr.append(a); er_s.append(b)
    print(f"  slot-level replay: blind loss {fmt(lb,3)} energy {fmt(eb_s,1)} ; reactive loss {fmt(lr,3)} energy {fmt(er_s,1)}")
    # pricing
    print("  margin pricing (blind jammer, same target): margin dB | jammer uJ/slot | defender uJ/slot | d(jammer)/d(defender) vs 0 dB")
    mg = np.array([[m["e_blind"] for m in r["margin"]] for r in rows]); df = np.array([m["defender_uJ_per_slot"] for m in rows[0]["margin"]])
    ratios = []
    for i, m in enumerate((0, 3, 6, 9, 12)):
        rr = (mg[:, i] - mg[:, 0]) / (df[i] - df[0]) if i else np.full(len(rows), np.nan); ratios.append(rr)
        print(f"    {m:2d} | {fmt(mg[:, i],0)} | {df[i]:.0f} | {fmt(rr,2) if i else '-'}")
    arq = 135.0                                                       # defender attempt energy at 15 dBm: 31.6/0.3+30
    arq = float(dbm2mw(PT_DBM) / ETA + P_FIX)
    extra = arq * (1 / (1 - DELTA) - 1)
    ratio = g('e_blind') / extra
    print(f"  defender ARQ extra energy {extra:.0f} uJ/slot at loss {DELTA}; jammer/defender energy ratio (blind) {fmt(ratio,2)}, (reactive) {fmt(g('e_react')/extra,2)}")
    key("blind-jammer min energy (uJ/slot) for 30% delivery loss", fmt(g('e_blind'), 1))
    key("reactive-jammer min energy (uJ/slot)", fmt(g('e_react'), 1))
    key("cost-exchange ratio jammer/defender (blind)", fmt(ratio, 2))
    save_json("e14_energy.json", dict(rows=[{k: v for k, v in r.items() if k != "curve_D"} for r in rows], slot=dict(lb=lb, eb=eb_s, lr=lr, er=er_s)))
    D = np.array([r["curve_D"] for r in rows]); Dm_, Dh = D.mean(0), np.array([ci95(D[:, i])[1] for i in range(D.shape[1])])
    fig, ax = plt.subplots(1, 3, figsize=(12.5, 3.8))
    a = ax[0]; a.plot(P_GRID, Dm_, color=C["blue"]); a.fill_between(P_GRID, Dm_ - Dh, Dm_ + Dh, alpha=.3, color=C["blue"])
    a.set_xlabel("jammer power (dBm)"); a.set_ylabel("damage per jammed slot D(P)"); a.set_title("Rayleigh fading smooths the waterfall")
    a = ax[1]
    eng = lambda p: cost(p) / np.maximum(Dm_, 1e-9)
    a.plot(P_GRID, np.where(Dm_ > 0.02, eng(P_GRID), np.nan), color=C["verm"]); ps = float(np.mean(Pstar)); a.axvline(ps, color=C["grey"], ls="--")
    a.set_xlabel("jammer power (dBm)"); a.set_ylabel("energy per unit damage  c(P)/D(P)  (uJ)"); a.set_title(f"interior optimum near {ps:.0f} dBm"); a.set_yscale("log")
    a = ax[2]
    for lab, y, col in [("blind", mg, C["verm"])]:
        m_ = [ci95(y[:, i]) for i in range(5)]; a.errorbar((0, 3, 6, 9, 12), [x[0] for x in m_], [x[1] for x in m_], marker="o", color=col, label="jammer energy (blind), target 30% loss", capsize=2)
    a.plot((0, 3, 6, 9, 12), df, "s-", color=C["green"], label="defender TX energy per slot (always on)")
    a.set_xlabel("margin bought by the defender (dB)"); a.set_ylabel("uJ per slot"); a.legend(); a.set_yscale("log")
    save_fig(fig, "e14_energy.png")

if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
