#!/usr/bin/env python3
"""BER vs Eb/N0 of the ladder-driven correlator model (Monte Carlo, numpy) for N = 16/32/64, exact vs approximate adder trees.
Writes results/ber_vs_snr.csv, results/ber_vs_snr.txt (+ png when matplotlib exists).  Pure simulation of the bit-exact tree model; no hardware.
Bias compensation (COMP) is calibrated per configuration on an independent seed at 4 dB (mean of approx - exact output) and is the constant used in the RTL parameter COMP."""
import os, sys, csv, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from corr_model import *
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results"); os.makedirs(OUT, exist_ok=True)
W = 6; NB = int(os.environ.get("NBITS", 200000)); CH = 50000
SNRS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
CONFIGS = [("exact", 0, 0)] + [(f"{ATYPES[a]}{k}", a, k) for a in (1, 2, 3) for k in (1, 2, 3, 4)]

def calib(N, a, k, seed=999, B=40000, snr=4.0):
    rng = np.random.default_rng(seed); _, code, q = make_frames(rng, B, N, W, snr)
    d = corr(code, q, W, a, k) - corr(code, q, W, 0, 0)
    return int(np.rint(-d.mean())), float(d.mean()), float(d.std())

def main():
    calibs = {}; plan = {}                                   # plan[N] = list of (variant name, atype, K, comp)
    for N in (16, 32, 64):
        plan[N] = []
        for name, a, k in CONFIGS:
            plan[N].append((name, a, k, 0))
            if a: comp, mean, sd = calib(N, a, k); calibs[f"N{N}_{name}"] = dict(comp=comp, mean_err=mean, sd_err=sd); plan[N].append((name + "+comp", a, k, comp))
    rows = []
    for N in (16, 32, 64):
        for snr in SNRS:
            errs = {v[0]: 0 for v in plan[N]}; tot = 0
            for s in range(0, NB, CH):
                B = min(CH, NB - s); rng = np.random.default_rng(7 * 1000003 + s)              # common random numbers across configs
                b, code, q = make_frames(rng, B, N, W, snr); tot += B
                t, nneg = leaves(code, q, W)
                for vname, a, k, comp in plan[N]:
                    T = tree_sum(t, W, a, k, False)
                    S = wrap_signed(T + nneg - (N << (W - 1)) + (comp if a else 0), sw_of(N, W))
                    errs[vname] += int((np.where(S >= 0, 1, -1) != b).sum())
            for vname, a, k, comp in plan[N]:
                rows.append(dict(N=N, config=vname, ebn0_db=snr, comp=comp, errors=errs[vname], bits=tot, ber=errs[vname] / tot))
        print("N =", N, "done", flush=True)
    with open(f"{OUT}/ber_vs_snr.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    json.dump(calibs, open(f"{OUT}/ber_calibration.json", "w"), indent=1)
    # text table: BER at selected SNR, ratio to exact; only points with >= 30 errors are shown as numbers (else '<' bound)
    L = [f"BER vs Eb/N0, DS-SS BPSK, AWGN, {W}-bit ADC (step {STEP}), random +-1 code per bit, {NB} bits per point, common random numbers",
         "ratio = BER / BER(exact) at the same SNR; '*' marks points with fewer than 30 errors (statistically weak)", ""]
    idx = {(r["N"], r["config"], r["ebn0_db"]): r for r in rows}
    for N in (16, 32, 64):
        L.append(f"N = {N}")
        names = [("exact",)] + [(n, ) for n, _, _ in CONFIGS[1:]] 
        cfgs = ["exact"] + [x for n, a, k in CONFIGS[1:] for x in (n, n + "+comp")]
        L.append("config".ljust(14) + "".join(f"{s:>12d}dB" for s in (2, 4, 6, 8, 10)))
        for cn in cfgs:
            line = cn.ljust(14)
            for s in (2, 4, 6, 8, 10):
                r = idx[(N, cn, s)]; e = idx[(N, "exact", s)]
                star = "*" if r["errors"] < 30 else " "
                rat = (r["ber"] / e["ber"]) if e["ber"] > 0 else float("nan")
                line += f"{r['ber']:>10.2e}{star}{rat:>5.2f}x"
            L.append(line)
        L.append("")
    L.append("bias calibration (mean of approx-minus-exact output at 4 dB, independent seed; comp = -round(mean)):")
    for k, v in calibs.items(): L.append(f"  {k}: mean_err={v['mean_err']:.2f} sd={v['sd_err']:.2f} comp={v['comp']}")
    open(f"{OUT}/ber_vs_snr.txt", "w").write("\n".join(L) + "\n"); print("\n".join(L))
    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        fig, ax = plt.subplots(1, 3, figsize=(15, 4.5), sharey=True)
        for i, N in enumerate((16, 32, 64)):
            for cn in ["exact", "LOA2", "LOA2+comp", "TRUNC2", "TRUNC2+comp", "ETA2", "ETA2+comp", "LOA3+comp"]:
                xs = [s for s in SNRS if idx[(N, cn, s)]["errors"] >= 10]
                ax[i].semilogy(xs, [idx[(N, cn, s)]["ber"] for s in xs], marker="o", ms=3, label=cn)
            ax[i].set_title(f"N={N}"); ax[i].set_xlabel("Eb/N0 [dB]"); ax[i].grid(True, which="both", alpha=.3)
        ax[0].set_ylabel("BER"); ax[0].legend(fontsize=7); plt.tight_layout(); plt.savefig(f"{OUT}/ber_vs_snr.png", dpi=120)
    except Exception as ex:
        print("plot skipped:", ex)
if __name__ == "__main__":
    main()
