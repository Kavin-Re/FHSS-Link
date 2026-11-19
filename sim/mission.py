"""Idea 24: mission scenario. A patrol node walks from the base at (0,0) to (120,0) m along a road; a fixed interferer on our own test range stands at (70,25).
Log-distance path loss; packet = 256 bits. Compare packet delivery along the path for: fixed channel (jammed channel), FH (13 ch, interferer covers k=2 channels),
DS-SS (Gp=32). Also: the distance range with delivery >= 0.8."""
import numpy as np
from fhss_sim import ber_tone_theory, ber_ds_theory, ber_awgn_theory, pdr_theory

def snr_jsr(x, jam=(70, 25), n=2.7, tx_dbm=0, noise_dbm=-98, jam_dbm=-5):
    d = max(abs(x), 1.0); dj = max(np.hypot(x - jam[0], jam[1]), 1.0)
    s = tx_dbm - 40 - 10 * n * np.log10(d); j = jam_dbm - 40 - 10 * n * np.log10(dj)
    return s - noise_dbm, 10 ** ((j - s) / 10)

def pdr(ber, L=256): return float((1 - min(max(ber, 0), 0.5)) ** L)

def curves(xs):
    out = {"fixed": [], "FH 13ch, k=2": [], "DS Gp=32": [], "no interferer": []}
    for x in xs:
        e, j = snr_jsr(x)
        out["fixed"].append(pdr(ber_tone_theory(e, j)))
        out["FH 13ch, k=2"].append(float(pdr_theory(e, j, 13, 2, 256)))   # packet-level: a packet sits on one channel
        out["DS Gp=32"].append(pdr(ber_ds_theory(e, j, 32)))
        out["no interferer"].append(pdr(ber_awgn_theory(e)))
    return out

if __name__ == "__main__":
    import json, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    xs = np.arange(5, 121, 1.0); c = curves(xs); res = {}
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    for k, v in c.items(): ax[1].plot(xs, v, label=k)
    ax[0].plot(0, 0, "ks", label="base"); ax[0].plot(70, 25, "r^", label="interferer"); ax[0].plot(xs, 0 * xs, "b-", alpha=.4, label="patrol path"); ax[0].set_aspect("equal"); ax[0].legend(); ax[0].set_title("Scenario (m)")
    ax[1].set_xlabel("distance from base along path (m)"); ax[1].set_ylabel("packet delivery (256 bits)"); ax[1].legend(fontsize=8); ax[1].grid(alpha=.3); ax[1].set_title("Delivery along the patrol path")
    plt.tight_layout(); plt.savefig("figures/13_mission.png", dpi=130); plt.close()
    print("delivery at selected positions"); 
    for x in (20, 50, 70, 90, 110):
        i = int(x - 5); print(f"x={x:3d} m:", {k: round(v[i], 3) for k, v in c.items()})
    for k, v in c.items():
        good = [x for x, p in zip(xs, v) if p >= 0.8]; res[k] = dict(first_below_0_8=float(next((x for x, p in zip(xs, v) if p < 0.9), -1)), fraction_of_path_ok=len(good) / len(xs))
        print(f"{k:14s} fraction of path with delivery >= 0.8: {len(good)/len(xs):.2f}")
    json.dump(res, open("figures/mission.json", "w"), indent=1)
