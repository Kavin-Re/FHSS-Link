# STORY: break it, fix it, prove it

Structured reasoning and numbers only. Put it in your own words; I deliberately did not write recitable sentences. Every number is in CLAIMS_vs_EVIDENCE.csv with its script and its limit. All of it is simulation, formal/simulation checking and synthesis estimates; there is no hardware.

## 1. Problem
* A fixed-frequency link under a narrowband tone is effectively lost: BER 0.24 at JSR 0 dB, 0.43 at 10 dB, Eb/N0 10 dB (docs/RESULTS.md; `python3 -m fhss_lab run` reproduces 0.238 / 0.427).
* Hopping over M channels caps the loss at about the fraction of slots on the jammed channel: BER roughly 1/M, saturating with jammer power (M=8 0.053, M=32 0.013 at JSR 10 dB); PDR 0.92 at M=13 with one jammed channel.
* That gain exists only while the schedule is secret. Information-theoretic backdrop (arXiv 1512.06645, in docs/LANDSCAPE.md): without shared randomness, hopping does not raise capacity against a power-matched jammer. So the real question is: what schedule generator keeps the secret, and at what cost?
* Packets, not bits: the unit that matters is delivery (PDR) and what happens when the attacker is allowed to learn.

## 2. Attack (break it)
* Attacker model (Kerckhoffs): knows the algorithm, sees which channel was used each slot, does not know key/seed; jams its prediction of the next slot.
* Target: 16-bit LFSR schedule (x^16+x^14+x^13+x^11+1, `state mod 13`).
* Result: pinned down after 8 observed hops for 62.5 % of the 65,535 seeds and 9 for 37.5 %, mean 8.375, exhaustive (40,961 + 24,574 seeds). Information floor log13(65,535) = 4.32 hops. At 1 kHz hopping that is milliseconds.
* Consequence in the link model: delivery 0.92 -> about 0.05, worse than a fixed channel against a static jammer.
* Other weak generators fall the same way (lab6 R5, HopBench): LCG-24 8 hops, xorshift32 9, MT19937 624 outputs, counter-mod and table schedules to n-gram/Berlekamp-Massey in 14-128 hops. HopBench scores: LFSR-16 20.4, LCG-24 22.9, Xorshift-16 21.6, Table-32 20.7, Counter-mod 16.8.
* Also attacked beyond the schedule (lab5/6/7/9, all models of my own link): control-plane (beacon) jamming 0.135 availability for the naive design; time pushing at 1 ppm (alarm at 39 s after guard violation at 32 s); a signal-contingent relay (BER 0.797 with keyed hopping alone); early-exit tag compare timing leak.

## 3. Fix
* Replace the LFSR with SipHash-2-4 (128-bit key, counter in, 64-bit digest) plus Lemire unbiased reduction to 0..12; an iterative engine, 1 SipRound per clock.
* Why this primitive: add/rotate/xor only, published test vectors, short-input PRF. Not a NIST/IETF cipher; the security argument rests on the PRF assumption (2^128 is the generic key-search bound, not a proof).
* Cost, said plainly: 12 clocks per hop (LFSR 1), 31,394 um2 / 8,364 GE / 461 flops vs LFSR 1,828 um2 / 487 GE: 17.2x. "Bits per kGE" favours the LFSR (32.9 vs 15.3), so it is the wrong metric alone; the point is that the LFSR's effective security is zero after 8-9 hops.
* Negative results kept: v2 lean (serialised) engine saves only 5.8 % / 4.9 % area for 3x / 5.7x latency; mod-13 folding shrinks the LFSR by 25.3 %; the approximate-adder correlator saves about 21-22 % static area but the switchable (ladder-driven) block is 13-16 % larger than an exact-only block, and power was not measured.
* Around the schedule: keyed schedule + adaptive layer with a uniform floor (game value 1 - 0.95/13 = 0.9177); MAC + rolling counter (0 accepted replays of accepted packets); multi-rendezvous beacons (availability 0.988 vs 0.135); degradation ladder (critical delivery mean 0.97 vs 0.55 vs 0.27 strawman cliff, paid for by dropping bulk).

## 4. Evidence (prove it)
| Layer | What | Number |
|---|---|---|
| Spec anchor | Python SipHash vs published vectors; independent re-implementation by the audit | paper vector 0xa129ca6149be45e5; 0 mismatches over 3,000 random pairs across 4 implementations |
| Simulation | RTL vs model, iverilog and Verilator | 60,000 + 20,000 + 20,000 + 2,000 + 3,000 + 3,000 hops, 0 errors; 692 retries exercised; LFSR 80,000 hops |
| Testbench quality | mutants | v1: audit's 11 fresh mutants caught; v2: 28/28 |
| Formal | SymbiYosys k-induction | 3 proofs (+ v2 wrapper proofs), safety/range only; cover at step 14 |
| Maths | Lemire exactly unbiased | 330,382,099 per channel; both chunks rejected 4.391e-18 |
| Statistics | randomness battery on RTL output | keyed: all p > 0.05, predictor 0.0759 vs 0.0769 chance; LFSR serial p 0.000, predictor 0.2356 |
| Synthesis | yosys 0.33 + abc, sky130hd | area/delay numbers above (two different netlists for area and delay) |
| Audit | adversarial read-only review (docs/AUDIT_WAVE1.md) | 21 numbered findings, none critical; no headline conclusion overturned; wording fixed in docs/CHANGES_8OCT.md |
| Software siblings | test counts today | lab4 36, lab5 56, lab6 11, lab7 65, ApproxKit 10 (+173 RTL by audit), GNSS-Sentinel 31, LifeLine C 288,113 checks + 26 Python, VCD-Studio 11 |

## 5. Limits (the list an examiner will find anyway)
* No hardware at all; no FPGA place-and-route; no power; no real RF/GNSS data; sky130 numbers are estimates and delay comes from a different (18-24 % larger) abc mapping than the area.
* Red-team results attack models I wrote with assumed leakage/fault/trojan/PUF parameters; samples are small (3 seeds, 12 trials, 3 masked trials, 3 keys in the default bench, 64 chips); several tests compare a model to its own formula.
* Formal properties are safety only; the PRF assumption is not proved; the retry path makes latency data-dependent with probability 4.4e-18.
* Key distribution, pairing, time sync and re-keying are out of scope (that is exactly where ExpressLRS was broken in 2022).
* Attacker sees channel indices only, perfectly, instantly: generous to the attacker on observation, generous to the defender on side channels and sync errors.
* Stale doc: FHSS-Link/README.md still says "PLANNING (no code yet)"; the HopBench CLI needs Python 3.12 (fails on the laptop's 3.10).

## 6. What is new vs the landscape (docs/LANDSCAPE.md) and what is not
Not novel, say so first: LFSR/weak-PRNG hop prediction (Praetorian's nRF24 write-up, about 9 bits effective randomness on a commercial device); keyed hop engine in RTL (cirradio: Zynq + AD9361, AES-256 hop sequencing, 128 tests); decoy channels (arXiv 2103.14056); ML jammer detection on simulated data (JamShield, public datasets exist, so my 99 % has low standalone value); GPS acquisition and spread-spectrum watermarking (textbook). Mature real-world baseline: ExpressLRS.

What the landscape page lists as open, and what I can honestly point to:
1. Reproducible evidence on when hopping helps and when it does not, theory + Monte Carlo side by side: docs/RESULTS.md, lab5 game check, lab6 negative results. Hardware numbers are still missing, so this is half of the stated opening.
2. Hopping on ESP32/ESP-NOW: not done; no data.
3. A design-attack-fix methodology packaged as a runnable suite: lab4-lab9 + HopBench + audit trail. This is the strongest claim, as a packaging and honesty contribution, not as a new attack or new primitive.
Smaller honest contributions: the exhaustive 8/9-hop distribution; an auditable area/latency table for the same function in four microarchitectures (v1, lean 64, lean 32, LFSR folded) including the cases that did not help; quantified cost of making an approximate correlator switchable; a benchmark whose own caveats say a 100 means "nothing found".

## 7. How the wording survived the audit (use this if asked how you know)
Things I would have said and the audit showed were wrong, now fixed in docs: "about 9 hops" (8.375 exact); "chance level" for 2 of 24 masked bytes (p about 0.004); "every adder BER >= 0.17" (LOA(5) is 0.067); "60 of 128 key bits guessable" (60.2 bits remain, about 68 known); "one mapping script" for area and delay; "run_tests.sh runs every test" (it ran 10 files; now more, and the RTL tools are explicitly excluded); EXP3 "not a best response" on a +0.001 difference.

## 8. What would make this stronger (ranked by value for the next viva, with cost)
1. Two-board ESP32 PDR run, jammed vs unjammed, with logs and the same loss model fitted to it. Turns "simulation" into one measured point; also gives hop dead-time. About 1-2 days. Biggest gap.
2. One FPGA flow report (Vivado/Radiant) for the keyed engine: LUTs, FFs, Fmax from a real timing report; replaces the abc ns numbers. Half a day if the board toolchain exists.
3. Single-netlist synthesis: re-run area and delay from one mapping (or report both from the same run) and run OpenROAD/place-and-route once. Fixes the largest standing synthesis caveat.
4. More keys and seeds: random keys in the RW=8 and M=37 benches, 20+ trials for masked CPA stage 2, 30 seeds in lab5; ship `scripts/mutate.sh` so the mutation claim is reproducible. Cheap, removes audit items.
5. A real side-channel or fault measurement on a microcontroller SipHash (even a software one) to test the Hamming-weight assumption behind lab4.
6. Replace circular tests (lab6 R7/R8, TMR, formula-vs-formula) with independent checks or label them as consistency checks.
7. Re-derive lab4 overhead percentages from the synthesised 8,364 GE instead of the 6,890 GE proxy.
8. Real data: replace GNSS-Sentinel's synthetic logs with a recorded log; use one public jamming dataset (JamShield/IEEE DataPort) for the classifier.
9. Make the repo reproducible on a fresh machine: remove hard-coded cloud paths (formal/sby, synth.sh, refsim.py), fix HopBench for Python 3.10 or document 3.12, update README line 2.
10. Power: even a switching-activity estimate would test the approximate-correlator ladder argument that currently has no energy evidence.
