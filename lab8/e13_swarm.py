"""E13 (RED_TEAM idea 13): one strong jammer vs a swarm of N weak coordinated jammers with the SAME total power; spatial-diversity best response.
Swarm jammers jam the same k=3 channels together (interference powers add at the mobile receiver); positions chosen by greedy sequential
placement on a candidate grid (>= STANDOFF m from the path). Same link model as E12. Simulation only.
Claims: (a) delivery vs N at fixed total power; (b) total power needed for a target damage, vs N; (c) a relay (E12-style) placed as a best
response to the observed swarm, after which the swarm re-places (one round of alternating best response)."""
import sys
import numpy as np
from _spatial import *
from e12_placement import allowed_mask, relay_candidates, STANDOFF

PTOT_DBM = 0.0
TARGET = 0.90
NS = [1, 2, 4, 8, 16]

def greedy_swarm(inst, N, ptot_dbm, txs, n=None, rng=None, random_place=False, standoff=STANDOFF):
    """returns (positions (N,2), mean delivery). txs (T,2) transmitters."""
    path = inst["path"]; mask = allowed_mask(inst, standoff); cand = inst["cand"][mask]
    pe = ptot_dbm - 10 * np.log10(N)
    Ic = rx_mw(pe, dist(cand, path), n)                              # (G', m) each candidate's power at each path point
    S = tx_signal_mw(txs, path, n)
    I = np.zeros(len(path)); pos = []
    if random_place:
        idx = rng.choice(len(cand), N, replace=True); I = Ic[idx].sum(0); pos = cand[idx]
        return np.array(pos), float(delivery_points(S, I).mean())
    for _ in range(N):
        dl = delivery_points(S, I[None, :] + Ic).mean(1)
        i = int(np.argmin(dl)); I = I + Ic[i]; pos.append(cand[i])
    return np.array(pos), float(delivery_points(S, I).mean())

def power_for_target(inst, N, target, txs, n=None, lo=-30.0, hi=40.0, iters=10):
    """smallest total power (dBm) for which the greedy swarm gets mean delivery <= target (bisection; monotone in power)"""
    if greedy_swarm(inst, N, hi, txs, n)[1] > target: return float("nan")
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        if greedy_swarm(inst, N, mid, txs, n)[1] <= target: hi = mid
        else: lo = mid
    return hi

def best_response_relay(inst, jam_pos, pe_dbm, base):
    path = inst["path"]; Rc = relay_candidates()
    I = rx_mw(pe_dbm, dist(jam_pos, path)).sum(0)
    SB = tx_signal_mw(base[None], path)
    V = [float(delivery_points(np.vstack([SB, tx_signal_mw(r[None], path)]), I).mean()) for r in Rc]
    return Rc[int(np.argmax(V))], max(V)

def run_seed(seed):
    inst = random_instance(seed); base = inst["base"][None]; rng = np.random.default_rng(500 + seed)
    r = dict(seed=seed)
    for N in NS:
        pos, v = greedy_swarm(inst, N, PTOT_DBM, base)
        rp = np.mean([greedy_swarm(inst, N, PTOT_DBM, base, rng=rng, random_place=True)[1] for _ in range(10)])
        r[f"v_{N}"] = v; r[f"vrand_{N}"] = float(rp)
        relay, _ = best_response_relay(inst, pos, PTOT_DBM - 10 * np.log10(N), inst["base"])
        txs2 = np.vstack([inst["base"], relay])
        r[f"vrelay_fixedpos_{N}"] = float(delivery_points(tx_signal_mw(txs2, inst["path"]),
                                          rx_mw(PTOT_DBM - 10 * np.log10(N), dist(pos, inst["path"])).sum(0)).mean())
        r[f"vrelay_reopt_{N}"] = greedy_swarm(inst, N, PTOT_DBM, txs2)[1]
        r[f"ptarget_{N}"] = power_for_target(inst, N, TARGET, base)
    for N in (1, 8):                                                  # larger stand-off, higher power so that damage is visible
        r[f"so25_{N}"] = greedy_swarm(inst, N, 10.0, base, standoff=25.0)[1]
    # path-loss exponent sensitivity of the swarm advantage (damage relative to the clean-link delivery at the same n)
    for nn in (2.0, 4.0):
        clean = float(delivery_points(tx_signal_mw(base, inst["path"], nn), 0.0).mean())
        for N in (1, 8):
            r[f"dmg_n{int(nn)}_{N}"] = clean - greedy_swarm(inst, N, PTOT_DBM, base, n=nn)[1]
    return r, inst

def main(nseeds=30):
    rows = []; keep = None
    for s in range(nseeds):
        r, inst = run_seed(s); rows.append(r)
        if s == 3: keep = (inst, r)
    g = lambda k: np.array([r[k] for r in rows], dtype=float)
    print(f"E13 {nseeds} random instances; total jammer power {PTOT_DBM:.0f} dBm split equally over N jammers (N=1 is E12's jammer)")
    print("  N : mean path delivery (greedy placement) | random placement | after relay best-response, swarm re-placed | power for delivery<=0.90 (dBm total)")
    for N in NS:
        print(f"  {N:2d}: {fmt(g(f'v_{N}'))} | {fmt(g(f'vrand_{N}'))} | {fmt(g(f'vrelay_reopt_{N}'))} | {fmt(g(f'ptarget_{N}'),2)}")
    d, h = paired_ci(g('v_8'), g('v_1')); print(f"  paired delivery N=8 minus N=1 : {d:.3f} +/- {h:.3f}")
    d2, h2 = paired_ci(g('ptarget_8'), g('ptarget_1')); print(f"  paired total-power needed N=8 minus N=1 (dB): {d2:.2f} +/- {h2:.2f}")
    for nn in (2, 4):
        a, b = g(f"dmg_n{nn}_1"), g(f"dmg_n{nn}_8")
        print(f"  n={nn}: damage (clean - delivered) N=1 {fmt(a)}  N=8 {fmt(b)}  ratio of means {b.mean()/a.mean():.2f}")
    d3, h3 = paired_ci(g("vrelay_reopt_8"), g("vrelay_reopt_1"))
    print(f"  after relay response + re-placement: paired N=8 minus N=1 delivery {d3:.3f} +/- {h3:.3f} (positive = swarm weaker than the single jammer)")
    a, b = g("so25_1"), g("so25_8"); dd, hh = paired_ci(b, a)
    print(f"  stand-off 25 m, total power 10 dBm: N=1 {fmt(a)}  N=8 {fmt(b)}  paired N=8 minus N=1 {dd:.3f} +/- {hh:.3f}")
    key("delivery at fixed total power N=1 / N=8 / N=16", f"{fmt(g('v_1'))} / {fmt(g('v_8'))} / {fmt(g('v_16'))}")
    key("total power needed for delivery<=0.90 (dB), N=8 minus N=1", f"{d2:.2f} +/- {h2:.2f}")
    key("delivery after relay response + swarm re-placement, N=1 / N=8", f"{fmt(g('vrelay_reopt_1'))} / {fmt(g('vrelay_reopt_8'))}")
    save_json("e13_swarm.json", dict(rows=rows))
    fig, ax = plt.subplots(1, 3, figsize=(12.5, 3.8))
    a = ax[0]
    for lab, pre, col in [("greedy placement", "v_", C["verm"]), ("random placement", "vrand_", C["grey"]), ("with relay, swarm re-placed", "vrelay_reopt_", C["green"])]:
        m = [ci95(g(f"{pre}{N}")) for N in NS]
        a.errorbar(NS, [x[0] for x in m], [x[1] for x in m], marker="o", color=col, label=lab, capsize=2)
    a.set_xscale("log", base=2); a.set_xticks(NS); a.set_xticklabels(NS); a.set_xlabel("number of jammers N (fixed total power)"); a.set_ylabel("mean path delivery"); a.legend()
    a = ax[1]
    m = [ci95(g(f"ptarget_{N}")) for N in NS]
    a.errorbar(NS, [x[0] for x in m], [x[1] for x in m], marker="s", color=C["blue"], capsize=2)
    a.set_xscale("log", base=2); a.set_xticks(NS); a.set_xticklabels(NS); a.set_xlabel("N"); a.set_ylabel("total power for delivery <= 0.90 (dBm)")
    a = ax[2]; inst, r = keep
    a.plot(*inst["path"].T, "k-", lw=2); a.plot(*inst["base"], "s", c=C["orange"], ms=8, label="base")
    pos, _ = greedy_swarm(inst, 1, PTOT_DBM, inst["base"][None]); a.plot(*pos.T, "x", c=C["verm"], ms=11, mew=3, label="N=1")
    pos, _ = greedy_swarm(inst, 8, PTOT_DBM, inst["base"][None]); a.plot(*pos.T, "o", c=C["sky"], ms=6, label="N=8")
    a.set_xlim(0, ARENA); a.set_ylim(0, ARENA); a.set_aspect("equal"); a.legend(); a.set_title("seed 3: placements")
    save_fig(fig, "e13_swarm.png")

if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 30)
