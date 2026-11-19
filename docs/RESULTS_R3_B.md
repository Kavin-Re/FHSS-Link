# Round 3, batch B: seven software-only studies (lab2/)

Every number below was printed by the script named in the section header (outputs saved as `lab2/out_*.txt`; figures in `lab2/figures/`). Tests: `python3 lab2/test_batchB.py` (19 assertions-based tests, all pass in about 3 s). Everything is simulation or theory on a laptop. Nothing was run on hardware, and none of the existing files were edited.

How to rerun: each script runs straight through (`python3 lab2/<name>.py`). Some take minutes. For short slices set `LAB2_CACHE=1 LAB2_BUDGET=30` and repeat until it stops printing `BUDGET_EXHAUSTED` (the cache lives in `~/.lab2cache` of the VM). Note: a stale folder `lab2/.cache/` was created by an early version of the helper and could not be deleted (deletion was not allowed); it is unused and can be removed.

---
## 1. Networked control over the lossy link (`lab2/netcontrol.py`, fig `netcontrol_rms.png`)

Setup: linearised inverted pendulum, dt = 0.05 s, open-loop unstable discrete pole |a| = 1.2479. LQR gain from a numpy Riccati iteration, K = [9.4401, 2.1996]. Only the command packet is lost. Three loss policies at the actuator: `zero` (u = 0), `hold` (last command), `pred` (the packet carries the state and the actuator runs the nominal model xh+ = (A-BK) xh between packets). Mean-square stability (MSS) is tested exactly with the Markov-jump spectral-radius condition, then checked by simulation.

**Scalar bound.** For a scalar plant with deadbeat gain and u = 0 on loss, the printed theory threshold equals 1 - 1/a^2 exactly: a = 1.2 gives 0.3056, a = 1.5 gives 0.5556, a = 2.0 gives 0.75. Hold-last needs far more: 0.7549, 0.8333, 0.9000. The predictor equals the bound (0.3056, 0.5556, 0.75).

**Pendulum, i.i.d. loss, MSS threshold on delivery probability:** zero 0.577, hold 0.483, pred 0.358 (the last equals 1 - 1/a^2 = 0.3579 for the pendulum's unstable pole). The second-moment theory matches Monte Carlo within about 1% where Monte Carlo is reliable (for example zero, p = 0.95: analytic 4.6734e-05, simulated 4.6973e-05).

**Sample-path view.** Fraction of runs that tip beyond 0.35 rad within 200 steps (10 s): the delivery at which 1% of runs fall is 0.591 (zero), 0.477 (hold), 0.367 (pred), close to the MSS values for this plant. For the scalar plant the corresponding value is higher than the MSS one (0.530, 0.772, 0.899 for a = 1.2, 1.5, 2.0) because that criterion depends on the chosen limit and horizon. A plain ensemble-mean estimate of mean-square growth was tried first and discarded: it under-samples rare long loss runs and gave about 0.22 for every a, which is wrong.

**RMS angle vs delivery (i.i.d.).** Lossless RMS 0.00639 rad. At p = 0.8: zero 0.00905, hold 0.00679, pred 0.00713. At p = 0.5: zero 3.15 rad (diverging), hold 0.0143, pred 0.0112. Highest grid p at which RMS exceeds twice the lossless RMS: zero 0.65, hold 0.50, pred 0.45. Hold and pred are about equal at high delivery; pred is the only one still bounded near 0.35-0.40.

**Burstiness (Gilbert-Elliott from hopping against a jammer, dB = 0.05, dG = 0.99, mean dwell D packets per hop).** At equal mean delivery bursts hurt a lot:
- MSS spectral radius at q = k/M = 1/13 (mean delivery 0.918), D = 1, 1.5, 2, 3, 5, 10, 20: zero 0.726, 0.762, 0.869, 1.059, 1.234, 1.370, 1.439. hold and pred are similar (pred 0.699 ... 1.411). So a mean dwell of about 3 packets already makes the loop mean-square unstable even with only 1 of 13 channels jammed.
- MSS threshold on mean delivery rate: D = 1: zero 0.577, hold 0.483, pred 0.358. D = 1.5: 0.682, 0.650, 0.509. D = 2: 0.787, 0.792, 0.661. D = 3: zero and hold unstable at every q > 0; pred 0.964.
- Empirical RMS at mean delivery 0.90 (rad): zero 0.00739 (D=1), 0.00924 (D=2), 0.223 (D=5); pred 0.00671, 0.00766, 0.114.
- Fall probability within 10 s at k = 1 of 13 jammed (mean delivery 0.918): D = 5: 0.052 (zero), 0.055 (hold), 0.022 (pred); D = 20: 0.249, 0.242, 0.151. At k = 3 of 13 (mean 0.773): D = 5: 0.292, 0.269, 0.115; D = 20: 0.620, 0.609, 0.433; with D = 1 all are 0.000.
- Sample-path critical mean delivery (1% fall in 10 s, coarse q grid): zero D=1 0.609, D=5 0.977; pred D=1 0.373, D=5 0.950.

**Thresholds suggested for a link-layer controller (this plant and period only; scale with 1 - 1/a^2).**
1. With i.i.d.-like loss, treat windowed delivery below about 0.6 as critical when the actuator holds or zeros the command (MSS floors 0.48 to 0.58), and below about 0.4 if it runs a predictor.
2. The mean is not enough. The burst length matters more: a mean dwell of 3 or more packets (0.15 s here) breaks mean-square stability at 92% mean delivery, so also flag any loss run or hop dwell longer than about 2 packets as critical.
3. For other plants use p_c = 1 - 1/a^2 with a the per-period unstable pole (a = 1.2: 0.31, 1.5: 0.56, 2.0: 0.75 in the printed scalar cases).

Caveats: sensor-to-controller link ideal; no actuator saturation; Gaussian process noise; the fall limit (0.35 rad) and horizon are my choices; MSS is a conservative criterion (a heavy-tailed loss-run effect), as the sample-path numbers show.

---
## 2. Clock tamer (`lab2/clock_kalman.py`, fig `clock_kalman.png`)

Model: skew uniform within +-20 ppm initially, random walk 0.02 ppm/sqrt(s), unmodelled 0.5 ppm thermal sinusoid (300 s), beacon timestamp noise 3 us, phase noise 0.3 us/sqrt(s). Guard g = 99.9th percentile of the timing error, calibrated on one seed and checked on another. Airtime: T_pkt = 2 ms, beacon 1 ms.

| T_b [s] | guard naive / Kalman [us] | useful airtime eta naive / Kalman | saved [pp] |
|---|---|---|---|
| 0.1 | 10.1 / 3.8 | 0.980 / 0.986 | 0.6 |
| 1 | 23.4 / 4.7 | 0.976 / 0.994 | 1.8 |
| 5 | 98.6 / 9.3 | 0.910 / 0.991 | 8.1 |
| 10 | 195.5 / 13.1 | 0.836 / 0.987 | 15.1 |
| 30 | 591.5 / 27.5 | 0.628 / 0.973 | 34.5 |
| 60 | 1206.7 / 54.3 | 0.453 / 0.948 | 49.5 |
| 120 | 2498.0 / 131.3 | 0.286 / 0.884 | 59.8 |

- Hold-out reception rates at the calibrated guards were 0.9984 to 0.9994 across all 10 beacon periods (target 0.999), so the quantile calibration works within sampling error.
- Best operating points: naive T_b = 0.25 s (eta 0.985, g = 11.5 us); Kalman T_b = 1 s (eta 0.994, g = 4.7 us). Each at its own best: +1.0 pp.
- The longest beacon period keeping the guard at or below 100 us: naive 5 s, Kalman 60 s (12 times fewer beacons).
- Beacon loss 20% at T_b = 5 s: naive guard 98.6 -> 338.7 us; Kalman 9.3 -> 13.1 us.
- Filter mismatch at T_b = 30 s (skew-walk density used by the filter relative to truth): 0.01: 49.7 us, 0.1: 37.5, 1.0: 27.5, 10: 24.1, 100: 26.4. Over-estimating the process noise helped here, most likely because of the unmodelled thermal sinusoid.
- Pure constant skew (no walk, no sinusoid), T_b = 30 s: naive 582.0 us, Kalman 7.6 us.

Caveats: Gaussian noise, no clock steps, beacon detection jitter assumed 3 us (hardware timestamping), the airtime model is simple (guard on both sides of every slot). The finding "naive is fine for T_b of 0.25 s, Kalman buys nothing in airtime there" is part of the table: the gain only becomes large once beacons are slower than about 1-2 s.

---
## 3. Transmitter fingerprinting (`lab2/fingerprint.py`, fig `fingerprint.png`)

Six nodes (skews +2, +3.5, -1, +8, -6.5, +11 ppm; jitter 6, 9, 12, 7, 10, 15 us), a packet every 100 ms, skew by regression slope, jitter by residual std, enrolled with 5000 packets (enrolled skews match true to 0.01 ppm). Test windows see 0.3 ppm temperature wander.

- Identification accuracy: n = 20 packets (2 s) 0.736 (worst node 0.570); n = 50 0.991; n >= 100 1.000.
- Impostor with the correct key (random clock), detection at a 1% false-alarm target: n = 20: 0.668; n = 50: 0.943; n = 100: 0.987; n = 200: 0.995; n = 1000: 0.996. Measured false-alarm rates on held-out windows were 0.0042 to 0.0147 for the 1% target (n = 20 to 2000).
- At 0.1% false alarm: random impostor 0.991 at n = 200; 0.995 at n = 1000.
- Skilled impostor (skew within +-1 ppm and jitter within +-20% of the claimed node), 1% FA: n = 50: 0.079; n = 100: 0.244; n = 200: 0.446; n = 500: 0.660; n = 1000: 0.741; n = 2000: 0.786.
- Exact clone: detection equals the false-alarm rate (0.005 to 0.017 at the 1% target). The method cannot see a clone.
- ROC points (random impostor): n = 200: FA 0.0102 -> detection 0.991; n = 1000: FA 0.0102 -> 0.996. The random impostor curve saturates just below 1 (0.982 at the lowest printed false-alarm point, n = 200), plausibly because some random draws land near the claimed node.

Caveats: Gaussian jitter and independent per packet (real hardware, interrupts and MAC timing add heavy tails and bursts), hardware timestamps assumed, the 0.3 ppm temperature wander is my assumption, node population only six, the impostor draws are from my distribution (+-20 ppm, 4-16 us).

---
## 4. Jammer/defender matrix game (`lab2/game_lp.py`, fig `game_lp.png`)

Own dense simplex (Bland's rule), certificate = duality gap on the returned strategies; Hedge (multiplicative weights) as an independent check with its proven bound. Delivery 0.05 on a jammed channel, 0.99 on a clean one (sim/game.py loss 0.95 / 0.01).

**Formula.** The uniform defender gets p_clean - (k/M)(p_clean - p_jam) against any jammed set of size k, and a uniform random k-subset jammer forces exactly that, so it is the value. The printed LP values match it to 6 digits in all ten cases, duality gaps at most 4.7e-15, optimal defender strategy exactly uniform (max deviation 4e-16). Examples: (M,k) = (13,1) 0.917692; (13,2) 0.845385; (13,3) 0.773077; (13,4) 0.700769; (13,6) 0.556154; (8,1) 0.8725; (20,2) 0.896. The sign in the task text had p_jam - p_clean; with p_jam as delivery on a jammed channel the minus form above is the correct one.

**Versus EXP3 simulation (sim/game.py, M = 13, k = 1, last 5000 slots of 20000, 3 seeds, run here):** blind 0.9197, mixed 0.9219, ucb 0.9237, against the game value 0.9177. The EXP3 jammer (gamma = 0.07) does not reach the optimum, so the defender sees 0.002 to 0.006 more than the guaranteed value; the 0.92 quoted earlier is consistent with the value, not an extra gain.

**Cost version** (jam any set of at most 3, cost c per channel, M = 13): value equals 0.99 - 3 max(0, 0.0723 - c) in every case. At c = 0 value 0.7731, c = 0.05: 0.9231, c = 0.0723 (break-even): 0.9900, c >= 0.08: 0.9900 and the jammer stays silent (expected jammed set size 0.000).

**Unequal channel quality** (q = 0.99 x5, 0.95 x3, 0.80 x3, 0.5, 0.3; jammed delivery = 0.05 q): value 0.8589 (k = 1), 0.7610 (k = 2), 0.6815 (k = 3). Uniform hopping only guarantees 0.7738, 0.7015, 0.6291. Always using the best channel guarantees 0.0495. For k = 1 the LP value equals the closed form (support of the 8 best channels, x proportional to 1/q): weight 0.123 on each 0.99 channel, 0.128 on each 0.95 channel, zero on the five worst. For k = 2 and 3 the mass spreads to the 0.80 channels (0.105 each) and the 0.5 and 0.3 channels still get zero. Hedge for these games: gap 7.8e-4 at T = 100000 for k = 1 (proven bound 7.0e-3), value estimates within 3e-4 of the LP.

Caveats: payoffs are delivery probabilities, not throughput or energy; the jammer is memoryless; a symmetric homogeneous game makes Hedge trivially exact, which is why the Hedge check is run on the unequal-quality games.

---
## 5. Information theory of the jammed link (`lab2/capacity.py`, fig `capacity.png`)

Hopping capacity (erasure model, e_j = 0.95, e_c = 0.01, M = 13) with a keyed hop schedule the jammer does not know: 0.9900, 0.9177, 0.8454, 0.7731, 0.7008, 0.6285, 0.5562 for k = 0..6 jammed channels. These equal the game values of module 4 (same LP, printed side by side). If the hop pattern is known to the jammer the capacity is 1 - e_j = 0.05 for any k >= 1. So keeping the schedule secret is worth 0.87 bits per packet bit at k = 1.

Eb/N0 limits: R = 4/7: Shannon 0.24 dB, BPSK soft 0.53, hard-decision 2.06; R = 1/2: 0.00, 0.19, 1.77 dB. Uncoded BPSK needs 6.79 dB for BER 1e-3.

**Codes from sim/fec.py at BER 1e-3 (hard decisions, Monte Carlo, interpolated):**
- Hamming(7,4), R = 0.571: p* = 0.0104 (BSC), capacity there 0.9165, gap 0.345 bit; Eb/N0 6.70 dB, coding gain only 0.09 dB over uncoded, 4.64 dB from the hard-decision limit.
- Convolutional K = 3, r = 1/2: p* = 0.0266, capacity there 0.8232, gap 0.323 bit; Eb/N0 5.73 dB, coding gain 1.06 dB, 3.96 dB from the hard-decision limit and 5.54 dB from the BPSK soft limit.
- Capacity allows crossover 0.0876 (R = 4/7) and 0.1100 (R = 1/2); the codes are 8x and 4x below that.

**Erasure code (n,k) over hop losses, best rate with block failure <= 1e-3, i.i.d. erasures:** for eps = 0.2 (capacity 0.80): n = 8: R 0.250 (gap 0.55); 13: 0.385 (0.415); 16: 0.438 (0.363); 32: 0.562 (0.238); 64: 0.641 (0.159); 128: 0.688 (0.113); 255: 0.718 (0.082). eps = 0.1 at n = 255: R 0.839 (gap 0.061). The binomial formula was checked against the real `erasure_encode/erasure_decode`: failures 0.2063 vs 0.1941 (8,5, eps 0.3), 0.2103 vs 0.2031 (8,6, eps 0.2), 0.0907 vs 0.0991 (13,9, eps 0.2) with 3000 trials each, i.e. within about 2 standard errors.

**Bursty loss** (Gilbert-Elliott, mean eps 0.2, n = 32, 200k blocks): best rate 0.562 (D = 1, k = 18), 0.062 (D = 5), 0.000 (D = 20). Spreading the codeword over every 5th (D = 5) or 20th (D = 20) slot restores 0.438. Interleaving depth equal to the mean dwell does not fully recover the i.i.d. figure (0.562).

Caveats: hard-decision decoding only; BER 1e-3 target is arbitrary; the conv Viterbi decoder is the one in sim/fec.py, run on 100k bits per point; capacity of the burst channel is still 1 - eps, the loss is finite-length.

---
## 6. Compressed-sensing spectrum sensing (`lab2/cs_sensing.py`, fig `cs_sensing.png`)

N = 256 bins, s occupied (|a| uniform in [1,2], random phase), m random measurements, OMP in numpy, exact-support recovery, 100 trials per point (about +-0.05 error near 0.5). SNR is for the weakest tone (|a| = 1) in the unitary basis.

**Noise-free-ish (40 dB), smallest grid m/N with P(exact) >= 0.9:** random sub-sampling: s = 3: 0.075 (m = 19), s = 4: 0.075 (19), s = 5: 0.10 (26), s = 6: 0.125 (32), s = 8: 0.15 (38), s = 12: 0.20 (51), s = 16: 0.30 (77), s = 24: 0.40 (102). Gaussian projections need more for s = 4 (0.10), 8 (0.20), 12 (0.30) and do not reach 0.9 for s = 24 by m/N = 0.4 (0.89). The ratio m / (s ln(N/s)) is 1.14 to 1.80 for sub-sampling.

**Noise (s = 5, sub-sampling):** at SNR 20 dB P = 0.49 (m = 26), 0.91 (38), 1.00 (51), 1.00 (77); at 15 dB 0.02, 0.17, 0.44, 0.85; at 10 dB at most 0.07; at 5 dB and below 0.00. So the compressed measurements need roughly 15 to 20 dB per-bin SNR (noise folding: all 256 bins' noise lands in m samples). Blind OMP (sparsity unknown, noise-level stopping) at m = 77: P(exact) 0.00 at 0 to 10 dB, 0.37 at 20 dB, 1.00 at 30 dB; mean false bins at most 0.02 per trial, so its failures are missed tones, not false alarms.

Caveats: on-grid tones, white known-level noise, no leakage or wideband interferers, complex IQ model, hopping signal and jammer tones treated identically.

---
## 7. Co-evolution of hop and jam strategies (`lab2/evolve.py`, fig `evolve.png`)

M = 13, one jammed channel per slot, game value 0.9177, maximum entropy 3.700 bits. 40 individuals per side unless stated.

- **A. Genome = probability vector, GA on mean delivery (5 seeds, 300 generations, last 150 averaged).** It does not converge to uniform. Generation 1: delivery 0.9174 and individual entropy 3.137 bits (random initial vectors). Afterwards individuals collapse to near-pure strategies: mean delivery 0.8502, instantaneous population entropy 0.298, time-averaged entropy of the population usage 1.209, individual entropy 0.281; best final defender worst-case delivery 0.1553 on average (single seeds 0.0517 to 0.5282) against the game value 0.9177. One seed sat on a single channel with delivery 0.944 because the jammer population never found it. Reason (my reading of the mechanics, not separately tested): a vector's fitness against a fixed opponent population is linear in the vector, so selection pushes to pure strategies and the two populations cycle.
- **A2. Defender fitness = mean of its worst 25% opponents (3 seeds, 150 gens).** Better but still not uniform: time-averaged entropy 2.508, 2.842, 2.985; best worst-case 0.056, 0.089, 0.739.
- **B. 4-state FSA defenders (ACK-driven) vs 4-state FSA jammers (see our last channel), 5 seeds.** Co-evolved delivery 0.9126. But a freshly evolved jammer population against the frozen best defender pushes its delivery down to 0.3517 on average (seeds: 0.399, 0.341, 0.120, 0.649, 0.250), so memory did not buy robustness in this setup.
- **D. Population = mixed strategy (pure-channel genomes, 500 per side, selection plus 2% mutation, 600 generations, last 300 averaged, 5 seeds), unrestricted jammer.** Delivery 0.9029 (value 0.9177), instantaneous entropy 3.373, time-averaged entropy 3.698 (near 3.700), maximum channel share 0.182 (uniform 0.077). So the average play converges to uniform while the instantaneous population still wobbles; the delivery stays 0.015 below the value because of the finite-population noise.
- **Restricted jammer (structure helps), D:** jammer can only emit on |W| channels. LP value 0.99 in each case (defender should avoid W). Evolved delivery |W| = 9: 0.9768, 5: 0.9824, 3: 0.9857, mass left on W 0.115, 0.040, 0.014; instantaneous entropy 2.352, 2.875, 3.015 (ideal log2(13-|W|) = 2.000, 3.000, 3.322, so the |W| = 9 case is unconverged). With the vector GA (A) and 3 seeds, delivery reaches 0.9900 for |W| = 5 and 3 with zero mass on W, but the defender collapses to one or a few channels (entropy 0.008 and 0.264), which is exploitable by a jammer that is not restricted. Structure helps only as long as the jammer's restriction holds.

Caveats: finite populations and generations, a stochastic and cycling process with no convergence proof; jammer limited to k = 1; seeds are few (5, or 3 for A2 and the vector-GA restricted runs); the GA hyperparameters were not tuned beyond the variants shown.

---
## What this adds to the plan
1. A secret hop schedule is worth far more than any code: capacity 0.9177 against 0.05 when the pattern is known (k = 1 of 13), and uniform hopping is the proven optimum against an equal-quality k-channel jammer (LP, 6 digits).
2. For control traffic the dangerous quantity is burst length, not mean delivery (module 1), and clock sync is cheap with a Kalman filter (module 2): guard 13.1 us at a 10 s beacon period against 195.5 us for reset-to-beacon.
3. A clock-skew fingerprint catches a keyed impostor with a different crystal after about 50 to 100 packets (0.943 to 0.987 at 1% false alarm) but not a matched clock.
