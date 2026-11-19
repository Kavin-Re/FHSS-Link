"""Experiment 2: fault injection in the hop FSM / counter / key register at link level, TMR vs parity+compare, GE cost,
and a SipHash-internal fault diffusion measurement (differential-fault NOTE, no key-recovery DFA implemented).
Writes results/exp2_fault.json and figures/fig2_fault.png."""
import json, time, numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from faultsim import *
from siphash import siphash24_u64
import ge_model, refsim

t0 = time.time()
N = 1500
R = {"trials_per_config": N, "H_slots": 256, "link": dict(M=13, kjam=1, p_jam=0.95, p_clean=0.01, beacon_period=32, loss_of_lock_L=3, watchdog_Lw=4)}
res = {}
for sc in SCHEMES:
    for (site, w) in SITES:
        res[f"{sc}|{site}|{w}"] = campaign(sc, site, w, N, seed=hash((sc, site, w)) % 2**31 if False else 1000 + 17 * SCHEMES.index(sc) + 3 * SITES.index((site, w)))
    print(sc, f"{time.time()-t0:.0f}s", flush=True)
R["campaign"] = res

# link_sim cross-check
ls = refsim.load("link_sim")
R["link_sim_importable"] = ls is not None
R["fault_free_pdr_siphash_engine"] = fault_free_pdr()
if ls is not None:
    R["fault_free_pdr_link_sim_lfsr"] = ls.run("static", slots=20000, hop=True, k=1)["pdr"]
    # link_sim has no hook for engine faults, so only its fault-free PDR and 'never resyncs' drift mode are used as references
    R["link_sim_never_resync_pdr_drift0.30"] = ls.run("static", slots=20000, hop=True, k=1, drift=0.30)["pdr"]

# GE cost
B, extra = ge_model.scheme_costs()
R["ge"] = {"baseline_total_GE": B, "extra_GE": extra, "overhead_pct": {k: 100 * v / B for k, v in extra.items()},
           "ff_cost_sensitivity_pct": {str(k): v for k, v in ge_model.sensitivity().items()},
           "breakdown": ge_model.engine_breakdown(), "cell_assumptions": ge_model.CELL}

# averaged over the 8 fault classes (equal weight), per scheme
agg = {}
for sc in SCHEMES:
    rows = [res[f"{sc}|{s}|{w}"] for s, w in SITES]
    agg[sc] = dict(mean_p_desync=float(np.mean([r["p_desync"] for r in rows])), mean_p_unrecovered=float(np.mean([r["p_unrecovered"] for r in rows])),
                   mean_excess_lost=float(np.mean([r["mean_excess_lost"] for r in rows])), mean_pdr=float(np.mean([r["pdr"] for r in rows])))
R["aggregate_equal_weight_over_8_fault_classes"] = agg

# ---- SipHash-internal fault diffusion (differential-fault note)
rng = np.random.default_rng(77)
n = 400
k0 = rng.integers(0, 2**63, n, dtype=np.uint64); k1 = rng.integers(0, 2**63, n, dtype=np.uint64); m = rng.integers(0, 2**63, n, dtype=np.uint64)
clean = siphash24_u64(k0, k1, m)
diff = {"round_index": list(range(8)), "mean_out_diff_hw": [], "frac_diff_hw_le_16": [], "p_hop_changes": []}
for r in range(8):
    hws, hop = [], []
    for word in range(4):
        for bit in rng.choice(64, 16, replace=False):
            f = siphash24_u64(k0, k1, m, fault=(r, word, 1 << int(bit)))
            hws.append(np.bitwise_count(f ^ clean).astype(float)); hop.append(((f % np.uint64(13)) != (clean % np.uint64(13))).astype(float))
    hws = np.concatenate(hws)
    diff["mean_out_diff_hw"].append(float(hws.mean())); diff["frac_diff_hw_le_16"].append(float((hws <= 16).mean()))
    diff["p_hop_changes"].append(float(np.concatenate(hop).mean()))
R["siphash_fault_diffusion"] = diff
print("diffusion", [round(x, 1) for x in diff["mean_out_diff_hw"]], flush=True)

# ---- figure
fig, ax = plt.subplots(2, 3, figsize=(16, 8.6))
labels = [f"{s}\nw={w}" for s, w in SITES]
cols = {"none_nowd": "#9aa5b1", "none": "#1b6ca8", "tmr": "#2a9d8f", "dcp": "#e9a23b"}
nm = {"none_nowd": "no protection, no watchdog", "none": "no protection (beacon+watchdog)", "tmr": "TMR (state)", "dcp": "dup+parity+compare"}
x = np.arange(len(SITES)); wd_ = 0.2
for j, key in enumerate(["p_desync", "mean_excess_lost", "mean_rec"]):
    a = ax.flat[j]
    for i, sc in enumerate(SCHEMES):
        a.bar(x + (i - 1.5) * wd_, [res[f"{sc}|{s}|{w}"][key] for s, w in SITES], wd_, color=cols[sc], label=nm[sc])
    a.set_xticks(x); a.set_xticklabels(labels, fontsize=8); a.grid(alpha=.3, axis="y")
ax[0, 0].set_title("P(state desync) after one fault event"); ax[0, 0].legend(fontsize=7)
ax[0, 1].set_title("extra packets lost in 256 slots (static jammer on 1 of 13 channels)")
ax[0, 2].set_title("mean desync duration (slots; 256 = never recovered)")
a = ax[1, 0]; names = list(extra.keys()); ov = [100 * extra[k] / B for k in names]
a.barh(names, ov, color=["#9aa5b1", "#2a9d8f", "#2a9d8f", "#e9a23b", "#e9a23b"]); a.set_xlabel("overhead vs baseline engine (%% of %.0f GE, proxy)" % B)
a.set_title("Gate-equivalent PROXY cost (not synthesis)"); a.grid(alpha=.3, axis="x")
for i, v in enumerate(ov): a.text(v + 2, i, f"{v:.0f}%", va="center", fontsize=8)
a = ax[1, 1]
for sc, gk in (("none", "baseline"), ("tmr", "TMR_state"), ("dcp", "DMR_parity_state")):
    a.scatter(100 * extra[gk] / B, agg[sc]["mean_excess_lost"], s=90, color=cols[sc], label=nm[sc])
a.set_xlabel("GE overhead (%)"); a.set_ylabel("mean extra lost packets per fault (8 classes, equal weight)"); a.set_title("Cost vs benefit (state-only schemes simulated)")
a.legend(fontsize=8); a.grid(alpha=.3)
a = ax[1, 2]
a.plot(diff["round_index"], diff["mean_out_diff_hw"], "o-", color="#c0392b", label="mean output diff Hamming weight (of 64)")
a.plot(diff["round_index"], [32] * 8, "--", color="gray", lw=.8)
a2 = a.twinx(); a2.plot(diff["round_index"], diff["frac_diff_hw_le_16"], "s:", color="#1b6ca8", label="fraction with diff HW <= 16")
a.set_xlabel("round (0..7) before which a 1-bit fault is injected into v0..v3"); a.set_ylabel("output difference HW"); a2.set_ylabel("fraction sparse diffs")
a.set_title("SipHash-2-4 internal single-bit fault diffusion"); a.set_ylim(0, 40); a.grid(alpha=.3)
h1, l1 = a.get_legend_handles_labels(); h2, l2 = a2.get_legend_handles_labels(); a.legend(h1 + h2, l1 + l2, fontsize=7, loc="center left")
fig.suptitle("SIMULATED fault injection on the keyed hop engine (abstract bit-flip model, RX side only)", fontsize=11)
fig.tight_layout(); fig.savefig("figures/fig2_fault.png", dpi=125)
R["runtime_s"] = time.time() - t0
json.dump(R, open("results/exp2_fault.json", "w"), indent=1)
print("done", f"{R['runtime_s']:.0f}s")
