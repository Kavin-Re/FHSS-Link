# Round 3, batch A: four software-only modules (lab/)

All numbers below are copied from the printed output of the scripts in `lab/` (numpy only, fixed seeds).
Tests: `python3 lab/test_batchA.py` -> 11 tests, ALL PASSED (about 20 s).
Re-run: `cd lab && python3 gps_acq.py | ss_watermark.py | audio_fh.py | amc.py` (gps_acq.py takes ~35 s,
ss_watermark.py ~65 s, audio_fh.py ~50 s, amc.py ~35 s on the laptop VM).
Figures: `lab/figures/{gps_acq,ss_watermark,audio_fh,amc}.png`.

## 1. GPS-style acquisition (lab/gps_acq.py)

Model: C/A Gold codes (G1 = 1+x^3+x^10, G2 = 1+x^2+x^3+x^6+x^8+x^9+x^10, published phase-tap pairs, PRN 1-12 in the table, PRN 1-8 exercised),
1 sample/chip (1.023 MHz), integer code delay, Doppler +-5 kHz searched in 500 Hz steps, FFT circular correlation, no nav bits.
SNR = per-sample pre-correlation SNR (C/N0 = SNR + 60.1 dBHz at this fs). Metric = peak cell power / mean of remaining cells; threshold from noise-only trials (Pfa 1 %).

Code check: PRN1 first 10 chips = 1100100000 (matches the published value). Autocorrelation peak 1023, max |sidelobe| 65,
max |cross-correlation| over all PRN1-8 pairs 65 (Gold bound for length 1023).

Detection probability (150 trials per point, random Doppler and code phase):

| SNR (dB) | -34 | -32 | -30 | -28 | -26 | -24 | -22 | -20 |
|---|---|---|---|---|---|---|---|---|
| Pd, 1 ms | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 | 0.04 | 0.21 |
| Pd, 5 ms non-coherent | 0.00 | 0.00 | 0.01 | 0.02 | 0.13 | 0.49 | 0.95 | 1.00 |

Thresholds: 14.68 (11.67 dB) for 1 ms, 4.80 (6.82 dB) for 5 ms. Measured false-alarm rate on 600 fresh noise-only trials (1 ms): 0.007.
PRN identification among PRN 1-8 at SNR -16 dB, 1 ms: 40/40 correct.

CW jammer (1 ms, Pd vs J/S, jammer at random offset within +-5 kHz):

| J/S (dB) | 0 | 10 | 15 | 18 | 20 | 22 | 25 | 30 |
|---|---|---|---|---|---|---|---|---|
| SNR -10 dB | 1.00 | 1.00 | 1.00 | 0.85 | 0.44 | 0.15 | 0.01 | 0.00 |
| SNR -15 dB | 0.99 | 0.97 | 0.82 | 0.54 | 0.30 | 0.11 | 0.01 | 0.00 |

Pd crosses 0.5 at J/S = 19.7 dB (SNR -10) and 18.3 dB (SNR -15); Pd >= 0.9 up to 15 dB and 10 dB respectively.
Reading: the nominal spreading gain vs a CW is 10log10(1023) = 30.1 dB, but the tolerated J/S measured here is about 18-20 dB. My interpretation (not separately
verified) is that the max-over-1023x21-cells peak search picks up the jammer's correlation leakage, which sits above its mean level; so quote about 18-20 dB, not 30 dB.

Spoofing flag (1 ms; (a) peak metric above what a genuine signal at SNR <= -16 dB gives, threshold 16.17 dB; (b) a second peak 2-10 chips from the main one, threshold 8.86 dB;
both calibrated on genuine-only trials, 200 test trials per row):
- genuine only (SNR -24..-16 dB): false flag rate 0.030.
- spoofer only, clean and strong, flag rate (a) vs spoofer SNR: -14 dB 0.30, -12 dB 0.94, -10 dB 1.00, -8 dB 1.00, -5 dB 1.00, 0 dB 1.00.
- genuine at -20 dB plus a same-PRN spoofer offset 2-8 chips, spoofer excess power r: r=0 dB: (a) 0.00 (b) 0.46 either 0.46; r=3: 0.00/0.77/0.77; r=6: 0.34/0.77/0.84; r=10: 1.00/0.69/1.00; r=15: 1.00/0.60/1.00; r=20: 1.00/0.40/1.00.

Caveats: (a) is in effect a "too-strong correlation peak" power test and will also flag a legitimate strong signal (e.g. open-sky receiver with a better antenna): its threshold depends on the assumed genuine SNR range.
The simulator adds receiver noise after the spoofer, so "perfectly clean" spoofer waveform is not directly visible; only its power/duplicate-peak signature is. (b) rate falls for large r because the genuine peak sinks below the spoofer's sidelobes.
Nothing here models multipath, nav-data bit flips, code Doppler, fractional chip delay, or a spoofer that matches the genuine power and code phase exactly (undetectable by these checks).
The Pd curve for 1 ms starts rising only above -26 dB: that is the expected operating region (~34-40 dBHz equivalent), not a problem, but the SNR axis is pre-correlation.

## 2. Spread-spectrum image watermark (lab/ss_watermark.py)

Model: 256x256 synthetic image (seeded; gradient, circles, rectangles, smoothed-noise texture, sinusoid), 8x8 orthonormal block DCT, 37 mid-frequency coefficients/block (3 <= u+v <= 8),
M = 37888 chips (sqrt(M) = 195, 45.8 dB), additive +-1 key pattern at alpha = 3, blind detection z = <c,w>/(std(c) sqrt(M)).
PSNR watermarked vs original: 40.97 dB mean over 20 images (min 40.93). 20 images x (true key + 200 wrong keys); wrong-key z is N(0,1)-like (mean -0.03, std 1.00, max over 4000 values 3.1-3.6 per attack).

| attack | mean z (true key) | min z over 20 images | max wrong-key z | AUC | Pd (z>4) |
|---|---|---|---|---|---|
| none | 27.81 | 26.23 | 3.24 | 1.000 | 1.00 |
| noise sigma 5 / 10 / 20 / 40 | 26.92 / 24.85 / 19.70 / 12.73 | 25.01 / 23.65 / 17.68 / 11.41 | 3.31 / 3.59 / 3.20 / 3.33 | 1.000 | 1.00 |
| JPEG-like Q 90 / 70 / 50 / 30 | 21.10 / 14.15 / 11.86 / 9.63 | 19.69 / 12.65 / 10.35 / 7.90 | about 3.2-3.4 | 1.000 | 1.00 |
| JPEG-like Q 10 | 5.33 | 3.49 | 3.46 | 1.000 | 0.95 |
| crop + zero-pad 32 px border | 20.65 | 19.00 | 3.12 | 1.000 | 1.00 |
| shift-crop (5,3) px, 64-offset grid search | 26.86 | 25.15 | 4.32 (wrong-key z is inflated by the search: mean +2.09) | 1.000 | 1.00, but Pfa(z>4) = 0.001 |
| blur sigma 0.7 / 1.0 / 1.5 | 13.19 / 7.28 / 3.28 | 11.66 / 5.53 / 1.10 | 3.32 / 3.44 / 3.52 | 1.000 / 1.000 / 0.989 | 1.00 / 1.00 / 0.30 |
| scale 2x down/up | 5.80 | 4.21 | 3.58 | 1.000 | 1.00 |

Honest limits: blur sigma 1.5 mostly defeats it (Pd(z>4) = 0.30; at the 0.1 % empirical-Pfa threshold Pd = 0.55). JPEG Q=10 is marginal. The shift-crop result needs the detector to search the 8x8 grid (not free: wrong-key statistics rise).
Rotation, general geometric attacks, and non-aligned crop without grid search were not tested (an unsearched misaligned detector would fail).
The host image is a synthetic noisy-texture image; natural images with different mid-band energy will give different z (the z scale is proportional to alpha/std(host coefficients)).
Strength tradeoff (JPEG Q=50, mean z of true key): alpha 1: PSNR 49.98 dB, z 4.00, Pd(z>4) 0.45; alpha 2: 44.37 dB, 7.90, 1.00; alpha 3: 40.94 dB, 11.86; alpha 4: 38.47 dB, 15.82; alpha 6: 34.97 dB, 23.75.
Processing-gain link: z ~ alpha sqrt(M)/sigma (host plus attack noise), so z grows linearly with alpha (4.0 -> 7.9 -> 11.9 -> 15.8 -> 23.8 above) and as sqrt of the chip count.

Multi-bit (16 bits, disjoint key-permuted subsets of 2368 chips per bit, pattern pair per bit, alpha = 4, PSNR 38.51 dB; 20 trials = 320 bits per row):
BER 0.0000 for none, noise sigma 5/10/20/40, JPEG Q 90/70, crop+pad, blur 0.7; JPEG Q=50 0.0094, Q=30 0.0156, Q=10 0.1219; blur 1.0 0.0437, blur 1.5 0.1969; scale 2x 0.0719.
Wrong key, no attack: BER 0.519. The multi-bit decoder has no grid search, so the shift-crop attack was not run for it.

## 3. Frequency hopping over audio (lab/audio_fh.py)

Design (documented in the file): 8 channels at 1000-4500 Hz (500 Hz apart), 20 ms hops (882 samples, 44.1 kHz), BFSK inside each channel at centre -100 / +100 Hz (1 bit per hop),
hop channel = HMAC-SHA256(key, counter)[0] mod 8 (4000-hop histogram: 500, 480, 506, 549, 459, 492, 505, 509), Goertzel detection, perfect timing/key at the receiver.
Fixed baseline: channel 3 (2400/2600 Hz). Fixed jammer is a tone on 2400 Hz (the bit-0 tone of the fixed channel; this is a targeted jammer, with J/S relative to the signal tone); sweeping jammer is a 1000-4500 Hz chirp every 0.5 s.
SER, 4000 symbols x 3 seeds:

| condition | fixed | hopping |
|---|---|---|
| clean | 0.0000 | 0.0000 |
| white noise, full-band SNR 0 / -10 dB | 0.0000 / 0.0000 | 0.0000 / 0.0000 |
| white noise -20 dB | 0.0548 | 0.0553 |
| white noise -24 dB | 0.2069 | 0.2025 |
| white noise -27 dB | 0.3200 | 0.3181 |
| fixed-tone jam J/S -6 dB | 0.0000 | 0.0000 |
| fixed-tone jam J/S 0 dB | 0.2526 | 0.0348 |
| fixed-tone jam J/S +6 dB | 0.5011 | 0.0680 |
| fixed-tone jam J/S +12 dB | 0.5011 | 0.0680 |
| sweep jam J/S 0 dB | 0.0000 | 0.0000 |
| sweep jam J/S +6 dB | 0.0201 | 0.0155 |
| sweep jam J/S +12 dB | 0.0597 | 0.0480 |

Reading: hopping gives a large win only against a jammer that stays on one channel (0.50 -> 0.068 at +6 dB; about 1/8 of hops land on the jammed channel, giving ~0.5/8 = 0.0625 expected; measured 0.068).
Against white noise it is identical to fixed (as it must be), and against the sweeping jammer the difference (0.0201 vs 0.0155 at +6 dB) is small; I did not test whether it is statistically significant. A jammer covering all 8 channels, or one that follows the hops, was not simulated.

Files in `lab/audio/` (6 s, 300 bits, 44.1 kHz, 16-bit mono, each normalised to peak 0.890 of full scale, no clipping; 8 x 529.2 kB = 4.23 MB total).
What to play: `hop_clean.wav` (the hopping signal, chirpy), `fixed_clean.wav` (one steady two-tone pattern); then `hop_fixedjam.wav` vs `fixed_fixedjam.wav` (a steady 2.4 kHz whine is added; this is the demo: decoded back from the 16-bit files the SER is 0.0567 for hopping and 0.4833 for fixed);
`hop_sweepjam.wav` / `fixed_sweepjam.wav` (SER 0.0200 / 0.0133 on these 300 bits, too few to separate); `hop_noise.wav` / `fixed_noise.wav` (white noise at -6 dB full-band SNR, SER 0.0000 for both).
Jam files use J/S +6 dB. These files hold a 300-bit sample, so their SERs are much noisier than the 12000-symbol table above.

## 4. Automatic modulation classification (lab/amc.py)

Classes: OOK, BPSK, QPSK, BFSK, DS-SS BPSK (7-chip m-sequence, 2 samples/chip, about 4x the bandwidth of plain BPSK). 1024-sample frames, random phase, CFO +-0.003 cycles/sample, random timing offset, AWGN (SNR is wideband).
8 features (amplitude CV, kurtosis of |x|, 2nd and 4th power spectral peak ratios, instantaneous-frequency std, spectral flatness, spectral peak ratio, second/first peak ratio).
Softmax regression and nearest centroid, both written in numpy; trained on SNR -5..20 dB pooled (300 frames/class/SNR; train accuracy 0.983 softmax, 0.881 centroid); tested on fresh data (200 frames per class per SNR, 1000 frames per SNR):

| SNR (dB) | -10 | -5 | 0 | 5 | 10 | 15 | 20 |
|---|---|---|---|---|---|---|---|
| softmax | 0.484 | 0.890 | 0.999 | 1.000 | 1.000 | 1.000 | 1.000 |
| nearest centroid | 0.268 | 0.539 | 0.748 | 1.000 | 1.000 | 0.996 | 0.992 |

Confusion matrices (softmax) at 0, 5, 10, 15 dB are printed by the script: diagonal 200/200 for every class at 5, 10 and 15 dB; at 0 dB the only error is 1 BFSK frame called OOK.
At -5 dB (rows true -> predicted): BPSK 107 correct, 15 as QPSK, 78 as DS-SS; QPSK 199/200; BFSK 189 (7 as OOK, 4 as QPSK); DS-SS 195; OOK 200. BPSK vs DS-SS is the hardest pair at low SNR.
Caveats: the near-perfect results at >= 5 dB reflect a clean, idealised synthetic setup (rectangular pulses, same symbol rate/timing structure per class, no fading, no interference, one fixed spreading code), not real-world performance; with the SNR defined wideband, DS-SS gets no processing gain.
Training pooled SNRs down to -5 dB; the -10 dB column is outside the training range.

## Not done / not verified
- No hardware or git operations were performed; no existing files were edited. `lab/__pycache__/` was created by Python.
- GPS: second-peak spoof detector is only meaningful when the genuine signal is also present; single-spoofer detection relies on power alone.
- Statistical significance of the hop vs fixed difference under the sweeping jammer was not tested.
