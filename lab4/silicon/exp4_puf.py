"""Experiment 4: ring-oscillator PUF (simulated) -> uniqueness, reliability, bit-aliasing; fuzzy extractor key regeneration failure.
Writes results/exp4_puf.json and figures/fig4_puf.png. All parameters are ASSUMED model values (see puf.py)."""
import json, time, numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from puf import *
from siphash import hop_channels

t0 = time.time()
rng = np.random.default_rng(404)
NCH, READS = 64, 20
R = {"n_chips": NCH, "ros_per_chip": 2048, "pairs_per_chip": 1024, "reads_per_condition": READS,
     "assumptions": {"sigma_proc": 1.0, "layout_gradient_span_sigma": 3.0, "read_noise_sigma": 0.05, "temp_coeff_sigma_per_C": 0.0025,
                     "hot_dT": 60, "cold_dT": -40, "enrol": "majority of 15 nominal reads"}}
puf = ROArray(NCH, grad=3.0, sigma_noise=0.05, rng=rng)
conds = {"nominal": 0.0, "hot_plus60C": 60.0, "cold_minus40C": -40.0}
M_ = {}; inter_all = {}; p_all = {}
for kind in ("far", "far_planefit", "neighbor"):
    ref = enrol_reference(puf, kind)
    reads = {c: np.stack([get_response(puf, kind, dT) for _ in range(READS)]) for c, dT in conds.items()}
    m, inter, p = metrics(ref, reads); M_[kind] = m; inter_all[kind] = inter; p_all[kind] = p
    print(kind, {k: round(v, 4) for k, v in m.items() if "uniq" in k or "alias" in k or "ber_" in k}, flush=True)
R["metrics"] = M_
R["ber_theory_nominal"] = ber_theory(0.05); R["ber_theory_hot"] = ber_theory(np.hypot(0.05, 0.0025 * 60 * 1.0))

# ---- fuzzy extractor: failure rate by code and condition (best pairing: neighbor)
kind = "neighbor"; ref = enrol_reference(puf, kind)
codes = [("no ECC (128 raw bits)", FuzzyExtractor("raw")), ("rep-5 majority", FuzzyExtractor("rep", R=5)),
         ("BCH(15,7,t=2) x19", FuzzyExtractor("bch")), ("rep-3 + BCH(15,7)", FuzzyExtractor("rep+bch", R=3))]
FE = {}
for name, fe in codes:
    helper, s = fe.enrol(ref, rng)
    row = {"raw_bits_used": fe.n_code, "secret_bits": fe.k_secret, "helper_bits": fe.n_code}
    for c, dT in conds.items():
        fails = trials = 0
        for _ in range(READS):
            s2 = fe.regenerate(get_response(puf, kind, dT), helper)
            f = ~(s2 == s).all(1); fails += int(f.sum()); trials += len(f)
        row[f"fail_{c}"] = fails / trials; row[f"trials_{c}"] = trials
    FE[name] = row; print(name, {k: v for k, v in row.items() if k.startswith("fail")}, flush=True)
R["fuzzy_extractor_by_condition"] = FE

# ---- failure vs noise sweep (BER axis), nominal temperature, bigger sample, own chips
sweep = {"sigma_noise": [0.05, 0.1, 0.15, 0.2, 0.3], "ber_measured": [], "fail": {n: [] for n, _ in codes}, "trials": []}
for sn in sweep["sigma_noise"]:
    pf = ROArray(64, grad=3.0, sigma_noise=sn, rng=rng)
    rf = enrol_reference(pf, kind); bers = []; tr = 0; fl = {n: 0 for n, _ in codes}
    helpers = {n: fe.enrol(rf, rng) for n, fe in codes}
    for _ in range(40):
        resp = get_response(pf, kind); bers.append((resp != rf).mean()); tr += 64
        for n, fe in codes:
            h, s = helpers[n]; fl[n] += int((~(fe.regenerate(resp, h) == s).all(1)).sum())
    sweep["ber_measured"].append(float(np.mean(bers))); sweep["trials"].append(tr)
    for n, _ in codes: sweep["fail"][n].append(fl[n] / tr)
    print("sweep", sn, round(sweep["ber_measured"][-1], 4), {n: round(sweep["fail"][n][-1], 4) for n, _ in codes}, flush=True)
R["noise_sweep"] = sweep

# ---- end-to-end: PUF -> key -> hop sequence, hot corner, all chips
fe = FuzzyExtractor("rep+bch", R=3); helper, s = fe.enrol(ref, rng)
ok = 0; tot = 0
for dT in (0.0, 60.0, -40.0):
    for _ in range(5):
        s2 = fe.regenerate(get_response(puf, kind, dT), helper)
        for i in range(NCH):
            tot += 1
            ok += np.array_equal(hop_channels(FuzzyExtractor.key_from_secret(s[i]), np.arange(100)), hop_channels(FuzzyExtractor.key_from_secret(s2[i]), np.arange(100)))
R["end_to_end_hop_schedule_match"] = {"matches": ok, "total": tot}
R["key_uniqueness_distinct_keys_of_64"] = len({FuzzyExtractor.key_from_secret(x) for x in s})
nused = fe.n_code
R["helper_data_leakage_note"] = {"response_bits_used": nused, "secret_bits": fe.k_secret, "redundancy_bits_n_minus_k": nused - fe.k_secret,
    "empirical_entropy_deficit_bits_upper_bound_on_response": float(nused - M_["neighbor"]["entropy_sum_indep_upper_bound_bits"] * nused / M_["neighbor"]["n_bits"])}
print("e2e", R["end_to_end_hop_schedule_match"], flush=True)

# ---- figure
fig, ax = plt.subplots(1, 4, figsize=(18, 4.3))
cl = {"far": "#c0392b", "far_planefit": "#2a9d8f", "neighbor": "#1b6ca8"}
for k, c in cl.items():
    ax[0].hist(inter_all[k], bins=40, alpha=.55, color=c, label=f"{k} (mean {100*M_[k]['uniqueness_mean']:.1f}%)")
ax[0].axvline(0.5, color="k", ls=":"); ax[0].set_xlabel("inter-chip Hamming distance (fraction)"); ax[0].set_title("Uniqueness (64 chips, 2016 pairs)"); ax[0].legend(fontsize=7)
for k, c in cl.items():
    ax[1].hist(p_all[k], bins=40, range=(0, 1), alpha=.55, color=c, label=f"{k}: mean|p-0.5|={M_[k]['bit_aliasing_mean_abs_dev']:.2f}")
ax[1].set_xlabel("P(bit=1) across chips, per bit position"); ax[1].set_title("Bit aliasing (ideal: all at 0.5)"); ax[1].legend(fontsize=7)
names = list(conds); bars = [100 * (1 - M_["neighbor"][f"ber_{c}_mean"]) for c in names]
ax[2].bar(names, bars, color=["#1b6ca8", "#e9a23b", "#7b3fa0"]); ax[2].set_ylim(90, 100); ax[2].set_ylabel("reliability (% bits unchanged vs enrolment)")
for i, v in enumerate(bars): ax[2].text(i, v + .1, f"{v:.1f}%", ha="center")
ax[2].set_title("Reliability, neighbour pairing")
for (n, _), c, mk in zip(codes, ["#9aa5b1", "#e9a23b", "#7b3fa0", "#2a9d8f"], "osv^"):
    y = np.array(sweep["fail"][n]); y = np.where(y == 0, np.nan, y)
    ax[3].plot(100 * np.array(sweep["ber_measured"]), y, mk + "-", color=c, label=n)
ax[3].axhline(1 / sweep["trials"][0], color="gray", ls=":", lw=.8); ax[3].text(1, 1.3 / sweep["trials"][0], "1/N floor (0 failures below)", fontsize=7, color="gray")
ax[3].set_yscale("log"); ax[3].set_xlabel("raw bit error rate vs enrolment (%)"); ax[3].set_ylabel("128-bit key regeneration failure"); ax[3].set_title("Fuzzy extractor"); ax[3].legend(fontsize=7); ax[3].grid(alpha=.3, which="both")
fig.suptitle("SIMULATED ring-oscillator PUF and code-offset fuzzy extractor (assumed process/noise model)", fontsize=10)
fig.tight_layout(); fig.savefig("figures/fig4_puf.png", dpi=125)
R["runtime_s"] = time.time() - t0
json.dump(R, open("results/exp4_puf.json", "w"), indent=1, default=float)
print("done", f"{R['runtime_s']:.0f}s")
