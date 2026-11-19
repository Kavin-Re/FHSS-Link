"""Experiment 3 - relay ('convolution'-style) attacker vs keyed hopping, keyed BFSK tone positions and multi-antenna energy combining.

PROVENANCE NOTE: docs/ in this repo do not describe arXiv 1903.11261 (a grep finds nothing). The attacker below is therefore NOT a
reproduction of that paper; it is a generic signal-contingent relay model written from the task description: an attacker that does not
know the hop pattern but hears the whole band, and re-radiates energy in response to what it hears, so that its power lands on the
ACTIVE channel only (equivalent to a linear time-invariant 'convolution' of the band with a kernel that maps each tone to another tone).

Model (complex baseband, non-coherent energy detection, one bit per hop):
- M=13 channels, each with S candidate tone positions. Fixed BFSK: S=2, bit b -> position b. Randomised: the pair (p0,p1) of tones
  (and which one means 0) is drawn per hop by a keyed PRF; the attacker knows S and the layout but not the key.
- Receiver has N antennas, per-antenna flat Rayleigh fading h ~ CN(0,1) (independent for signal and relay), noise CN(0,N0) per bin,
  per-antenna Eb/N0 held fixed (extra antennas add diversity, NOT array gain: conservative). Energy statistic T_i = sum_a |y_{a,i}|^2 on the two keyed bins;
  decide bit by the larger T. Ties are impossible with continuous noise.
- Attacker sees the active tone position (perfect energy detection, zero latency: worst case) and spends relay power R (relative to the
  per-bit signal energy) on the opposite tone: 'swap' (fixed BFSK), 'guess1' (all power on one random other position),
  'spread' (R/(S-1) on each other position). Blind wideband jammer: noise power J per bin on every bin.
  For an equal TOTAL budget R a blind wideband jammer covers M*S bins: J = R/(M*S).
"""
import numpy as np
from math import comb
import _common as cm
from _common import C, plt

M_CH = 13


def ber(N=1, S=2, ebn0_db=15.0, attack="none", R_db=0.0, J_db=None, strat="swap", nbits=200_000, seed=3, keyed_tones=False):
    """BER of the energy-combining BFSK receiver. attack in none | wideband (per-bin level J_db) | relay (budget R_db, strategy strat)."""
    rng = np.random.default_rng(seed); N0 = 10 ** (-ebn0_db / 10)
    cn = lambda sc, shape: np.sqrt(sc / 2) * (rng.normal(size=shape) + 1j * rng.normal(size=shape))
    shp = (nbits, N)
    sig = cn(1.0, shp)                                   # active tone: Es=1 times Rayleigh
    noise_a, noise_o = cn(N0, shp), cn(N0, shp)
    Jbin = 0.0 if (attack != "wideband" or J_db is None) else 10 ** (J_db / 10)
    if Jbin: noise_a = noise_a + cn(Jbin, shp); noise_o = noise_o + cn(Jbin, shp)
    R = 10 ** (R_db / 10); P_other = np.zeros(nbits)
    if attack == "relay":
        if strat == "swap" or not keyed_tones: P_other[:] = R                      # fixed layout: the opposite tone is known
        elif strat == "guess1":
            # vectorised equivalent: attacker's random pick among S-1 others hits the opposite tone with prob 1/(S-1)
            P_other = R * (rng.random(nbits) < 1.0 / (S - 1))
        elif strat == "spread": P_other[:] = R / (S - 1)
        else: raise ValueError(strat)
    other = noise_o + np.sqrt(P_other)[:, None] * cn(1.0, shp)
    act = sig + noise_a
    Ta, To = (np.abs(act) ** 2).sum(1), (np.abs(other) ** 2).sum(1)
    return float(np.mean(To > Ta))


def ber_theory(N, gamma):
    """Non-coherent orthogonal BFSK, N-branch square-law combining, Rayleigh, per-branch mean SNR gamma (Proakis, eq. for N-fold diversity)."""
    mu = 1.0 / (2 + gamma)
    return mu ** N * sum(comb(N - 1 + k, k) * (1 - mu) ** k for k in range(N))


def main(nbits=200_000):
    lines = []; res = {}
    eb = np.arange(0, 41, 4.0); S = 8
    # ---- panel a: BER vs Eb/N0, relay budget R = +6 dB
    cases = {
        "no attack, N=1": dict(N=1, S=2), "keyed hop only vs RELAY (fixed BFSK), N=1": dict(N=1, S=2, attack="relay", R_db=6, strat="swap"),
        "relay vs keyed tones S=8 (guess1), N=1": dict(N=1, S=S, attack="relay", R_db=6, strat="guess1", keyed_tones=True),
        "relay vs keyed tones S=8 (spread), N=1": dict(N=1, S=S, attack="relay", R_db=6, strat="spread", keyed_tones=True),
        "relay vs keyed tones S=8 (spread), N=4": dict(N=4, S=S, attack="relay", R_db=6, strat="spread", keyed_tones=True),
        "relay vs keyed tones S=8 (guess1), N=4": dict(N=4, S=S, attack="relay", R_db=6, strat="guess1", keyed_tones=True),
        "blind wideband, same total power (+6 dB over 13x8 bins), N=1": dict(N=1, S=S, attack="wideband", J_db=6 - 10 * np.log10(M_CH * S)),
    }
    pa = {k: [ber(ebn0_db=e, nbits=nbits, **kw) for e in eb] for k, kw in cases.items()}
    res["panel_a_ebn0"] = list(map(float, eb)); res["panel_a"] = pa
    for k, v in pa.items(): lines.append(f"{k:62s} " + " ".join(f"{x:.3f}" for x in v))
    # ---- panel b: BER vs relay budget R at Eb/N0 = 20 dB
    Rs = np.arange(-10, 31, 4.0); RS = {}
    strat_cases = {"fixed BFSK + swap relay, N=1": dict(N=1, S=2, strat="swap"), "keyed tones S=8, guess1, N=1": dict(N=1, S=8, strat="guess1", keyed_tones=True),
                   "keyed tones S=8, spread, N=1": dict(N=1, S=8, strat="spread", keyed_tones=True), "keyed tones S=8, spread, N=4": dict(N=4, S=8, strat="spread", keyed_tones=True),
                   "keyed tones S=16, spread, N=4": dict(N=4, S=16, strat="spread", keyed_tones=True)}
    for k, kw in strat_cases.items(): RS[k] = [ber(ebn0_db=20, attack="relay", R_db=r, nbits=nbits, **kw) for r in Rs]; lines.append(f"R-sweep {k:34s} " + " ".join(f"{x:.3f}" for x in RS[k]))
    RS["blind wideband, equal total power (S=8)"] = [ber(N=1, S=8, ebn0_db=20, attack="wideband", J_db=r - 10 * np.log10(M_CH * 8), nbits=nbits) for r in Rs]
    res["panel_b_R"] = list(map(float, Rs)); res["panel_b"] = RS
    # ---- panel c: honest error floor against wideband jamming (Eb/N0 -> 40 dB), vs per-bin jam level, antennas N
    Js = np.arange(-20, 6, 3.0); FL = {}
    for n in (1, 2, 4, 8):
        FL[n] = [ber(N=n, S=8, ebn0_db=40, attack="wideband", J_db=j, nbits=nbits) for j in Js]; lines.append(f"wideband floor N={n} (per-bin J dB {list(map(int, Js))}): " + " ".join(f"{x:.4f}" for x in FL[n]))
    res["panel_c_J"] = list(map(float, Js)); res["panel_c"] = {str(n): v for n, v in FL.items()}
    print("\n".join(lines))
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.3))
    cols = [C["black"], C["verm"], C["orange"], C["pink"], C["blue"], C["sky"], C["grey"]]
    for (k, v), c in zip(pa.items(), cols): ax[0].semilogy(eb, np.maximum(v, 1e-5), "-o", ms=3, color=c, label=k)
    ax[0].set_xlabel("per-antenna Eb/N0 (dB)"); ax[0].set_ylabel("BER"); ax[0].set_title("relay budget +6 dB over signal energy"); ax[0].legend(fontsize=6, loc="lower left"); ax[0].set_ylim(1e-4, 1)
    for (k, v), c in zip(RS.items(), [C["verm"], C["orange"], C["pink"], C["blue"], C["sky"], C["grey"]]): ax[1].semilogy(Rs, np.maximum(v, 1e-5), "-o", ms=3, color=c, label=k)
    ax[1].set_xlabel("attacker total power R relative to signal (dB)"); ax[1].set_title("Eb/N0 = 20 dB: where tone keying + combining stop helping"); ax[1].legend(fontsize=6, loc="lower right"); ax[1].set_ylim(1e-4, 1)
    for n, c in zip(FL, [C["black"], C["verm"], C["blue"], C["green"]]): ax[2].semilogy(Js, np.maximum(FL[n], 1e-6), "-o", ms=3, color=c, label=f"N={n} antennas")
    ax[2].set_xlabel("wideband jammer power per bin, relative to signal (dB)"); ax[2].set_title("error floor vs wideband jamming (Eb/N0 = 40 dB)"); ax[2].legend(); ax[2].set_ylim(1e-6, 1)
    fig.suptitle("Relay attacker vs keyed hopping: key alone fails; keyed tones + energy combining raise the bar but wideband power still sets a floor", fontsize=9)
    cm.save_fig(fig, "fig3_relay_attack.png"); cm.save_json("exp3_relay_attack.json", res)
    open(cm.os.path.join(cm.OUT, "exp3_relay_attack.txt"), "w").write("\n".join(lines) + "\n")
    return res


if __name__ == "__main__":
    main()
