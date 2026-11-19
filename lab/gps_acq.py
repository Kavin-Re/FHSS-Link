"""GPS C/A-style acquisition simulation (numpy only).

Model / assumptions
-------------------
* Gold codes: GPS C/A pair of 10-stage LFSRs, G1 = 1+x^3+x^10, G2 = 1+x^2+x^3+x^6+x^8+x^9+x^10,
  all-ones initial state, chip = G1[10] xor G2[tap_a] xor G2[tap_b] (published GPS phase-select
  tap pairs for PRN 1-12). Verified against the published first chips of PRN 1 (1100100000).
* Received signal at complex baseband, 1 sample per chip (fs = 1.023 MHz, so 1 ms = 1023
  samples), integer code delay, constant carrier Doppler, no nav-data bit transitions, no code
  Doppler. Noise is complex white Gaussian with E|n|^2 = 1, so "SNR" below is the
  per-sample pre-correlation SNR (C/N0 = SNR + 60.1 dBHz at this fs).
* Acquisition: Doppler grid (+-5 kHz, 500 Hz step) x 1023 code phases, carrier wipe-off then
  FFT-based circular correlation, K ms coherent-per-ms, non-coherently summed over K ms.
  Test metric = peak cell power / mean power of the remaining grid cells.
  Detection threshold is set empirically for ~1 % false alarm from noise-only trials.
* Spoofing flag (two checks, both simple):
  (a) peak metric above what a genuine signal in the assumed genuine range (SNR <= -16 dB)
      can produce (calibrated threshold);
  (b) a second correlation peak 2..10 chips away from the main one at the same/adjacent
      Doppler bin (a spoofer replaying the same PRN with a small offset on top of the real signal),
      above a threshold calibrated on genuine-only trials.
"""
import numpy as np

N = 1023
FS = 1.023e6
G2_TAPS = {1: (2, 6), 2: (3, 7), 3: (4, 8), 4: (5, 9), 5: (1, 9), 6: (2, 10), 7: (1, 8),
           8: (2, 9), 9: (3, 10), 10: (2, 3), 11: (3, 4), 12: (5, 6)}


def ca_bits(prn):
    g1 = [1] * 10
    g2 = [1] * 10
    a, b = G2_TAPS[prn]
    out = []
    for _ in range(N):
        out.append(g1[9] ^ g2[a - 1] ^ g2[b - 1])
        f1 = g1[2] ^ g1[9]
        f2 = g2[1] ^ g2[2] ^ g2[5] ^ g2[7] ^ g2[8] ^ g2[9]
        g1 = [f1] + g1[:-1]
        g2 = [f2] + g2[:-1]
    return np.array(out, dtype=np.int8)


_CODE = {}
_FC = {}
_WIPE = {}


def ca_code(prn):
    """+-1 chips."""
    if prn not in _CODE:
        _CODE[prn] = (1 - 2 * ca_bits(prn)).astype(float)
    return _CODE[prn]


def make_signal(prn, snr_db, doppler, delay, K=1, jam_jsr_db=None, jam_off=None, rng=None, noise=True):
    """K ms of received complex baseband. Returns array length K*N."""
    rng = rng or np.random.default_rng()
    n = np.arange(K * N)
    code = np.tile(np.roll(ca_code(prn), delay), K)
    A = 10 ** (snr_db / 20)
    x = A * code * np.exp(1j * (2 * np.pi * doppler * n / FS + rng.uniform(0, 2 * np.pi)))
    if jam_jsr_db is not None:
        J = A * 10 ** (jam_jsr_db / 20)
        x = x + J * np.exp(1j * (2 * np.pi * jam_off * n / FS + rng.uniform(0, 2 * np.pi)))
    if noise:
        x = x + (rng.standard_normal(K * N) + 1j * rng.standard_normal(K * N)) / np.sqrt(2)
    return x


DOPP = np.arange(-5000, 5001, 500.0)


def surface(rx, prn, dopp=DOPP):
    """Non-coherent (over K ms) correlation power surface [doppler, code phase]."""
    K = len(rx) // N
    if prn not in _FC:
        _FC[prn] = np.conj(np.fft.fft(ca_code(prn)))
    Fc = _FC[prn]
    S = np.zeros((len(dopp), N))
    for k in range(K):
        seg = rx[k * N:(k + 1) * N]
        key = (k, len(dopp), dopp[0])
        if key not in _WIPE:
            t = np.arange(k * N, (k + 1) * N)
            _WIPE[key] = np.exp(-2j * np.pi * dopp[:, None] * t[None, :] / FS)
        W = seg[None, :] * _WIPE[key]
        C = np.fft.ifft(np.fft.fft(W, axis=1) * Fc[None, :], axis=1)
        S += np.abs(C) ** 2
    return S


def metric(S):
    """Peak / mean-of-rest, plus peak location."""
    i, j = np.unravel_index(np.argmax(S), S.shape)
    mask = np.ones_like(S, bool)
    mask[:, [(j + d) % N for d in (-1, 0, 1)]] = False
    return S[i, j] / S[mask].mean(), i, j


def calibrate_threshold(K, pfa=0.01, trials=1500, seed=1, prn=1):
    rng = np.random.default_rng(seed)
    m = [metric(surface(make_signal(prn, -100, 0, 0, K, rng=rng), prn))[0] for _ in range(trials)]
    return float(np.quantile(m, 1 - pfa))


def detect_prob(snr_db, K, thr, trials=200, jsr=None, seed=2, prn=3):
    rng = np.random.default_rng(seed + int(abs(snr_db) * 10))
    hit = 0
    for _ in range(trials):
        fd = rng.uniform(-4800, 4800)
        d = int(rng.integers(0, N))
        jo = rng.uniform(-5000, 5000) if jsr is not None else None
        rx = make_signal(prn, snr_db, fd, d, K, jsr, jo, rng)
        m, i, j = metric(surface(rx, prn))
        cd = min((j - d) % N, (d - j) % N)
        if m > thr and cd <= 1 and abs(DOPP[i] - fd) <= 500:
            hit += 1
    return hit / trials


# ---------------- spoofing flag ----------------
def spoof_features(rx, prn):
    S = surface(rx, prn)
    m, i, j = metric(S)
    # second peak: offsets 2..10 chips either side, Doppler bins i-1..i+1
    offs = [o for o in range(2, 11)] + [-o for o in range(2, 11)]
    rows = [r for r in (i - 1, i, i + 1) if 0 <= r < len(DOPP)]
    cand = np.array([S[r, (j + o) % N] for r in rows for o in offs])
    mask = np.ones_like(S, bool)
    mask[:, [(j + d) % N for d in (-1, 0, 1)]] = False
    floor = S[mask].mean()
    return m, cand.max() / floor


def spoof_case(prn, snr_g, snr_s, K, rng, genuine=True, off=None):
    fd_g = rng.uniform(-4000, 4000)
    d = int(rng.integers(0, N))
    x = 0
    if genuine and snr_g is not None:
        x = x + make_signal(prn, snr_g, fd_g, d, K, rng=rng, noise=False)
    if snr_s is not None:
        o = off if off is not None else int(rng.integers(2, 9)) * rng.choice([-1, 1])
        x = x + make_signal(prn, snr_s, fd_g + rng.uniform(-300, 300), (d + o) % N, K, rng=rng, noise=False)
    noise = (rng.standard_normal(K * N) + 1j * rng.standard_normal(K * N)) / np.sqrt(2)
    return x + noise


def calibrate_spoof(K, seed=5, trials=300, snr_max=-16.0):
    """Thresholds from genuine-only trials (SNR uniform in [-24,-16] dB)."""
    rng = np.random.default_rng(seed)
    hi = [spoof_features(spoof_case(3, snr_max, None, K, rng), 3)[0] for _ in range(trials)]
    sec = [spoof_features(spoof_case(3, rng.uniform(-24, snr_max), None, K, rng), 3)[1] for _ in range(trials)]
    return float(np.quantile(hi, 0.99)), float(np.quantile(sec, 0.99))


def spoof_flag(rx, prn, thr_a, thr_b):
    m, s2 = spoof_features(rx, prn)
    a, b = m > thr_a, s2 > thr_b
    return a, b


SNRS = [-34, -32, -30, -28, -26, -24, -22, -20]
JSRS = [0, 10, 15, 18, 20, 22, 25, 30, 40, 50]
SP_POW = [-14, -12, -10, -8, -5, 0]
REL = [0, 3, 6, 10, 15, 20]


def stage_a(R):
    b1 = ca_bits(1)
    first = ''.join(map(str, b1[:10]))
    print("PRN1 first 10 chips:", first, "(published 1100100000)", "OK" if first == "1100100000" else "MISMATCH")
    c = {p: ca_code(p) for p in range(1, 9)}
    xc = lambda a, b: np.real(np.fft.ifft(np.fft.fft(a) * np.conj(np.fft.fft(b))))
    ac = xc(c[1], c[1])
    cc = max(np.abs(xc(c[a], c[b])).max() for a in range(1, 9) for b in range(a + 1, 9))
    print(f"autocorr peak {ac[0]:.0f}, max |sidelobe| {np.abs(ac[1:]).max():.0f}; max |cross-corr| over PRN1-8 pairs {cc:.0f} (Gold bound 65)")
    R['pd'] = {}
    for K in (1, 5):
        thr = calibrate_threshold(K)
        print(f"K={K} ms: threshold (Pfa 1%) metric = {thr:.2f} ({10*np.log10(thr):.2f} dB)")
        pd = [detect_prob(s, K, thr, trials=150) for s in SNRS]
        R['pd'][K] = (thr, pd)
        print("  Pd vs SNR(dB): " + ", ".join(f"{s}:{p:.2f}" for s, p in zip(SNRS, pd)))
    rng = np.random.default_rng(99)
    thr1 = R['pd'][1][0]
    fa = np.mean([metric(surface(make_signal(3, -100, 0, 0, 1, rng=rng), 3))[0] > thr1 for _ in range(600)])
    print(f"measured false-alarm rate on fresh noise-only trials (K=1, 600 trials): {fa:.3f}")
    rng = np.random.default_rng(7)
    ok = 0
    for t in range(40):
        p = int(rng.integers(1, 9))
        rx = make_signal(p, -16, rng.uniform(-4000, 4000), int(rng.integers(0, N)), 1, rng=rng)
        ms = [metric(surface(rx, q))[0] for q in range(1, 9)]
        ok += (int(np.argmax(ms)) + 1 == p)
    print(f"PRN identification among PRN1-8 at SNR -16 dB, K=1: {ok}/40 correct")


def stage_b(R):
    thr1 = R['pd'][1][0]
    R['jam'] = {}
    for snr in (-10, -15):
        pd = [detect_prob(snr, 1, thr1, trials=150, jsr=j, seed=11) for j in JSRS]
        R['jam'][snr] = pd
        print(f"CW jammer, SNR {snr} dB, K=1: Pd vs J/S(dB): " + ", ".join(f"{j}:{p:.2f}" for j, p in zip(JSRS, pd)))
        tol = [j for j, p in zip(JSRS, pd) if p >= 0.9]
        print(f"  largest tested J/S with Pd>=0.9 at SNR {snr} dB: {max(tol) if tol else 'none'} dB")
        j50 = next((float(np.interp(0.5, pd[i + 1:i - 1 if i else None:-1] if False else [pd[i + 1], pd[i]], [JSRS[i + 1], JSRS[i]])) for i in range(len(pd) - 1) if pd[i] >= 0.5 > pd[i + 1]), None)
        print(f"  J/S where Pd crosses 0.5 (linear interp): {j50}")
    print("  (reference: 10log10(1023) = 30.1 dB spreading gain vs a CW)")


def stage_c(R):
    K = 1
    ta, tb = calibrate_spoof(K)
    print(f"spoof thresholds (K=1): (a) peak metric > {10*np.log10(ta):.2f} dB, (b) second-peak metric > {10*np.log10(tb):.2f} dB")
    rng = np.random.default_rng(21)
    T = 200
    fl = np.mean([any(spoof_flag(spoof_case(3, rng.uniform(-24, -16), None, K, rng), 3, ta, tb)) for _ in range(T)])
    print(f"genuine-only false flag rate (SNR uniform -24..-16 dB, {T} trials): {fl:.3f}")
    R['spA'] = [np.mean([spoof_flag(spoof_case(3, None, s, K, rng), 3, ta, tb)[0] for _ in range(T)]) for s in SP_POW]
    print("spoofer only (clean, strong) flag rate (a) vs spoofer SNR: " + ", ".join(f"{s}:{p:.2f}" for s, p in zip(SP_POW, R['spA'])))
    R['spB'], R['spAB'] = [], []
    print("genuine -20 dB + spoofer (same PRN, 2-8 chip offset), spoofer excess power r dB:")
    for r in REL:
        fb, fa_, fany = [], [], []
        for _ in range(T):
            a, b = spoof_flag(spoof_case(3, -20, -20 + r, K, rng), 3, ta, tb)
            fa_.append(a); fb.append(b); fany.append(a or b)
        R['spB'].append(np.mean(fb)); R['spAB'].append((np.mean(fa_), np.mean(fany)))
        print(f"  r={r:2d} dB: flag (a)={np.mean(fa_):.2f}  flag (b)={np.mean(fb):.2f}  either={np.mean(fany):.2f}")


def stage_fig(R):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 2, figsize=(11, 8))
    for K, st in ((1, 'o-'), (5, 's-')):
        ax[0, 0].plot(SNRS, R['pd'][K][1], st, label=f"{K} ms")
    ax[0, 0].set(title="Pd vs per-sample SNR (Pfa~1%)", xlabel="SNR (dB)", ylabel="Pd"); ax[0, 0].legend(); ax[0, 0].grid(alpha=.3)
    for snr in R['jam']:
        ax[0, 1].plot(JSRS, R['jam'][snr], 'o-', label=f"SNR {snr} dB")
    ax[0, 1].set(title="CW jammer: Pd vs J/S (K=1 ms)", xlabel="J/S (dB)", ylabel="Pd"); ax[0, 1].legend(); ax[0, 1].grid(alpha=.3)
    rng = np.random.default_rng(3)
    S = surface(make_signal(3, -14, 1700, 400, 1, rng=rng), 3)
    ax[1, 0].imshow(S, aspect='auto', extent=[0, N, DOPP[-1], DOPP[0]], cmap='viridis')
    ax[1, 0].set(title="Correlation surface PRN3, SNR -14 dB", xlabel="code phase (chips)", ylabel="Doppler (Hz)")
    ax[1, 1].plot(REL, [x[0] for x in R['spAB']], 'o-', label="(a) peak too high")
    ax[1, 1].plot(REL, R['spB'], 's-', label="(b) 2nd peak")
    ax[1, 1].plot(REL, [x[1] for x in R['spAB']], '^--', label="either")
    ax[1, 1].set(title="Spoof flag rate vs spoofer excess power", xlabel="spoofer power over genuine (dB)", ylabel="flag rate"); ax[1, 1].legend(); ax[1, 1].grid(alpha=.3)
    fig.tight_layout(); fig.savefig("figures/gps_acq.png", dpi=110)
    print("saved figures/gps_acq.png")


def main(stages="abcf"):
    """stages letters: a (codes, Pd, PRN id), b (jammer), c (spoof), f (figure). State is kept in the
    pickle named by env LAB_CACHE if set (lets slow runs be split into several shorter invocations)."""
    import os, pickle
    cache = os.environ.get("LAB_CACHE")
    R = pickle.load(open(cache, 'rb')) if cache and os.path.exists(cache) else {}
    for st, fn in (("a", stage_a), ("b", stage_b), ("c", stage_c), ("f", stage_fig)):
        if st in stages:
            fn(R)
            if cache:
                pickle.dump(R, open(cache, 'wb'))


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else "abcf")
