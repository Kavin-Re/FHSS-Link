"""R6 (RED_TEAM idea 10) Channel-manipulation attack on key-from-the-air. Own-link model (same family as sim/plkg.py, re-implemented, not imported).
A and B measure a reciprocal fading gain h plus independent noise: a=h+nA, b=h+nB. Normal environment: h ~ N(0, sf0^2), noise sigma = 0.5 sf0.
Implementation under test uses a FIXED threshold calibrated in the normal environment (bit = a > 0), as simple implementations do.
Attacker 'holds the environment still': fade std shrinks to alpha*sf0 and the mean is nudged by +shift*sf0 (e.g. by partial blocking).
Metrics: H(A bit), disagreement p between A and B, secret-bit rate ~ max(0, H(A) - Hb(p)) per sample (reconciliation leaks Hb(p)), and min-entropy
per bit for an attacker who guesses the likelier bit. Defence: online monitor that aborts if the estimated rate falls below R_MIN."""
import numpy as np
from _common import *
R_MIN = 0.15

def hb(p):
    p = np.clip(p, 1e-12, 1 - 1e-12); return float(-(p * np.log2(p) + (1 - p) * np.log2(1 - p)))

def measure(alpha, shift, N=100000, seed=0, sf0=1.0, sn=0.5):
    rng = np.random.default_rng(seed); h = shift * sf0 + alpha * sf0 * rng.normal(size=N)
    a = (h + sn * sf0 * rng.normal(size=N)) > 0; b = (h + sn * sf0 * rng.normal(size=N)) > 0
    p1 = a.mean(); H = hb(p1); pd = float((a != b).mean()); rate = max(0.0, H - hb(pd)); hmin = float(-np.log2(max(p1, 1 - p1)))
    return dict(H=H, pdis=pd, rate=rate, hmin=hmin, key128_bits=128 * hmin)

def monitor(alpha, shift, N=4096, seed=1):
    m = measure(alpha, shift, N, seed); return m["rate"] >= R_MIN        # True = accept key

ALPHAS = [1.0, 0.7, 0.5, 0.3, 0.2, 0.1, 0.05]
def main():
    res = {}
    print(f"{'alpha':>6s} | still only: {'H':>5s} {'pdis':>5s} {'rate':>5s} {'mon':>4s} | still+shift 0.3: {'H':>5s} {'pdis':>5s} {'rate':>5s} {'hmin':>5s} {'mon':>4s}")
    for al in ALPHAS:
        s1 = measure(al, 0.0); s2 = measure(al, 0.0 if al == 1.0 else 0.3)
        res[al] = dict(still=s1, shift=s2, mon_still=monitor(al, 0.0), mon_shift=monitor(al, 0.0 if al == 1.0 else 0.3))
        print(f"{al:6.2f} |             {s1['H']:5.2f} {s1['pdis']:5.2f} {s1['rate']:5.2f} {str(res[al]['mon_still']):>4s} |                  {s2['H']:5.2f} {s2['pdis']:5.2f} {s2['rate']:5.2f} {s2['hmin']:5.2f} {str(res[al]['mon_shift']):>4s}")
    fig, ax = plt.subplots(figsize=(6.2, 3.5))
    ax.plot(ALPHAS, [res[a]["still"]["rate"] for a in ALPHAS], "o-", color=C["blue"], label="environment held still")
    ax.plot(ALPHAS, [res[a]["shift"]["rate"] for a in ALPHAS], "s-", color=C["verm"], label="still + mean nudged by 0.3 sigma")
    ax.axhline(R_MIN, color=C["grey"], ls="--", label=f"monitor abort level {R_MIN}"); ax.invert_xaxis(); ax.set_xlabel("fade std relative to normal (alpha)"); ax.set_ylabel("secret bits per sample")
    ax.legend(); ax.set_title("R6 key-from-air entropy drain"); save_fig(fig, "r6_keyfromair_drain.png")
    save_json("r6_keyfromair_drain.json", {str(k): v for k, v in res.items()})
    key("alpha=0.1: secret bits/sample (still+shift) vs normal; min-entropy of a 128-bit key an attacker could guess", f"{res[0.1]['shift']['rate']:.3f} vs {res[1.0]['still']['rate']:.3f}; {res[0.1]['shift']['key128_bits']:.1f} of 128 bits")
    return res
if __name__ == "__main__": main()
