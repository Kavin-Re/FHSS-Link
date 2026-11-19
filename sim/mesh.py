"""Idea 19: relay and self-healing route under jamming. Nodes A (source) at (0,0), B (sink) at (30,0), R (relay) at (15,10). Jammer on our own test link at (jx, 4).
Each link is a hopping link: packet delivery from fhss_sim (Layer 1) with Eb/N0 from log-distance path loss and JSR at the receiver. The jammer is wideband: it covers k=8 of 13 channels with its power split equally (a single-channel jammer costs every link only 1/M, wherever it stands, so routing would not matter).
Routing: direct A-B, relay A-R-B, or adaptive (pick the lower expected transmissions, ETX = sum over hops of 1/PDR, using probe estimates)."""
import numpy as np
from fhss_sim import pdr_theory

def link_pdr(tx, rx, jam, jam_pow_db=-12.0, M=13, k=8, n=2.7, tx_dbm=0, noise_dbm=-95, L=128):
    d = max(np.linalg.norm(np.array(tx) - np.array(rx)), 1.0); dj = max(np.linalg.norm(np.array(jam) - np.array(rx)), 1.0)
    s_dbm = tx_dbm - 10 * n * np.log10(d) - 40; j_dbm = tx_dbm + jam_pow_db - 10 * n * np.log10(dj) - 40
    ebn0 = s_dbm - noise_dbm      # simple link budget: Eb/N0 about 15 dB on the 30 m direct link
    jsr = 10 ** ((j_dbm - s_dbm) / 10)
    return float(pdr_theory(ebn0, jsr, M, k, L))

if __name__ == "__main__":
    import json; A, B, R = (0, 0), (30, 0), (15, 10); res = []
    print("jammer x | PDR A-B | PDR A-R | PDR R-B | goodput direct | goodput relay | route picked | goodput picked")
    for jx in (0, 8, 15, 22, 28, 34):
        jam = (jx, 4); ab = link_pdr(A, B, jam); ar = link_pdr(A, R, jam); rb = link_pdr(R, B, jam)
        gd = ab; gr = 1 / (1 / max(ar, 1e-3) + 1 / max(rb, 1e-3))      # goodput = 1/ETX (relay needs two slots per delivered packet)
        pick = "direct" if gd >= gr else "relay"; res.append(dict(jx=jx, ab=ab, ar=ar, rb=rb, direct=gd, relay=gr, pick=pick, picked=max(gd, gr)))
        print(f"{jx:8d} | {ab:.3f} | {ar:.3f} | {rb:.3f} | {gd:.3f} | {gr:.3f} | {pick:6s} | {max(gd, gr):.3f}")
    json.dump(res, open("figures/mesh.json", "w"), indent=1)
