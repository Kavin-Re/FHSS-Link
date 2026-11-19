# UMBRELLA INDEX (state of the files on 8 Oct 2026, read from the laptop while other sessions were still editing)

Everything here is simulation, model-checking, synthesis estimate or software. No hardware has been built or measured anywhere. Excluded on purpose: PolarFire-VibMonitor, Approximate-SAD. Root: `~/Github_projects/Projects/`.

Status words: RAN = I re-ran it on the laptop today; AUDIT = re-run by the audit session (docs/AUDIT_WAVE1.md) in the cloud because the laptop has no RTL tools; STORED = outputs exist, not re-run by me. The laptop has Python 3.10.12, numpy 2.2.6, matplotlib, gcc, make, node. No iverilog, yosys, verilator, pytest.

Laptop-side results today (parallel runs, so times are inflated): FHSS `run_tests.sh` (old 10-file version) 10/10 PASS 55 s; lab4 36/36; lab5 56/56; lab6 11/11; lab7 65/65; ApproxKit 10/10; GNSS-Sentinel 31 OK; VCD-Studio 11 OK; LifeLine C 288,113 checks 0 failed + Python 26 OK; hop_model selftest True. `run_tests.sh` was extended during the day (see docs/CHANGES_8OCT.md); I did NOT get a completed run of the new version (my background run was killed after two entries), so its full pass state is unverified; the individual suites it calls were each run and passed.

## 1. FHSS-Link (core project)

Purpose: show, in simulation, when frequency hopping helps against interference, how a hop schedule gets attacked, and what fixes it. Design, attack, fix, evidence.

| Path | Purpose | Status | Run | Tests | Claim entry points |
|---|---|---|---|---|---|
| `sim/` | core simulators: BER/PDR, link, LFSR and keyed schedules, attacker, adaptive policies, EXP3 game, FEC, serial protocol, ladder, mesh, twin, safety | RAN (via run_tests.sh) | run scripts from inside `sim/` (`run_attack.py` writes into `sim/figures`, so it overwrites existing figures); no-write quick look: `python3 -m fhss_lab run` | `sim/test_*.py`, `modelcheck.py` | docs/RESULTS.md, docs/RESULTS_ROUND2.md |
| `fhss_lab/` | command-line wrapper: `run`, `emulate`, `classify`, `bench` | RAN (`run` 0.7 s, `classify` 1.4 s) | `python3 -m fhss_lab --help` | `bench` = run_tests list | docs/INDEX.md |
| `lab/` | GPS acquisition, spread-spectrum watermark, audio FH, modulation classifier, ICE_Lab.html study page | RAN (test_batchA) | `python3 test_batchA.py` | yes | docs/RESULTS_R3_A.md |
| `lab2/` | networked control, clock Kalman, fingerprinting, game LP, capacity, compressed sensing, evolution | RAN (test_batchB) | `out_*.txt` stored | yes | docs/RESULTS_R3_B.md |
| `lab3/` | survival codec, hash chain, LMS cancel, Wi-Fi survey tooling, venue model, synthetic dataset | RAN (test_batchC) | `wifi_survey.sh` needs a real scan, not done | yes | docs/RESULTS_R3_C.md |
| `lab4/silicon/` | red team on the hop engine as a MODEL: power CPA and masking, fault injection (TMR/parity), trojan detection, PUF key | RAN 36/36 (26 s in parallel, ~7 s alone) | `bash run_all.sh` (~6 min) or `python3 run_tests.py` | 36 | `RESULTS_SILICON.md` section 5 claim-to-script map; `results/*.json` |
| `lab5/` | approximate correlator, fast-hop jammer, relay attack, soft-set hopping, replay + MAC, graceful degradation, RM+ game check | RAN 56/56 (14-45 s) | `python3 run_all.py [exp1..exp7]` | 56 | `RESULTS_LAB5.md`; `outputs/*.json` |
| `lab6/` | red-team batch R1-R8: bandit poisoning, learning rate, beacon jamming, time push, PRNG graveyard, key-from-air drain, myopic jammer, scorecard | RAN 11/11 (25-58 s) | `python3 run_all.py` (~1 min) | 11 | `RESULTS_LAB6.md` claim table; `outputs/scorecard.md` |
| `lab7/` | "beyond the jammer": timing leak, carry-off spoofing, parser fuzzing, Dolev-Yao model check, permutation leak, traffic analysis, electric-fish rule, red/blue sandbox | RAN 65/65 | `python3 run_all.py` | 65 | `RESULTS_LAB7.md` |
| `lab8/` | second red-team batch: jammer placement + relay, swarm, energy-optimal jammer, capture effect, honeypot channels, moving-target link (E12-E17) | WRITTEN during this build by another worker (RESULTS_LAB8.md appeared while I was reading); STORED, not re-run by me | `python3 e12_placement.py` ... `e17_moving.py`; `python3 test_lab8.py` (about 3 min) | 14 stated in RESULTS_LAB8.md | `lab8/RESULTS_LAB8.md` claim table; every constant of the spatial model is an assumption |
| `lab9/` | batch 2 (B1, B4, B9, B10, B11, B14, B21): trojan hunt, CPA, fingerprint forgery, adversarial classifier, poisoned logs, crypto DoS, max-entropy hopping | WRITTEN during this build by another worker; STORED, not re-run by me | `python3 test_lab9.py` | stated in RESULTS_LAB9.md | `lab9/RESULTS_LAB9.md` |
| `rtl/hop_engine/` | v1 keyed hop engine (SipHash-2-4 + Lemire) and 16-bit LFSR reference in Verilog; Python model; vectors; formal; synthesis | model scripts RAN; RTL sims/formal/synth AUDIT (7/7 iverilog, 4/4 Verilator, 3 proofs + cover) | `python3 model/hop_model.py`, `unbias_check.py`, `randcheck.py`, `lfsr_hops_exhaustive.py` (80 s) work on the laptop; `scripts/run_all.sh` needs iverilog/verilator/yosys/z3/SymbiYosys (cloud paths hard-coded) | benches self-checking | `README.md`, `results/SUMMARY.txt`, `results/randcheck.txt`, `results/*.log.txt` |
| `rtl/hop_engine_v2/` | lean (serialised) keyed engine, LFSR with mod-13 folding, AXI-lite/beacon resync wrapper | STORED (wave 2 logs); not re-run by me | `rtl/wave2/run_all.sh` (cloud tools) | 28 mutants in `results/mutation.txt` | `rtl/wave2/RESULTS.md` section 1 |
| `rtl/approx_correlator/` | ladder-driven approximate-adder DS-SS correlator RTL built from ApproxKit cells | STORED | `rtl/wave2/run_all.sh` | 7 configs x 4,000 frames; SAT miter 90/90 | `rtl/wave2/RESULTS.md` section 2; `results/SUMMARY.txt`, `ber_vs_snr.png` |
| `rtl/wave2/` | index of wave-2 RTL claims (claim -> evidence) and the run-all script | STORED | `QUICK=1 ./run_all.sh` | n/a | `RESULTS.md` |
| `dashboard/index.html` | live dashboard: simulator or log replay, manual jam mode | opens from file:// (headless Chromium: no console errors, no external requests) | open in a browser | author checked headless | docs/RESULTS.md (Sat) |
| `docs/` | plans, results notes, landscape, audit, change log, explainer.html | read | - | - | `LANDSCAPE.md`, `AUDIT_WAVE1.md`, `CHANGES_8OCT.md`, `RESULTS*.md` |
| `firmware/` | ESP32 firmware stubs | not touched; no hardware run | - | - | `firmware/README.md` |
| `docs/defence/` | this pack | new | open `index.html` | - | - |

Known stale item: `FHSS-Link/README.md` line 2 still says "PLANNING (no code yet)" while the repo is full of code. Say so before an examiner finds it.

## 2. Sibling projects

| Project | Purpose | Status | Run | Tests | Claim entry points |
|---|---|---|---|---|---|
| `ApproxKit/` | Python bit-accurate approximate adders/multipliers, error metrics, Pareto explorer, Verilog units, RTL regression | RAN 10/10; RTL regression 173/173 AUDIT | `python3 tests/test_units.py`; `python3 examples/demo_apps.py` (8 s, rewrites results/apps_*) ; `python3 scripts/rtl_regress.py --out build --synth` needs iverilog+yosys | 10 + 173 | `README.md` Results section; `results/rtl_synth_n8.csv` |
| `VCD-Studio/` | single-file offline VCD waveform viewer (`index_final.html`), `vcd_stats.py`, demo VCDs from iverilog sims | RAN 11 tests; viewer opens headlessly with no console errors and no external requests; I did not drive Open .vcd | open `index_final.html`; load `demos/hop_engine.vcd` | `tests/test_vcd_stats.py` 11; `tests/test_viewer.py`, `smoke.py` not run | `out/*.png` screenshots |
| `HopBench/` | benchmark that scores hop schedules against 11 simulated attackers; "Break the Hop" browser game | stored results present; **CLI does not start on the laptop (Python 3.10: SyntaxError in `hopbench/report.py` line 90, an f-string with a backslash needs Python 3.12)**; `test_stats` and `test_schedules` pass, `test_report_cli` not run | `python -m hopbench run --quick --out /tmp/hb` on Python >= 3.12; or open `break_the_hop/index.html` | 31+ unit tests | `results/results.md`, `leaderboard.csv`, `radar.png` |
| `GNSS-Sentinel/` | passive GNSS interference/spoofing indicator toolkit on synthetic logs, CSV/NMEA input, offline HTML dashboard | RAN 31 tests; stream demo 7 s; full evaluation STORED | `python -m gnss_sentinel stream examples/meacon.csv --quiet` | 31 | `README.md` Limits; `results/results.md` |
| `LifeLine-Mesh/` | design + C99 reference + simulator for an infrastructure-less text/SOS mesh (custody forwarding, priority, SipHash MAC) | RAN: `make test` 288,113 checks 0 failed; 26 Python tests OK; sweeps STORED | `cd c && make test`; `cd python && python3 -m unittest discover -s tests` | 26 + C | `results/results.md`; `docs/PROTOCOL.md` |

## 3. How the pieces connect (the umbrella story)

L1 resilient link (sim/, lab5 fast-hop and graceful degradation) -> L2 trust (keyed schedule, MAC, replay window, lab6 control-plane) -> L3 silicon corner (rtl/hop_engine, hop_engine_v2, approx_correlator, ApproxKit cells, lab4 red team of the engine as a model) -> L6 assurance (HopBench scoring, formal and mutation checks, VCD-Studio to look at waveforms). GNSS-Sentinel and LifeLine-Mesh are sibling corners (awareness, mesh), not part of the FHSS claims.

## 4. Where to look for what

| If asked about | Open |
|---|---|
| why not an LFSR | `rtl/hop_engine/results/lfsr_hops_exhaustive.txt`, `sim/figures/8_lfsr_break.png` |
| is the RTL right | `rtl/hop_engine/results/sim_iverilog.log.txt`, `formal.log.txt`, `model/hop_model.py` |
| what does it cost | `rtl/hop_engine/results/SUMMARY.txt`, `rtl/hop_engine_v2/results/SUMMARY.txt` |
| side channels, faults, trojans, PUF | `lab4/silicon/RESULTS_SILICON.md` |
| what was found wrong | `docs/AUDIT_WAVE1.md`, `docs/CHANGES_8OCT.md` |
| what exists already | `docs/LANDSCAPE.md` |

## 5. Not done / open at time of reading
No hardware of any kind; no FPGA place-and-route; no sky130 layout; no power numbers; no real RF or GNSS data; lab8 unfinished; audit items listed as "Not fixed" in CHANGES_8OCT.md (ApproxKit docs, 6,890 vs 8,364 GE baseline, self-fulfilling tests, small sample sizes, cloud paths) remain unless later changed.
