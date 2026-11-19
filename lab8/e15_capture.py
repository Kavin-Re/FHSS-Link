"""E15 (RED_TEAM idea 15): capture effect and near-far abuse. Simulation only, own-link model (same radio constants as _common.py).
Receiver model (assumptions, not measurements): a receiver LOCKS onto one transmission at the preamble. Preamble detection needs SNR >= DET_DB.
  * 'first'   receiver (typical simple FSK/O-QPSK front end): locks onto the earliest detectable preamble and keeps it. A weak but EARLY frame wins.
  * 'strongest' receiver (message-in-message / re-lock): keeps the first lock but re-locks to a later frame that is at least MIM_DB stronger; with
                simultaneous starts the stronger frame (by CAP_DB) is taken.
After locking onto frame X, X is decoded with prob PRR(S_X / (N + S_other)) (waterfall in _common.py). A locked attacker frame = legit frame lost.
Geometry: legit TX 30 m from the receiver (15 dBm), attacker at distance d_a with power P_a, on the right channel with prob k/13 (blind to the hop).
Fading: Rayleigh power fading (mean 1) on both links, independent per slot. Defensive lesson: receiver design margin (re-lock / MiM threshold) and
sensitivity floor: the attacker does not need to be loud, only early and detectable. The attack here is a model of denial of delivery on our own link."""
import sys
import numpy as np
from _common import *

PT_DBM, D_LEG = 15.0, 30.0
DET_DB, CAP_DB, MIM_DB = 2.0, 3.0, 6.0
K_CH = 13

def sim(rng, n, p_att_dbm, d_att, rx, early, nf=True):
    """Monte-Carlo over n slots with attacker on the hop channel in every slot. Returns dict(deliv, att_lock)."""
    fl = rng.exponential(1.0, n) if nf else np.ones(n); fa = rng.exponential(1.0, n) if nf else np.ones(n)
    Sl = float(rx_mw(PT_DBM, D_LEG)) * fl; Sa = float(rx_mw(p_att_dbm, d_att)) * fa
    det_l = Sl >= NOISE_MW * 10 ** (DET_DB / 10); det_a = Sa >= NOISE_MW * 10 ** (DET_DB / 10)
    ratio_db = 10 * np.log10(Sa / Sl)                                   # attacker relative to legit, dB
    if rx == "first":
        lock_att = det_a & (early | ~det_l)
    else:
        if early:   lock_att = det_a & (~det_l | (ratio_db > -MIM_DB))  # re-lock to legit only if legit >= MIM_DB stronger
        else:       lock_att = det_a & (~det_l | (ratio_db > CAP_DB))   # simultaneous: stronger by CAP_DB wins
    pl = prr_from_mw(Sl, Sa); pc = prr_from_mw(Sl, 0.0)
    deliv = np.where(lock_att, 0.0, pl)
    return dict(deliv=float(deliv.mean()), att_lock=float(lock_att.mean()), clean=float(pc.mean()))

def overall(res_hit, k):
    """mean delivery when the attacker is on the hop channel with prob k/13"""
    return (k / K_CH) * res_hit["deliv"] + (1 - k / K_CH) * res_hit["clean"]

def run_seed(seed, n=4000):
    rng = np.random.default_rng(1000 + seed); out = {}
    # (a) attacker power sweep at 25 m, early vs simultaneous, both receivers
    P = np.arange(-60, 21, 5.0); out["P"] = P.tolist()
    for rx in ("first", "strongest"):
        for early in (True, False):
            out[f"{rx}_{'early' if early else 'sim'}"] = [sim(rng, n, p, 25.0, rx, early)["deliv"] for p in P]
    out["clean"] = sim(rng, n, -200.0, 25.0, "first", True)["clean"]
    # (b) minimum attacker power for 50% delivery loss (grid, finest 1 dB) for early frames
    Pf = np.arange(-70, 21, 1.0)
    for rx in ("first", "strongest"):
        d = np.array([sim(rng, 1500, p, 25.0, rx, True)["deliv"] for p in Pf]); ok = np.where(d < 0.5 * out["clean"])[0]
        out[f"p50_{rx}"] = float(Pf[ok[0]]) if len(ok) else float("nan")
    # (c) near-far: attacker at fixed 0 dBm, distance sweep
    D = np.array([5, 10, 20, 40, 80, 160.0]); out["D"] = D.tolist()
    for rx in ("first", "strongest"): out[f"dist_{rx}"] = [sim(rng, n, 0.0, d, rx, True)["deliv"] for d in D]
    # (d) frequency coverage k of 13 at fixed 0 dBm / 25 m, first-lock early
    r = sim(rng, n, 0.0, 25.0, "first", True); out["k"] = {str(k): overall(r, k) for k in (1, 3, 6, 13)}
    return out

def main(nseeds=24):
    rows = [run_seed(s) for s in range(nseeds)]
    g = lambda k: np.array([r[k] for r in rows], dtype=float)
    print(f"E15 {nseeds} seeds. legit {PT_DBM:.0f} dBm at {D_LEG:.0f} m; detection SNR {DET_DB} dB; MiM {MIM_DB} dB; capture {CAP_DB} dB; clean delivery {fmt(g('clean'))}")
    print("  attacker power at 25 m (dBm) | delivery: first/early | first/simult | strongest/early | strongest/simult")
    P = rows[0]["P"]
    for i, p in enumerate(P):
        print(f"   {p:5.0f} | " + " | ".join(fmt(g(k)[:, i], 3) for k in ("first_early", "first_sim", "strongest_early", "strongest_sim")))
    for rx in ("first", "strongest"):
        print(f"  attacker power for >=50% loss, early frame, {rx}-lock receiver: {fmt(g('p50_'+rx), 1)} dBm")
    d = g("p50_strongest") - g("p50_first")
    print(f"  extra power the attacker needs against the re-lock receiver: {fmt(d, 1)} dB (paired)")
    print("  distance sweep at 0 dBm early: " + "; ".join(f"{dd:.0f} m: {fmt(g('dist_first')[:, i],2)} / {fmt(g('dist_strongest')[:, i],2)}" for i, dd in enumerate(rows[0]['D'])))
    print("  channel coverage k/13 (first-lock, 0 dBm, 25 m): " + "; ".join(f"k={k}: {fmt([r['k'][k] for r in rows],3)}" for k in rows[0]["k"]))
    key("attacker power for 50% loss, first-lock vs strongest-lock receiver (dBm)", f"{fmt(g('p50_first'),1)} vs {fmt(g('p50_strongest'),1)}")
    key("extra attacker power forced by the re-lock receiver (dB)", fmt(d, 1))
    save_json("e15_capture.json", rows)
    fig, ax = plt.subplots(1, 2, figsize=(10.5, 3.8)); cols = dict(first_early=C["verm"], first_sim=C["orange"], strongest_early=C["blue"], strongest_sim=C["sky"])
    for k, c in cols.items():
        y = g(k); m = y.mean(0); h = np.array([ci95(y[:, i])[1] for i in range(y.shape[1])]); ax[0].plot(P, m, color=c, label=k.replace("_", " / ")); ax[0].fill_between(P, m - h, m + h, color=c, alpha=.25)
    ax[0].set_xlabel("attacker power at 25 m (dBm)"); ax[0].set_ylabel("legit delivery (attacker on the hop channel)"); ax[0].legend(); ax[0].set_title("an early weak frame captures a first-lock receiver")
    Dd = rows[0]["D"]
    for rx, c in (("first", C["verm"]), ("strongest", C["blue"])):
        y = g("dist_" + rx); ax[1].errorbar(Dd, y.mean(0), [ci95(y[:, i])[1] for i in range(y.shape[1])], color=c, marker="o", label=rx + "-lock", capsize=2)
    ax[1].set_xscale("log"); ax[1].set_xlabel("attacker distance (m), 0 dBm, early"); ax[1].set_ylabel("legit delivery"); ax[1].legend(); ax[1].set_title("near-far")
    save_fig(fig, "e15_capture.png")

if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 24)
