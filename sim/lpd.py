"""Idea 16: low probability of detection. An eavesdropper runs an energy detector (radiometer) on N samples; false alarm Pfa = 1%.
Our signal power P is fixed. Total band = M channels. Required total-band SNR for detection probability 0.9, N = 1000 samples (Gaussian approx; MC check).
Cases: (a) fixed channel seen by an eavesdropper tuned to it, (b) FH seen by a one-channel scanner, (c) FH or DS-SS seen by a wideband radiometer,
(d) DS-SS seen by a one-channel scanner (PSD flat across the band: 1/M of the power and 1/M of the noise, so no change). Note: FH on a one-channel scanner is present only 1/M of the time, so a single window cannot reach Pd 0.9 at any SNR."""
import numpy as np
from math import sqrt, erfc, log10

def Q(x): return 0.5 * erfc(x / sqrt(2))
def Qinv(p):
    lo, hi = -10.0, 10.0
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if Q(mid) > p else (lo, mid)
    return (lo + hi) / 2

def pd(snr, N, pfa=0.01):
    lam = 1 + Qinv(pfa) / sqrt(N); return Q((lam - (1 + snr)) / ((1 + snr) / sqrt(N)))

def need_snr_db(N, target=0.9, duty=1.0):
    lo, hi = 1e-6, 1e3
    for _ in range(80):
        mid = sqrt(lo * hi); p = duty * pd(mid, N) + (1 - duty) * 0.01
        lo, hi = (mid, hi) if p < target else (lo, mid)
    return 10 * log10(hi)

def mc_pd(snr, N, trials=20000, seed=0):
    rng = np.random.default_rng(seed); thr = 1 + Qinv(0.01) / sqrt(N)
    x = rng.normal(size=(trials, N)) * np.sqrt(1 + snr); return float(((x ** 2).mean(1) > thr).mean())

if __name__ == "__main__":
    import json; res = {}
    N, M = 1000, 13; off = 10 * log10(M)
    base = need_snr_db(N)
    rows = {"fixed channel, eavesdropper tuned to it": base - off,
            "FH, wideband radiometer": base,
            "DS-SS, wideband radiometer": base,
            "DS-SS, one-channel scanner (gets 1/M of power and 1/M of noise)": base}
    # FH seen by a one-channel scanner: present only 1/M of the time, so one window cannot reach Pd 0.9 at any SNR; needs about M windows
    print(f"Total-band SNR (dB) our signal needs for the eavesdropper to detect it with probability 0.9 (N={N}, Pfa=1%, M={M}); higher = harder to detect")
    for k, v in rows.items(): res[k] = v; print(f"{v:8.2f}  {k}")
    print("Gaussian check vs Monte Carlo: Pd at snr=-12 dB, N=1000:", round(pd(10 ** -1.2, 1000), 3), "vs", round(mc_pd(10 ** -1.2, 1000), 3))
    # sample-count wall: how many samples does the radiometer need at total-band SNR -10 dB?
    for Nn in (100, 1000, 10000, 100000):
        print(f"N={Nn:6d}: SNR needed {need_snr_db(Nn):6.2f} dB"); res[f"N{Nn}"] = need_snr_db(Nn)
    json.dump(res, open("figures/lpd.json", "w"), indent=1)
