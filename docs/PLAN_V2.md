# Plan v2 (written 6 Oct). Software only until Kavin says hardware is allowed.
Viva story in three claims, each backed by a figure and a test:
1. Hopping beats a fixed channel (figs 2-5) and DS-SS wins on processing gain (fig 4): textbook, verified by Monte Carlo against theory.
2. The hop schedule must be keyed: a bare LFSR is broken in 8 to 9 hops (8 for 62.5 % of seeds, 9 for 37.5 %, mean 8.375; figs 8-9).
3. Learning and coding help only in specific conditions, and we measured where (figs 10-12, game.py).

## Workstreams, ranked
| # | Workstream | Output | Why |
|---|---|---|---|
| A | Realistic 2.4 GHz model: ESP-NOW channels 1-13 overlap (22 MHz wide, 5 MHz apart; only 1/6/11 are clean), Wi-Fi traffic on 1/6/11, fading, adjacent-channel leakage | sim/rf_model.py, re-run key results with an honest channel set | Biggest realism gap: our M=13 assumes independent channels. Effective M is maybe 3-6 unless we hop smartly. |
| B | Protocol timing model: slot length, channel-switch time, beacon period, drift in ppm, resync cost, re-acquisition | sim/timing.py, throughput vs hop rate plot | Answers spec decision 1 (hop rate) with numbers instead of a guess |
| C | Security pass: pairing, key derivation, authenticated beacons, replay window, spoofed-beacon desync attack and defence | sim/security.py, docs/THREAT_MODEL.md | Defence framing; makes claim 2 complete |
| D | Layer 3 in Verilog: LFSR PN generator, correlator, testbench, processing-gain waveform; synthesis numbers if yosys/Vivado is available | rtl/, rtl/tb/, docs/LAYER3.md | Ties to your VLSI/FPGA work; strong for the presentation |
| E | C reference code: hop generator + HMAC schedule + CRC8, golden vectors from Python, compiled and tested with gcc on the laptop | firmware/ref/ | Firmware becomes copy-paste later, zero risk to hardware now |
| F | Reproducible benchmark: one command regenerates every figure and table, fixed seeds, confidence intervals, CI on GitHub (runs the tests) | bench.py, .github/workflows/tests.yml | Reviewer-proof; also a good GitHub profile signal |
| G | Dashboard v2: WebSerial live source, session record/export, parameter sweeps, shareable report page | dashboard/ | Same page drives the hardware demo later |
| H | Writing: one-page viva sheet, 15 likely questions with answers, demo script, short report (6-8 pages) | docs/VIVA.md, docs/REPORT.md | Report prose stays yours: I give numbers and reasoning, you write the wording |

## Calendar (adjust to the real presentation date)
| Window | Work | Your time |
|---|---|---|
| 7 Oct | ICE test; log only | none |
| 8-10 Oct | A realistic RF model, B timing model; re-run key results | 20 min: choose hop set and hop rate |
| 11-13 Oct | C security, E C reference + golden vectors | 15 min review |
| 14-16 Oct | D Layer 3 Verilog + testbench (VLSID statement due 15 Oct: keep light) | 15 min |
| 17-20 Oct | F benchmark + CI, G dashboard v2 | 20 min |
| 21-27 Oct | NPTEL and PolarFire: docs/tests only | minimal |
| 28 Oct - 3 Nov | Hardware allowed: channel-switch time, per-channel baseline, loopback, 3-board demo using E and G | 1 h a day |
| 4-6 Nov | integration, H writing, demo rehearsal | 1-2 h a day |

## Risks
- Real 2.4 GHz is noisier than the model: mitigate with A and a pre-written measurement checklist for the first hardware hour.
- Time sync on ESP-NOW may be harder than the simulator suggests: B quantifies the budget; fallback is slower hopping with wider guard.
- Presentation date unknown: the plan holds if there are at least 3 weeks left; otherwise cut D and G.
- Legal: interference is only ever generated on our own test link at minimum power; never on other people's networks.

## Decisions needed from Kavin
1. Hardware allowed from 28 Oct (or earlier)?  2. Include Layer 3 Verilog in the demo?  3. Public or private repo for now?  4. Presentation date and course name.
