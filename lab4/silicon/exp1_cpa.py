"""Experiment 1: simulated CPA on the SipHash hop engine, unmasked vs first-order masked. Writes results/exp1_cpa.json, figures/fig1_cpa.png.
All traces are SIMULATED from an assumed HW/HD leakage + Gaussian noise model. Seeds fixed."""
import json, time, numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sidechannel import *
from siphash import split_key, siphash24, MASK

t0 = time.time()
R = {"model": "HW leakage of v3 and v2+v3 bytes, Gaussian noise sigma (units: 1 sigma_HW_signal = 1.41)", "seed": 2026}
rng = np.random.default_rng(2026)
NS = [10, 20, 40, 80, 160, 320, 640, 1280, 2560]
SIGMAS = [0.5, 1.0, 2.0, 4.0]
TR = 12

# ---- A: unmasked success vs traces and noise
A = {}
for sg in SIGMAS:
    full = np.zeros(len(NS)); byt = np.zeros(len(NS))
    for t in range(TR):
        key = rng.bytes(16); k0, k1 = split_key(key)
        m = rand64(rng, NS[-1]); T = leak_unmasked(key, m, sg, rng)
        for i, n in enumerate(NS):
            e0, e1 = cpa_attack(T[:n], m[:n])
            h = byte_hits(e0, k0) + byte_hits(e1, k1)
            full[i] += (h == 16); byt[i] += h / 16
    A[str(sg)] = {"full_key_success": (full / TR).tolist(), "byte_success": (byt / TR).tolist()}
    print("A sigma", sg, [round(x, 2) for x in full / TR], f"{time.time()-t0:.0f}s", flush=True)
R["unmasked"] = {"N": NS, "sigmas": SIGMAS, "trials": TR, "by_sigma": A}
# traces needed for >=90% full-key success per sigma
need = {}
for sg in SIGMAS:
    ok = [n for n, s in zip(NS, A[str(sg)]["full_key_success"]) if s >= 0.9]
    need[str(sg)] = ok[0] if ok else None
R["unmasked"]["traces_for_90pct_full_key"] = need

# ---- A2: HD model on stage 2 (oracle k1) incl. MSB ambiguity
hd = {"N": [200, 800, 3200], "sigma": 1.0, "bytes_ok_except_msb": [], "after_msb_resolution": []}
for n in hd["N"]:
    ok = res = 0
    for t in range(10):
        key = rng.bytes(16); k0, k1 = split_key(key); m = rand64(rng, n)
        T = leak_unmasked(key, m, 1.0, rng, model2="HD")
        e0, _ = cpa_attack(T, m, model2="HD", k1_oracle=k1)
        ok += ((e0 ^ k0) & ~0x8080808080808080 & MASK) == 0
        msg = (777).to_bytes(8, "little")
        mk = lambda a, b: a.to_bytes(8, "little") + b.to_bytes(8, "little")
        res += resolve_msb_ambiguity(e0, k1, mk, msg, siphash24(key, msg)) == k0
    hd["bytes_ok_except_msb"].append(ok / 10); hd["after_msb_resolution"].append(res / 10)
R["hd_stage2"] = hd
print("HD", hd, flush=True)

# ---- B: masked, first order (stage 1 + stage 2 w/ oracle k1)
NB = [2000, 8000, 32000]
B = {"N": NB, "sigma": 1.0, "trials": 3, "stage1_byte_rate": [], "stage2_byte_rate_oracle_k1": []}
for n in NB:
    s1 = s2 = 0
    for t in range(3):
        key = rng.bytes(16); k0, k1 = split_key(key); m = rand64(rng, n)
        T = leak_masked(key, m, 1.0, rng)
        s1 += byte_hits(cpa_firstorder_masked(T, m, stage=1), k1) / 8
        if n <= 8000:
            s2 += byte_hits(cpa_firstorder_masked(T, m, k1_oracle=k1, stage=2), k0) / 8
    B["stage1_byte_rate"].append(s1 / 3); B["stage2_byte_rate_oracle_k1"].append(s2 / 3 if n <= 8000 else None)
B["chance_byte_rate"] = 1 / 256
R["masked_first_order"] = B
print("B", B, f"{time.time()-t0:.0f}s", flush=True)

# ---- C: second-order attack on masked stage 1
NC = [250, 500, 1000, 2000, 4000, 8000, 16000]
C = {"N": NC, "by_sigma": {}}
for sg in (0.5, 1.0, 2.0):
    r = []
    for n in NC:
        h = 0
        for t in range(6):
            key = rng.bytes(16); k0, k1 = split_key(key); m = rand64(rng, n)
            T = leak_masked(key, m, sg, rng)
            h += byte_hits(cpa_secondorder_masked(T, m), k1) / 8
        r.append(h / 6)
    C["by_sigma"][str(sg)] = r
    print("C", sg, [round(x, 2) for x in r], f"{time.time()-t0:.0f}s", flush=True)
R["masked_second_order"] = C

# ---- D: controls
key = rng.bytes(16); k0, k1 = split_key(key); m = rand64(rng, 3000)
Tz = leak_masked(key, m, 1.0, rng, mask_on=False)
Th = leak_masked(key, m, 1.0, rng, extra_hd=True)
R["controls"] = {
    "mask_disabled_r0_stage1_bytes_of_8": byte_hits(cpa_firstorder_masked(Tz, m, stage=1), k1),
    "share_overwrite_HD_leak_stage1_bytes_of_8_N3000": byte_hits(cpa_firstorder_masked(Th, m, stage=1), k1)}
print("D", R["controls"], flush=True)

# ---- E: TVLA fixed-vs-random Welch t (max |t| over 16 samples), 20000 traces each
n = 20000
fixed = np.full(n, 0x0123456789abcdef, dtype=np.uint64); rnd = rand64(rng, n)
tu = np.abs(welch_t(leak_unmasked(key, fixed, 1.0, rng), leak_unmasked(key, rnd, 1.0, rng))).max()
Tf, Tr = leak_masked(key, fixed, 1.0, rng), leak_masked(key, rnd, 1.0, rng)
tm1 = np.abs(welch_t(Tf, Tr)).max()
def cp(T):  # centred product of the two share samples, per byte-position
    return (T[:, 0, :] - 4.0) * (T[:, 1, :] - 4.0)
tm2 = np.abs(welch_t(cp(Tf), cp(Tr))).max()
R["tvla_max_abs_t"] = {"unmasked": float(tu), "masked_first_order": float(tm1), "masked_second_order_centred_product": float(tm2), "threshold": 4.5, "traces_per_set": n}
print("E", R["tvla_max_abs_t"], flush=True)

# ---- F: sequential counter (low bytes only vary)
n = 4000; key = rng.bytes(16); k0, k1 = split_key(key)
m = np.arange(n, dtype=np.uint64); T = leak_unmasked(key, m, 0.5, rng)
mb = bytes_of(m)
rec = [int(np.argmax(stage1_scores(T[:, b], mb, b))) == ((k1 >> 8 * b) & 255) for b in range(8)]
R["sequential_counter_0_to_3999_stage1_bytes_recovered"] = [bool(x) for x in rec]

# ---- G: correlation-vs-hypothesis illustration
key = rng.bytes(16); k0, k1 = split_key(key); m = rand64(rng, 400); T = leak_unmasked(key, m, 1.0, rng)
sc = stage1_scores(T[:, 0], bytes_of(m), 0); true_b = k1 & 255
R["illustration"] = {"N": 400, "sigma": 1.0, "true_corr": float(sc[true_b]), "best_wrong_corr": float(np.max(np.delete(sc, true_b)))}

# ---- figure
fig, ax = plt.subplots(1, 3, figsize=(15, 4.3))
cols = ["#1b6ca8", "#2a9d8f", "#e9a23b", "#c0392b"]
for c, sg in zip(cols, SIGMAS):
    ax[0].plot(NS, A[str(sg)]["full_key_success"], "o-", color=c, label=f"sigma={sg}")
ax[0].set_xscale("log"); ax[0].set_xlabel("number of traces"); ax[0].set_ylabel("full 128-bit key recovered (rate)")
ax[0].set_title("Unmasked: CPA success vs traces and noise"); ax[0].legend(); ax[0].grid(alpha=.3)
ax[1].plot(NS, A["1.0"]["byte_success"], "o-", color="#1b6ca8", label="unmasked, 1st-order CPA (16 bytes)")
ax[1].plot(NB, B["stage1_byte_rate"], "s-", color="#c0392b", label="masked, 1st-order CPA (k1 bytes)")
for sg, c, ls in ((0.5, "#7b3fa0", "--"), (1.0, "#e9a23b", "-"), (2.0, "#2a9d8f", ":")):
    ax[1].plot(NC, C["by_sigma"][str(sg)], "^" + ls, color=c, label=f"masked, 2nd-order CPA, sigma={sg}")
ax[1].axhline(1 / 256, color="gray", lw=.8); ax[1].text(12, 0.02, "chance 1/256", color="gray", fontsize=8)
ax[1].set_xscale("log"); ax[1].set_xlabel("number of traces"); ax[1].set_ylabel("fraction of key bytes recovered")
ax[1].set_title("Masking: 1st order fails, 2nd order succeeds (sigma=1 unless noted)"); ax[1].legend(fontsize=7); ax[1].grid(alpha=.3)
ax[2].bar(range(256), sc, color="#9aa5b1", width=1.0); ax[2].bar([true_b], [sc[true_b]], color="#c0392b", width=2.5)
ax[2].set_xlabel("key-byte hypothesis (k1 byte 0)"); ax[2].set_ylabel("Pearson correlation")
ax[2].set_title("400 traces, sigma=1: correct hypothesis in red"); ax[2].grid(alpha=.3)
fig.suptitle("SIMULATED power analysis of a SipHash-2-4 hop engine (assumed Hamming-weight leakage; no real device)", fontsize=10)
fig.tight_layout(); fig.savefig("figures/fig1_cpa.png", dpi=130)
R["runtime_s"] = time.time() - t0
json.dump(R, open("results/exp1_cpa.json", "w"), indent=1)
print("done", f"{R['runtime_s']:.0f}s")
