"""Generate Layer-1 figures and a results table. Run: python3 run_all.py"""
import os, json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from fhss_sim import (ber_awgn_theory, ber_tone_theory, ber_fh_theory,
                      ber_ds_theory, pdr_theory, simulate_ber)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figures")
os.makedirs(OUT, exist_ok=True)
NB = 200_000
res = {}

# 1. BER vs Eb/N0, no jammer
eb = np.arange(0, 11, 1.0)
mc = [simulate_ber("fixed", e, None, nbits=NB) for e in eb]
plt.figure(); plt.semilogy(eb, [ber_awgn_theory(e) for e in eb], "k-", label="theory")
plt.semilogy(eb, np.maximum(mc, 1e-6), "o", label="Monte Carlo")
plt.xlabel("Eb/N0 (dB)"); plt.ylabel("BER"); plt.grid(True, which="both", alpha=.3)
plt.title("BPSK over AWGN (sanity check)"); plt.legend()
plt.savefig(f"{OUT}/1_ber_awgn.png", dpi=130); plt.close()

# 2. BER vs JSR, Eb/N0 = 10 dB
jsr_db = np.arange(-10, 21, 2.0); E = 10.0
cfg = {"fixed": dict(), "FH M=8": dict(M=8, k=1), "FH M=32": dict(M=32, k=1),
       "DS Gp=16": dict(Gp=16), "DS Gp=64": dict(Gp=64)}
plt.figure(figsize=(7, 5)); rows = {}
for name, kw in cfg.items():
    sch = name.split()[0].lower().replace("fixed", "fixed")
    vals = [simulate_ber(sch, E, j, nbits=NB, **kw) for j in jsr_db]
    rows[name] = vals
    plt.semilogy(jsr_db, np.maximum(vals, 1e-6), "o-", ms=4, label=name)
plt.xlabel("JSR (dB)"); plt.ylabel("BER"); plt.ylim(1e-6, 1)
plt.title(f"BER vs tone-jammer strength (Eb/N0={E:.0f} dB)")
plt.grid(True, which="both", alpha=.3); plt.legend(fontsize=8)
plt.savefig(f"{OUT}/2_ber_vs_jsr.png", dpi=130); plt.close()
res["ber_vs_jsr"] = {"jsr_db": list(jsr_db), **{k: [float(x) for x in v] for k, v in rows.items()}}

# 3. FH: BER vs number of channels M (one interfered channel)
Ms = [1, 2, 4, 8, 16, 32, 64]
for jdb in (0, 10):
    mcv = [simulate_ber("fh" if M > 1 else "fixed", E, jdb, nbits=NB, M=M, k=1) for M in Ms]
    th = [ber_fh_theory(E, 10**(jdb/10), M, 1) for M in Ms]
    plt.figure(); plt.semilogy(Ms, th, "k-", label="theory"); plt.semilogy(Ms, np.maximum(mcv, 1e-6), "o", label="MC")
    plt.xscale("log", base=2); plt.xlabel("hop channels M"); plt.ylabel("BER")
    plt.title(f"FH: BER vs M, 1 jammed channel, JSR {jdb} dB"); plt.grid(True, which="both", alpha=.3); plt.legend()
    plt.savefig(f"{OUT}/3_fh_vs_M_jsr{jdb}.png", dpi=130); plt.close()
    res[f"fh_vs_M_jsr{jdb}"] = {"M": Ms, "mc": [float(x) for x in mcv], "theory": [float(x) for x in th]}

# 4. DS processing gain: BER vs Gp at JSR 10 dB, Eb/N0 6 dB
Gps = [1, 2, 4, 8, 16, 32, 64]
mcv = [simulate_ber("ds", 6.0, 10.0, nbits=NB, Gp=g) for g in Gps]
th = [ber_ds_theory(6.0, 10.0, g) for g in Gps]
plt.figure(); plt.semilogy(Gps, th, "k-", label="theory (Gaussian approx)")
plt.semilogy(Gps, np.maximum(mcv, 1e-6), "o", label="MC")
plt.xscale("log", base=2); plt.xlabel("processing gain Gp (chips/bit)"); plt.ylabel("BER")
plt.title("DS-SS: BER vs Gp (JSR 10 dB, Eb/N0 6 dB)"); plt.grid(True, which="both", alpha=.3); plt.legend()
plt.savefig(f"{OUT}/4_ds_vs_Gp.png", dpi=130); plt.close()
res["ds_vs_Gp"] = {"Gp": Gps, "mc": [float(x) for x in mcv], "theory": [float(x) for x in th]}

# 5. Packet delivery ratio vs M (256-bit packets)
plt.figure()
for jdb in (0, 10):
    plt.plot(Ms, [pdr_theory(E, 10**(jdb/10), M, 1, 256) for M in Ms], "o-", label=f"JSR {jdb} dB")
plt.xscale("log", base=2); plt.xlabel("hop channels M"); plt.ylabel("packet delivery ratio")
plt.title("FH packet delivery (model, 256-bit packets, no coding)"); plt.grid(True, alpha=.3); plt.legend()
plt.savefig(f"{OUT}/5_pdr_vs_M.png", dpi=130); plt.close()
res["pdr_vs_M"] = {"M": Ms, **{f"jsr{j}": [float(pdr_theory(E, 10**(j/10), M, 1, 256)) for M in Ms] for j in (0, 10)}}

json.dump(res, open(f"{OUT}/results.json", "w"), indent=1)
print("done")
