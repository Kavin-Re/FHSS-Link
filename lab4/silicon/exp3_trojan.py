"""Experiment 3: detection delay of a trigger-counter trojan vs bias strength. Writes results/exp3_trojan.json, figures/fig3_trojan.png.
Monte Carlo uses multinomial window counts (equivalent to iid uniform hops = ideal PRF); a cross-check runs the same detectors on the
real SipHash trojan engine. Delay = hops from the trigger slot to the end of the window in which the alarm fires."""
import json, time, numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from trojan import *
from siphash import split_key
import ge_model, refsim

t0 = time.time()
rng = np.random.default_rng(303)
W, df = 256, 12
BETA_D = 0.03                                   # design bias of the CUSUM
lam_d = W * BETA_D ** 2 * (M - 1)               # noncentrality for a stuck-channel bias
K = df + lam_d / 2
CAP = 8000                                      # max windows observed after trigger
PRE = 40                                        # clean windows before trigger (CUSUM warm-up)
R = {"W": W, "M": M, "cusum_design_beta": BETA_D, "cusum_k": K, "cap_windows": CAP, "pre_windows": PRE}

# ---- calibrate CUSUM h: P(false alarm within 5000 clean windows) = 5 %
runs, nwin = 1000, 5000
S = np.zeros(runs); mx = np.zeros(runs); p0 = [1 / M] * M
for t in range(nwin):
    X = chi2_stat(rng.multinomial(W, p0, size=runs), W)
    S = np.maximum(0, S + X - K); mx = np.maximum(mx, S)
H_THR = float(np.quantile(mx, 0.95))
ALPHA_W = 1 - (1 - 0.05) ** (1 / 5000)
C_THR = chi2_threshold(ALPHA_W)
R.update(cusum_h=H_THR, single_window_alpha=ALPHA_W, single_window_threshold=C_THR,
         false_alarm_design="5 % probability of any alarm in 5000 clean windows (1.28M hops) for each detector")
print("calibrated h", round(H_THR, 1), "c", round(C_THR, 1), f"{time.time()-t0:.0f}s", flush=True)

# empirical FAR check on fresh clean data (CUSUM and single window)
runs2 = 1000; S = np.zeros(runs2); alarm_c = np.zeros(runs2, bool); alarm_w = np.zeros(runs2, bool)
for t in range(nwin):
    X = chi2_stat(rng.multinomial(W, p0, size=runs2), W)
    S = np.maximum(0, S + X - K); alarm_c |= S >= H_THR; alarm_w |= X >= C_THR
R["empirical_false_alarm_5000_windows"] = {"cusum": float(alarm_c.mean()), "single_window": float(alarm_w.mean())}
print("FAR check", R["empirical_false_alarm_5000_windows"], flush=True)

# ---- delay vs beta (MC)
BK = [3, 5, 8, 13, 26, 51, 102]
RUNS = 300
out = {}
for mode in ("stuck", "narrow"):
    rows = []
    for bk in BK:
        beta = bk / 256
        p1 = bias_pmf(beta, mode)
        trig_frac = rng.random(RUNS)              # fraction of the trigger window that is clean
        S = np.zeros(RUNS); firstc = -np.ones(RUNS, int); firstw = -np.ones(RUNS, int); pre_alarm = np.zeros(RUNS, bool)
        for t in range(PRE + CAP):
            if t < PRE: P = np.tile(p0, (RUNS, 1))
            elif t == PRE: P = np.outer(trig_frac, p0) + np.outer(1 - trig_frac, p1)
            else: P = np.tile(p1, (RUNS, 1))
            if t == PRE: cnt = np.stack([rng.multinomial(W, P[i]) for i in range(RUNS)])
            else: cnt = rng.multinomial(W, P[0], size=RUNS)
            X = chi2_stat(cnt, W)
            S = np.maximum(0, S + X - K)
            if t < PRE:
                pre_alarm |= (S >= H_THR) | (X >= C_THR)
            else:
                nc = (S >= H_THR) & (firstc < 0); firstc[nc] = t
                nw = (X >= C_THR) & (firstw < 0); firstw[nw] = t
            if t > PRE and (firstc >= 0).all() and (firstw >= 0).all(): break
        def delays(first):
            ok = (first >= 0) & ~pre_alarm
            d = (first[ok] - PRE + 1 - trig_frac[ok]) * W      # end of alarm window minus trigger position (offset trig_frac*W in window PRE)
            return d, ok.mean()
        dc, pc = delays(firstc); dw, pw = delays(firstw)
        row = {"beta": beta, "beta_k": bk,
               "cusum": {"p_detect": float(pc), "median_delay_hops": float(np.median(dc)) if len(dc) else None,
                         "p10": float(np.percentile(dc, 10)) if len(dc) else None, "p90": float(np.percentile(dc, 90)) if len(dc) else None},
               "single_window": {"p_detect": float(pw), "median_delay_hops": float(np.median(dw)) if len(dw) else None,
                                 "p10": float(np.percentile(dw, 10)) if len(dw) else None, "p90": float(np.percentile(dw, 90)) if len(dw) else None},
               "pre_trigger_false_alarm_runs": float(pre_alarm.mean())}
        rows.append(row)
        print(mode, bk, round(beta, 3), "cusum", row["cusum"]["p_detect"], row["cusum"]["median_delay_hops"], "win", row["single_window"]["p_detect"], f"{time.time()-t0:.0f}s", flush=True)
    out[mode] = rows
R["delay_mc"] = out

# ---- golden-reference detector on the REAL SipHash engine (first mismatch vs expected hop)
gold = {}
for mode in ("stuck", "narrow"):
    rows = []
    for bk in BK:
        ds = []
        for r in range(100):
            k = split_key(rng.bytes(16))
            eng = TrojanEngine(k, trigger=0, beta_k=bk, mode=mode)
            a, b = HopEngine(k).hops(0, 6000), eng.hops(0, 6000)
            mism = np.flatnonzero(a != b)
            ds.append(mism[0] + 1 if len(mism) else np.nan)
        ds = np.array(ds)
        rows.append({"beta_k": bk, "median_delay_slots": float(np.nanmedian(ds)), "p90": float(np.nanpercentile(ds, 90)), "p_detect_6000": float(np.mean(~np.isnan(ds)))})
    gold[mode] = rows
R["golden_reference"] = gold
print("golden", [round(r["median_delay_slots"]) for r in gold["stuck"]], flush=True)

# ---- real-engine cross-check of the blind detectors (stuck mode)
real = {}
for bk in (26, 51):
    dl_c, dl_w = [], []
    for r in range(12):
        k = split_key(rng.bytes(16)); trig = PRE * W + int(rng.integers(W))
        eng = TrojanEngine(k, trigger=trig, beta_k=bk, mode="stuck")
        nW = PRE + 600
        h = eng.hops(0, nW * W); X = chi2_stat(window_counts(h, W), W)
        fc, _ = cusum_run(X, K, H_THR); fw = np.flatnonzero(X >= C_THR)
        if fc[0] >= 0 and fc[0] >= PRE: dl_c.append((fc[0] + 1) * W - trig)
        if len(fw) and fw[0] >= PRE: dl_w.append((fw[0] + 1) * W - trig)
    real[str(bk)] = {"cusum_median_delay_hops": float(np.median(dl_c)) if dl_c else None, "n_cusum": len(dl_c),
                     "single_window_median_delay_hops": float(np.median(dl_w)) if dl_w else None, "n_single": len(dl_w)}
R["real_siphash_crosscheck"] = real
print("real", real, flush=True)

# ---- randtests (existing repo suite) on post-trigger real stream
rt = refsim.load("randtests"); R["randtests_importable"] = rt is not None
if rt is not None:
    k = split_key(bytes(range(16))); rr = {}
    for name, h in (("clean", HopEngine(k).hops(0, 20000)),
                    ("trojan_beta0.10_stuck", TrojanEngine(k, 0, 26).hops(0, 20000)),
                    ("trojan_beta0.02_stuck", TrojanEngine(k, 0, 5).hops(0, 20000)),
                    ("trojan_beta0.40_narrow", TrojanEngine(k, 0, 102, mode="narrow").hops(0, 20000))):
        rr[name] = rt.tests(h, 13)
    R["randtests_20000_hops"] = rr
    print("randtests", {k_: (v["chi_p"], v["predictor_acc"]) for k_, v in rr.items()}, flush=True)

# ---- stealth check
T = 100000; k = split_key(bytes(range(16)))
R["stealth_pre_trigger_identical_hops"] = bool(np.array_equal(HopEngine(k).hops(0, T), TrojanEngine(k, trigger=T + 1, beta_k=255).hops(0, T)))
R["trojan_cost_GE"] = ge_model.trojan_gate_cost(); R["trojan_cost_pct_of_engine"] = 100 * R["trojan_cost_GE"] / ge_model.scheme_costs()[0]

# ---- figure (CUSUM trajectory example)
beta_ex = 26 / 256; Xs = np.concatenate([rng.multinomial(W, p0, size=PRE), rng.multinomial(W, bias_pmf(beta_ex), size=400)])
fx, path = cusum_run(chi2_stat(Xs, W), K, H_THR)
fig, ax = plt.subplots(1, 3, figsize=(16, 4.4))
for a, mode in zip(ax[:2], ("stuck", "narrow")):
    rows = out[mode]; b = [r["beta"] for r in rows]
    for key, c, lab in (("cusum", "#1b6ca8", "CUSUM (blind)"), ("single_window", "#e9a23b", "single window chi-square (blind)")):
        ok = [r[key]["median_delay_hops"] is not None for r in rows]
        bb = [r["beta"] for r, o in zip(rows, ok) if o]
        med = [r[key]["median_delay_hops"] for r, o in zip(rows, ok) if o]
        lo = [r[key]["p10"] for r, o in zip(rows, ok) if o]; hi = [r[key]["p90"] for r, o in zip(rows, ok) if o]
        pd = [r[key]["p_detect"] for r, o in zip(rows, ok) if o]
        a.plot(bb, med, "o-", color=c, label=lab); a.fill_between(bb, lo, hi, color=c, alpha=.15)
        for x_, y_, p_ in zip(bb, med, pd):
            if p_ < 0.9: a.annotate(f"{p_:.0%} det", (x_, y_), fontsize=6, color=c)
    g = gold[mode]; a.plot(b, [r["median_delay_slots"] for r in g], "s--", color="#2a9d8f", label="golden reference (needs key)")
    a.set_xscale("log"); a.set_yscale("log"); a.set_xlabel("bias beta (fraction of hops overwritten)"); a.set_ylabel("detection delay after trigger (hops)")
    a.set_title(f"trojan mode '{mode}'"); a.grid(alpha=.3, which="both"); a.legend(fontsize=7)
a = ax[2]; a.plot(path[0], color="#1b6ca8"); a.axhline(H_THR, color="#c0392b", ls="--", label="alarm threshold h"); a.axvline(PRE, color="gray", ls=":", label="trigger")
a.set_xlabel("window index (256 hops each)"); a.set_ylabel("CUSUM statistic"); a.set_title(f"example run, beta={beta_ex:.2f}, 'stuck'"); a.legend(fontsize=8); a.grid(alpha=.3)
fig.suptitle("SIMULATED trigger-counter trojan: blind statistical detection (FAR set to 5% per 1.28M clean hops)", fontsize=10)
fig.tight_layout(); fig.savefig("figures/fig3_trojan.png", dpi=125)
R["runtime_s"] = time.time() - t0
json.dump(R, open("results/exp3_trojan.json", "w"), indent=1, default=float)
print("done", f"{R['runtime_s']:.0f}s")
