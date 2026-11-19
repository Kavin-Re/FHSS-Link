# Round 2 results (6 Oct). Every number below is printed by the script named in the heading; JSON in sim/figures/. Simulation only, no hardware.

## #13 Data in the hop, FH-MFSK (sim/fhmfsk.py)
Symbol s sent on channel (k_t + s) mod M with secret offset k_t; M=16, Es/N0 12 dB, 4 bits per slot, symbol error rate 0.0022 without a jammer.
- A tone jammer breaks it fast: SER 0.47 at JSR 0 dB, 0.94 at 6 dB, with or without the key. The keyed offset does NOT improve reliability.
- What the key does buy is integrity: an attacker who jams channel 5 to force the receiver to read symbol 5 succeeds 100% of the time on plain M-FSK and 6.2% (about 1/16) with the keyed offset. The jammer can corrupt but cannot choose what the receiver reads.
- Detecting two strong peaks lets the receiver flag an erasure instead of guessing: at JSR 6 dB 84% of symbols are flagged, 10% remain undetected errors. Pair this with the erasure code across slots (fec.py).
- Verdict: high rate (4 bits/slot) but fragile; useful in a clean or lightly jammed mode of the ladder, not in a jammed one.

## #14 Key from the air (sim/plkg.py)
Alice and Bob measure the same fade with independent noise; guard-band quantiser, Hamming(7,4) syndrome reconciliation, 16-bit hash check per 112-bit segment, 3000 measurements per trial, 20 trials per row.
| SNR | bits kept | raw disagreement | segments agreeing | key bits before privacy amplification | Eve's agreement |
|---|---|---|---|---|---|
| 5 dB | 1560 | 6.9% | 3.8 of 13.4 | 420 | 49.5% |
| 10 dB | 1708 | 0.8% | 14.6 of 14.8 | 1630 | 50.0% |
| 15 dB | 1854 | 0.0% | 16.0 of 16.0 | 1792 | 50.0% |
Reconciliation leaks 3 bits per 7 plus 16 per segment (about 700-900 bits at 10-15 dB); 1600-1800 raw bits therefore leave several hundred secret bits, enough for a 128-bit key. Eve, with an independent fade (outside about half a wavelength, 6 cm at 2.4 GHz), agrees with 50%, i.e. guesses. Assumptions: reciprocal channel, independent fades per sample (obtained by hopping across channels/time), Eve not near either node.

## #15 Interferer localisation (sim/locate.py)
RSSI at K boards, 20 m x 20 m room, path loss exponent 2.5, 200 trials. Median / 90th percentile error:
| boards | shadowing 0 dB | 2 dB | 4 dB | 6 dB |
|---|---|---|---|---|
| 3 | 0.15 / 1.45 m | 2.49 / 5.77 | 3.71 / 7.51 | 4.80 / 10.24 |
| 4 | 0.13 / 1.18 | 1.92 / 4.52 | 3.15 / 6.38 | 4.10 / 8.62 |
| 6 | 0.11 / 0.26 | 1.07 / 2.30 | 1.85 / 3.93 | 2.73 / 5.84 |
With 3 dB shadowing and a wrong path-loss exponent (2.0, 3.0, 3.5 vs 2.5 true), 4 boards still give 2.4-2.8 m median. Honest reading: indoors, with real shadowing, this finds the area (a few metres), not the object; the third board gives a rough bearing at best. More boards help more than a better model.

## #16 Low probability of detection (sim/lpd.py)
Total-band SNR (dB) at which an energy-detecting eavesdropper detects us with probability 0.9 (1000 samples, 1% false alarm, 13 channels): fixed channel with the eavesdropper tuned to it -20.4 dB; FH or DS-SS seen by a wideband radiometer -9.2 dB; DS-SS seen on one channel -9.2 dB. Spreading therefore buys 10 log10(13) = 11.1 dB of invisibility against an eavesdropper who does not know where to listen; an FH signal on a one-channel scanner is present only 1/13 of the time, so one window cannot detect it at any SNR. Longer observation erodes this: needed SNR falls from -3.8 dB (100 samples) to -19.4 dB (100,000 samples). Gaussian approximation vs Monte Carlo at -12 dB: 0.378 vs 0.402.

## #17 Interactive "Jam the Link" (dashboard/index.html)
New jammer option Manual: click channel rows on the waterfall to toggle jamming; a score counts slots with delivery below 50%. Tested headless: jamming 8 of 13 channels, keyed hopping scores 1560 bad slots in 8 s (delivery 36%), the AFH defender recovers to 94% with score 88.

## #18 + #29 Degradation ladder with explanations (sim/ladder.py, logs/ladder_decisions.txt)
Scenario 10,000 slots: clean, static 2 channels, wideband 8 of 13, random 4 per slot, clean. Critical delivery / bulk goodput (packets per slot):
| policy | clean | static-2 | wide 8 of 13 | random-4 |
|---|---|---|---|---|
| always NORMAL | 0.99 / 0.89 | 0.83 / 0.75 | 0.40 / 0.38 | 0.75 / 0.63 |
| always ADAPT | 1.00 / 0.89 | 1.00 / 0.88 | 1.00 / 0.86 | 0.96 / 0.59 |
| always CODED | 1.00 / 0.51 | 1.00 / 0.49 | 0.94 / 0.15 | 1.00 / 0.43 |
| SURVIVAL | 1.00 / 0.00 | all 1.00 / 0.00 |
| LADDER | 0.99 / 0.88 | 1.00 / 0.88 | 1.00 / 0.86 | 1.00 / 0.44 |
The ladder keeps the critical channel at 1.00 in every phase and tracks the best bulk goodput except against random jamming, where it pays for coding (0.44 vs 0.59 for plain ADAPT). Finding: the first version flapped between NORMAL and ADAPT because ADAPT hides losses by avoiding channels; fixed by not downgrading while the learner still avoids channels (6 switches per run on average). Every switch is logged with its reason, e.g. "NORMAL -> ADAPT because loss 8% over the last 50 attempts; most-hit channels [0, 1]".

## #19 Relay under jamming (sim/mesh.py)
Wideband jammer (8 of 13 channels, low power) near the sink: direct A-B delivery falls from 1.00 to 0.385 as the jammer moves next to B (x=28 m); the relay path A-R-B delivers 0.50 goodput (two slots per packet) and is chosen. Note: a single-channel jammer costs every link only 1/13 wherever it stands, so routing matters only against wideband interference.

## #20 Energy-depletion attack (sim/energy.py)
Battery drain per packet period (1.30 clean): naive retry 2.51 at 50% loss, 4.34 at 80%, 5.88 at 95% (4.5x). Sleep-and-probe cuts it to 1.42 at 95% but delivers 0.05 instead of 0.23: it protects the battery, not the data. Use it only when the classifier says the interference is not going away.

## #21 Protocol model checker (sim/modelcheck.py)
Exhaustive search of 72 reachable states. Protocol v1 (resync only by hearing a packet) has 19 dead states from which synchronisation can never return, matching the PDR=0 case seen earlier in link_sim. Protocol v2 (after 3 missed slots, park on the rendezvous channel and wait for a beacon every 4 slots) has 0 dead states for guard 1, 2 and 3. Assumes losses are not permanent and drift has a fixed sign.

## #22 Randomness tests on schedules (sim/randtests.py, 20,000 hops, M=13)
| schedule | chi-square p | serial correlation p | runs p | next-hop predictor accuracy (chance 7.7%) |
|---|---|---|---|---|
| LFSR16 | 0.79 | 0.000 (fails) | 0.28 | 23.6% |
| keyed PRF | 0.41 | 0.47 | 0.53 | 6.7% |
| logistic map | 0.000 | 0.000 | 0.000 | 64.5% |
| Mersenne Twister | 0.23 | 0.38 | 0.95 | 6.8% |
A generic order-3 predictor that knows nothing about the generator already predicts the LFSR three times better than chance, and the chaotic map eight times better.

## #23 Digital twin (sim/twin.py)
A static per-channel loss model fitted from a 12,000-slot blind-hop log (parsed through the serial format) predicts the delivery of other policies on an environment with bursty Wi-Fi on channels 1, 6, 11 within 1 point: blind 0.891 vs real 0.895, AFH 0.894 vs 0.902, Thompson 0.951 vs 0.959, Thompson+floor 0.943 vs 0.949. The twin slightly under-predicts adaptive policies because it ignores the burst timing they exploit.

## #24 Mission scenario (sim/mission.py, fig 13)
Patrol along 120 m with an interferer 25 m off the road at 70 m. Fraction of the path with delivery >= 0.8: fixed 0.28, FH 13 channels (2 jammed) 0.58, DS-SS Gp=32 0.45, no interferer 0.64. DS-SS beats FH while the patrol is moderately far (x=50 m: 0.99 vs 0.85) but collapses at closest approach (x=70 m: 0.006 vs 0.82). FH degrades gracefully, DS-SS fails abruptly once the jammer exceeds the processing gain.

## #25 Adversarial classifier test (sim/advclass.py)
Evasive on/off jamming defeats the classifier trained on constant jammers: accuracy 1.00 at duty 100%, 0.73 at 50%, 0.60 at 30%, 0.40 at 15%. Training with duty-cycle augmentation lifts these to 0.97, 0.95, 0.83, 0.63; longer windows (600 slots) at 15% duty reach 0.82. The evasion has a price for the attacker: loss caused falls from 0.32 to 0.06. (Simulated windows only.)

## #27 Safety guard (sim/safety.py, 10/10 tests in test_safety.py)
Policy logic for the interference node: authenticated time-limited token from the owner's board, own-link channel set, power cap, 10% duty cap over 10 s, 2 s burst cap, kill switch, every decision logged. In the test, 50 back-to-back requests over 5 s yield 10 allowed emissions. The same rules go into firmware later.

## Not done
- #26 spectrum analyser and #28 opportunistic timing need the boards.
- #30 reusing Layer 3 RTL in the PolarFire entry: Layer 3 does not exist yet and the contest rules must be checked first (the toolchain iverilog/verilator/yosys was not found on this laptop either).
