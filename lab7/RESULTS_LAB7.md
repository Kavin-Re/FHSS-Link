# Lab 7: Beyond the jammer (simulation only, defensive/educational)

Scope: models and our own test setup only. No hardware, no real network or system access. Python + numpy + matplotlib.
Run: `python3 run_all.py` (scripts expect the project's `sim/` folder next to `lab7/`, or set `FHSS_SIM`). Tests: `python3 test_lab7.py` (65/65 checks pass).
Idea numbers are those of docs/BEYOND_IDEAS.md. Skipped: #2 (Approximate-SAD, excluded by request), anything PolarFire, and the 14 ideas not selected for this batch (1, 3, 4, 7-11, 14, 17-19, 21, 22).

| ID | Claim (key number) | Script | Figure | Output |
|----|--------------------|--------|--------|--------|
| B5 timing side channel | Early-exit tag compare: at sigma/delta=2, n=128 repeats/guess gives 90% forgery in 262144 queries (vs 2^64 brute force); constant-time compare stays at chance | b05_timing.py | figures/b05_timing.png | outputs/b05_timing.json |
| B6 carry-off spoofing | Innovation test alarms before 50 m error for drag rates down to 0.5 m/s (OCXO-like clock) or 1.0 m/s (TCXO-like); slower drags evade inside the 540 s window; false alarm 0.007 | b06_carryoff.py | figures/b06_carryoff.png | outputs/b06_carryoff.json |
| B12 parser/CRC fuzzing | 120000 inputs: original parser accepted 16529 non-canonical and 24333 out-of-range lines (strict parser 0/0), 0 crashes; CRC-8 catches all bursts <=8 bits and all odd-weight errors, but 0.32% of 2-bit errors 127 bits apart are CRC-invisible | b12_fuzz.py | figures/b12_fuzz.png | outputs/b12_fuzz.json |
| B13 Dolev-Yao model check | 137242 attacker sequences (depth 6) on the real Guard: S1 violated (shortest trace 5 actions, emission on authorisation 8 s old vs 7 s bound); challenge-response fix: 0 violations over 299592 sequences | b13_dolevyao.py | figures/b13_dolevyao.png | outputs/b13_dolevyao.json |
| B15 permutation-epoch leak | Attacker guess 0.244 vs 0.078 iid (3.12x, theory 0.245); keyed guard(L=6,W=26) holds 0.196 at max gap 26 slots | b15_permleak.py | figures/b15_permleak.png | outputs/b15_permleak.json |
| B16 traffic analysis | Undefended leak 0.76 of 2 bits; padding alone 0.50 bit at 174% cost; <0.05 bit needs pad+cover T=48 at 333% extra airtime | b16_traffic.py | figures/b16_traffic.png | outputs/b16_traffic.json |
| B20 electric-fish JAR | Vs static jammer JAR 0.990 vs Thompson 0.979; vs tracking jammer JAR collapses to 0.052, JAR+eps 0.872; worst case JAR 0.052, JAR+eps 0.441, Thompson 0.777 | b20_fish.py | figures/b20_fish.png | outputs/b20_fish.json |
| B23 red/blue loop | 6 rounds, 116 logged actions, hash chain valid, 4 hostile submissions refused, sockets blocked; blue converged to uniform hopping with worst case 0.845 = game value 0.845 | b23_redblue.py | figures/b23_redblue.png | outputs/b23_redblue.json, outputs/b23_referee_log.jsonl |

Tests for every row: test_lab7.py (grouped by ID, `PASS B..` lines).

## Honest caveats
- B5: timing noise is a Gaussian model; real MCU jitter, interrupts and the network path will differ. Query counts are model outputs, not measurements.
- B6: simplified 1-D tracking loop with a synthetic clock; thresholds tuned on that model. Drags slower than the limit are not detected, only bounded by the window.
- B12: the fuzzer targets our own parser model; a 0.32% CRC-invisible 2-bit class is a property of the polynomial period, not a parser bug. Strict parser still shows a few silent corruptions that a CRC cannot catch (digit-level edits that keep the checksum).
- B13: bounded model checking (depth 6, abstract time steps), not a proof. Result holds for the modelled attacker actions only.
- B15: assumes the attacker knows the epoch structure; theory and simulation agree, fix trades gap length against guess probability.
- B16: classifier/MI estimates from synthetic traffic classes; plug-in estimator has a floor (~0.005 bit, shown by a shuffled-label control).
- B20: the fish rule loses to a jammer that tracks it (honest failure); dither fixes much of it but the worst case stays below Thompson.
- B23: the "agents" are scripted program generators inside a validated DSL, not live LLM agents; the sandbox blocks sockets in-process and a static audit checks imports, which is a guard rail for this simulator and not a security boundary.
