"""E17 (RED_TEAM idea 17): moving-target link. Simulation only, own link, same radio constants as _common.py.
The link varies FEATURES, not only the channel: modulation (A robust / B fast), packet length (32 / 128 B) and slot-timing offset (0..3). F = 16 feature
configurations. A feature-locking jammer (learns which configuration the link uses) couples its power into the receiver with a MATCH GAIN that depends on
how many features it matches (ASSUMPTIONS, not measurements): wrong modulation -8 dB, wrong length -3 dB, wrong timing -6 dB; all matched = 0 dB.
Geometry: link 30 m, 15 dBm; jammer d_J metres from the receiver, P_J dBm, on the hop channel every slot (worst case for the link, isolates the feature effect).
Rayleigh fading on both links. PRR threshold: A 6 dB, B 12 dB, +1.5 dB per doubling of length over 32 B. Rate: A 1, B 2; goodput = rate x (L/(L+8)) x PRR.
Jammer: UCB1 bandit over the 16 configurations, reward = observed loss of a packet (0/1). Link policies: static (best clean goodput config) or uniform over the n best
configs (diversity H = log2 n bits). Reported: goodput relative to the unjammed static link, after the jammer has learned (last half of 6000 slots).
Defensive lesson: diversity is a currency - it costs clean goodput and only pays while the jammer is power-limited, not when raw power drowns every mismatch."""
import sys, itertools
import numpy as np
from _common import *

PT_DBM, D_LINK = 15.0, 30.0
THETA_M = {0: 6.0, 1: 12.0}; RATE_M = {0: 1.0, 1: 2.0}; LENS = (32, 128); N_TIM = 4
G_MOD, G_LEN, G_TIM = -8.0, -3.0, -6.0
FEATS = list(itertools.product((0, 1), (0, 1), range(N_TIM)))          # (mod, len idx, timing)
F = len(FEATS); T_SIM = 6000

def prr_f(feat, sinr_db):
    m, li, _ = feat; th = THETA_M[m] + 1.5 * np.log2(LENS[li] / 32)
    return 1.0 / (1.0 + np.exp(-(np.asarray(sinr_db) - th) / WIDTH))

def rate_f(feat):
    m, li, _ = feat; return RATE_M[m] * LENS[li] / (LENS[li] + 8)

def match_gain_db(link, arm):
    return (G_MOD if link[0] != arm[0] else 0.0) + (G_LEN if link[1] != arm[1] else 0.0) + (G_TIM if link[2] != arm[2] else 0.0)

def tables(rng, pj_dbm, d_j, nf=4000):
    """PRR[link, arm] with jammer, PRR0[link] clean (Rayleigh on both links, same draws for every pair)"""
    fs = rng.exponential(1.0, nf); fj = rng.exponential(1.0, nf)
    S = float(rx_mw(PT_DBM, D_LINK)) * fs; Jm = float(rx_mw(pj_dbm, d_j)) * fj
    P = np.empty((F, F)); P0 = np.empty(F)
    for i, lf in enumerate(FEATS):
        P0[i] = prr_f(lf, 10 * np.log10(S / NOISE_MW)).mean()
        for a, af in enumerate(FEATS):
            g = 10 ** (match_gain_db(lf, af) / 10)
            P[i, a] = prr_f(lf, 10 * np.log10(S / (NOISE_MW + g * Jm))).mean()
    return P, P0

def learn(rng, P, policy, T=T_SIM):
    """UCB1 jammer vs link policy (array of config indices used uniformly). Returns mean goodput over the last half and the jammer's arm counts."""
    cnt = np.zeros(F); rew = np.zeros(F); gp = 0.0; n2 = 0; rates = np.array([rate_f(f) for f in FEATS])
    for t in range(T):
        a = t if t < F else int(np.argmax(rew / np.maximum(cnt, 1) + np.sqrt(2 * np.log(t + 1) / np.maximum(cnt, 1))))
        li = policy[rng.integers(len(policy))]
        ok = rng.random() < P[li, a]
        cnt[a] += 1; rew[a] += (not ok)
        if t >= T // 2: gp += rates[li] * ok; n2 += 1
    return gp / n2

def run_seed(seed, pj=5.0, d_j=25.0):
    rng = np.random.default_rng(2000 + seed)
    P, P0 = tables(rng, pj, d_j); rates = np.array([rate_f(f) for f in FEATS])
    order = np.argsort(-(rates * P0)); base = float((rates * P0)[order[0]])           # unjammed static best
    out = dict(base=base, clean={}, jam={}, oracle={})
    for n in (1, 2, 4, 8, 16):
        pol = order[:n]
        out["clean"][n] = float(np.mean(rates[pol] * P0[pol]) / base)
        out["jam"][n] = learn(rng, P, pol) / base
        # offline oracle jammer: best fixed arm against the uniform mixture (computed from the table, no learning)
        out["oracle"][n] = float(min(np.mean(rates[pol] * P[pol, a]) for a in range(F)) / base)
    return out

def power_sweep(seed, d_j=25.0):
    rng = np.random.default_rng(3000 + seed); rows = {}
    for pj in (-10.0, 0.0, 5.0, 10.0, 15.0, 20.0, 30.0):
        P, P0 = tables(rng, pj, d_j, nf=1500); rates = np.array([rate_f(f) for f in FEATS]); order = np.argsort(-(rates * P0)); base = (rates * P0)[order[0]]
        rows[pj] = {n: float(min(np.mean(rates[order[:n]] * P[order[:n], a]) for a in range(F)) / base) for n in (1, 4, 16)}
    return rows

def main(nseeds=20):
    rows = [run_seed(s) for s in range(nseeds)]
    print(f"E17 {nseeds} seeds. 16 configs; jammer 5 dBm at 25 m; goodput relative to the unjammed static link (1.0). clean = no jammer.")
    print("  n configs (H bits) | clean | learning-jammer goodput | offline-oracle jammer goodput")
    for n in (1, 2, 4, 8, 16):
        c = [r["clean"][n] for r in rows]; j = [r["jam"][n] for r in rows]; o = [r["oracle"][n] for r in rows]
        print(f"   {n:2d} ({np.log2(n):.0f})  | {fmt(c)} | {fmt(j)} | {fmt(o)}")
    ps = [power_sweep(s) for s in range(nseeds)]
    print("  oracle-jammer goodput vs jammer power at 25 m (static n=1 / n=4 / n=16):")
    for pj in ps[0]:
        print(f"   {pj:5.0f} dBm: " + " / ".join(fmt([p[pj][n] for p in ps], 2) for n in (1, 4, 16)))
    best_n = max((1, 2, 4, 8, 16), key=lambda n: np.mean([r["jam"][n] for r in rows]))
    m, h = paired_ci([r["jam"][best_n] for r in rows], [r["jam"][1] for r in rows])
    print(f"  best diversity under attack: n={best_n}; paired gain over static {m:+.3f} +/- {h:.3f}")
    key("goodput vs learning jammer, static (n=1) / n=4 / n=16", " / ".join(fmt([r["jam"][n] for r in rows]) for n in (1, 4, 16)))
    key("clean goodput cost of diversity n=16 vs static", fmt([r["clean"][16] for r in rows]))
    save_json("e17_moving.json", dict(rows=rows, power=[{str(k): v for k, v in p.items()} for p in ps]))
    fig, ax = plt.subplots(1, 2, figsize=(10.5, 3.8)); ns = (1, 2, 4, 8, 16)
    for lab, key_, c in (("clean", "clean", C["green"]), ("learning jammer", "jam", C["verm"]), ("oracle jammer", "oracle", C["blue"])):
        ms = [ci95([r[key_][n] for r in rows]) for n in ns]; ax[0].errorbar(np.log2(ns), [m[0] for m in ms], [m[1] for m in ms], marker="o", color=c, label=lab, capsize=2)
    ax[0].set_xlabel("diversity H = log2(n configs) bits"); ax[0].set_ylabel("goodput / unjammed static"); ax[0].legend()
    pjs = list(ps[0]); 
    for n, c in ((1, C["verm"]), (4, C["orange"]), (16, C["blue"])):
        ms = [ci95([p[pj][n] for p in ps]) for pj in pjs]; ax[1].errorbar(pjs, [m[0] for m in ms], [m[1] for m in ms], marker="o", color=c, label=f"n={n}", capsize=2)
    ax[1].set_xlabel("jammer power (dBm) at 25 m"); ax[1].set_ylabel("oracle-jammer goodput"); ax[1].legend()
    save_fig(fig, "e17_moving.png")

if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
