# FHSS-Link RTL wave 2 - RESULTS (claim -> evidence)

Scope: simulation + yosys/sky130 synthesis estimates + formal only. No hardware, no place and route, no timing sign-off, no power numbers.
Tools (cloud container): iverilog 12.0, Verilator 5.020, yosys 0.33, z3 5.1, SymbiYosys (upstream python sources + yosys 0.33), python3/numpy.
Re-run everything: `wave2/run_all.sh` (`QUICK=1` skips synthesis and the BER Monte Carlo). Last run log: `wave2/run_all.log`.
Paths below are relative to `FHSS-Link/rtl/`. Every number in this file is copied from the cited file; nothing is typed from memory.

## 1. hop_engine_v2

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 1.1 | Lean keyed engine (`hop_keyed_lean`, DW=64 and DW=32) is bit-exact against the Python model (SipHash-2-4 + Lemire) | PASS, 0 channel errors, 0 digest errors: default M=13 60000 hops (3 keys, incl. 2^56 slot wrap) + 3000 digests; RW=8 NCH=1 20000 hops (692 with retry); RW=8 NCH=4 20000 hops; M=37 and M=16 3000 hops each (DW=64); same M=13/RW=8 sets for DW=32 | `hop_engine_v2/results/sim_iverilog.log`, `model/hop_model.py`, `tb/tb_hop_keyed_lean.v` |
| 1.2 | LFSR with mod-13 folding (`hop_lfsr_fold`, FV=0 and FV=1) equals the v1 LFSR | PASS: all 65535 non-zero states exhaustively (0 errors) + 4 seeds x 20000 hops vs Python (0 errors), both FV | `hop_engine_v2/results/sim_iverilog.log`, `tb/tb_hop_lfsr_fold.v` |
| 1.3 | Keyed engine + beacon resync wrapper with AXI-lite-style registers (`hop_sync_axil`: key load, slot counter, status, beacon lock/drift, holdover) matches a register-level Python model | PASS DW=64 and DW=32: 1976 ops, 1929 checks, 204 writes, 783 reads, 894 hops, 0 mismatches, 0 handshake-monitor errors | `hop_engine_v2/results/sim_iverilog.log`, `model/wrap_model.py`, `tb/tb_hop_sync_axil.v`, register map in the header of `rtl/hop_sync_axil.v` |
| 1.4 | The testbenches can actually fail | 28 hand-made bugs (15 engine, 10 wrapper, 3 LFSR fold) all caught; unmutated baseline passes | `hop_engine_v2/results/mutation.txt` |
| 1.5 | Verilator lint clean | `verilator --lint-only -Wall` and `iverilog -Wall`: no messages for DW=64/32, FV=0/1 (the RTL files carry `lint_off UNUSEDSIGNAL`) | `hop_engine_v2/results/lint.txt` |
| 1.6 | Area / latency trade-off vs v1 (same synth script, same machine) | see table below | `hop_engine_v2/results/SUMMARY.txt`, `results/synth/*_stat.txt`, `scripts/synth.sh` |

Synthesis comparison (yosys 0.33 + abc, sky130_fd_sc_hd tt_025C_1v80, no P&R, ideal clock; delay = abc `stime`, optimistic combinational estimate, NOT sign-off timing):

| design | sky130 cells | flops | area um2 | GE | delay ns | clk req->valid |
|---|---|---|---|---|---|---|
| v1 keyed (4 adders/clk) | 3903 | 461 | 31394 | 8364 | 5.57 | 12 |
| v2 lean DW=64 | 3567 | 463 | 29588 | 7883 | 4.35 | 36 |
| v2 lean DW=32 | 3664 | 465 | 29850 | 7952 | 4.11 | 68 |
| v1 LFSR16 plain `% 13` | 245 | 21 | 1828 | 487 | 8.04 | 1 |
| v2 LFSR fold FV=0 | 162 | 21 | 1366 | 364 | 3.67 | 1 |
| v2 LFSR fold FV=1 (no divider) | 172 | 21 | 1430 | 381 | 4.17 | 1 |
| v2 lean64 + AXI-lite/beacon wrapper | 5352 | 721 | 41570 | 11075 | 4.08 | 36 |
| v2 lean32 + AXI-lite/beacon wrapper | 5085 | 723 | 41532 | 11065 | 3.67 | 68 |

Reading: serialising the SipRound saves only 5.8 % (DW=64) / 4.9 % (DW=32) area because the 461 state/key/slot flops and the operand muxes dominate; latency grows 3x / 5.7x, so area x latency is 2.83x / 5.39x v1. v2 lean is the choice only if the shorter combinational path (-22 % / -26 % delay, abc estimate) or the smaller gate depth (132 / 71 vs 181 levels) is what limits the clock; it is not an area win. The mod-13 fold saves 25.3 % (FV=0) / 21.8 % (FV=1) of the LFSR block and cuts the abc delay by about half. The wrapper roughly adds 12 k um2 (258 flops: staged slot, beacon slot, counters, AXI registers).

## 2. approx_correlator (DS-SS despreading, N = 16 / 32 / 64, 6-bit samples, 1-bit chips)

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 2.1 | RTL is built from ApproxKit adder cells and bit-exact vs the Python model | PASS, 7 configurations x 4000 frames, 0 mismatches: N16 LOA3, N32 LOA3, N64 LOA3 (all with calibrated COMP), N32 TRUNC2 (COMP=48), N32 ETA3, N64 LOA4, N32 exact; frames in both modes (e.g. 2634 exact / 1366 approximate for N16) with random idle gaps and ladder changes | `approx_correlator/results/sim_iverilog.log`, `model/corr_model.py`, `tb/tb_approx_correlator.v` |
| 2.2 | `ak_cells/` are the unmodified ApproxKit RTL; `dual_adder` (runtime exact/approx) equals them | `cmp` identical to `approxkit/rtl/{exact,loa,trunc,eta}_adder.v`; SAT miter, all inputs, n = 6..11, K = 1..5, three types, ex=0 -> approx cell, ex=1 -> exact adder: 90/90 pass (negative control: a deliberately broken LOA carry gives 30 fails) | `approx_correlator/results/equiv_dual.log`, `formal/equiv_dual.sh` |
| 2.3 | Runtime mode input driven by the 2-bit ladder state | `corr_mode_ctrl`: ladder[1] = want exact (0 NORMAL, 1 ADAPT -> approximate; 2 CODED, 3 SURVIVAL -> exact), taken only at frame boundaries, DWELL=8 frames hysteresis before returning to approximate, reset state exact. Testbench: mode changes happen only in the clock after a frame (0 violations) and `ex_q` never changes between clock edges (0 glitches), 76-92 mode changes per run | `rtl/corr_mode_ctrl.v`, sim log |
| 2.4 | BER vs SNR from the Python model | 200000 bits/point, Eb/N0 0..10 dB, 6-bit ADC step 0.5, random code per bit, 25 adder variants incl. +comp, common random numbers; points with fewer than 30 errors are starred in the table | `approx_correlator/results/ber_vs_snr.{txt,csv,png}`, `ber_calibration.json`, `model/ber_model.py` |
| 2.5 | Verilator lint clean | 5 parameter sets, no messages | `approx_correlator/results/lint.txt` |
| 2.6 | Exact vs approximate area (yosys/sky130) | tables below | `approx_correlator/results/SUMMARY.txt`, `results/synth/` |

Area, static combinational core with the ApproxKit cells unmodified (COMP=0), um2 and change vs the exact core:

| N | exact | LOA1 | LOA2 | LOA3 | TRUNC2 | ETA3 |
|---|---|---|---|---|---|---|
| 16 | 4258 | 4119 (-3.3 %) | 3751 (-11.9 %) | 3374 (-20.7 %) | 3192 (-25.0 %) | 3257 (-23.5 %) |
| 32 | 8884 | 8852 (-0.4 %) | 7894 (-11.1 %) | 7051 (-20.6 %) | 6787 (-23.6 %) | 6744 (-24.1 %) |
| 64 | 18176 | 17445 (-4.0 %) | 15790 (-13.1 %) | 14169 (-22.0 %) | 13920 (-23.4 %) | 13786 (-24.2 %) |

Full block with the run-time switch (dual adders + mode controller + output registers), um2:

| N | ATYPE=0 block | LOA3 switchable | overhead of switchable vs ATYPE=0 block |
|---|---|---|---|
| 16 | 4927 | 5698 | +15.6 % |
| 32 | 9335 | 10692 | +14.5 % |
| 64 | 18373 | 20770 | +13.0 % |

BER (model), selected points, exact vs LOA+comp (full grid in `ber_vs_snr.txt`; no point below is starred except where marked):

| N | 4 dB exact | 4 dB LOA1+comp | 4 dB LOA2+comp | 4 dB LOA3+comp | 6 dB exact | 6 dB LOA2+comp | 6 dB LOA3+comp |
|---|---|---|---|---|---|---|---|
| 16 | 1.31e-02 | 1.39e-02 | 1.65e-02 | 3.21e-02 | 2.71e-03 | 4.55e-03 | 1.91e-02 |
| 32 | 1.31e-02 | 1.36e-02 | 1.52e-02 | 2.12e-02 | 2.38e-03 | 3.29e-03 | 7.73e-03 |
| 64 | 1.28e-02 | 1.29e-02 | 1.38e-02 | 1.65e-02 | 2.37e-03 | 2.94e-03 | 4.43e-03 |

Reading: bias compensation (COMP, calibrated on an independent seed) is essential; without it even LOA1 raises the 4 dB BER of N=32 from 1.31e-02 to 2.49e-02. The useful operating points are K=1..2 with COMP (BER at 4 dB = 1.01x..1.06x of exact for LOA1, 1.08x..1.26x for LOA2, N=64..16) at only -0.4..-13 % static area; LOA3 saves ~21..22 % area but even with COMP costs 1.29x (N=64) to 2.44x (N=16) BER at 4 dB. Because the exact mode must remain available (CODED/SURVIVAL), the switchable block is 13..16 % LARGER than an exact-only block: the area saving exists only for a fixed-approximate build. Any power saving (the usual argument for the ladder policy) was not measured.

## 3. Formal (SymbiYosys k-induction with z3; SBY upstream python + yosys 0.33)

| # | Property | Result | Evidence |
|---|----------|--------|----------|
| 3.1 | Engine: no illegal FSM state (`state <= S_RED`, `op <= 3`, `cnt < NCH`), `chan < M`, valid is a single-clock pulse after S_RED, slot counter +1 exactly on a hop, unchanged otherwise (engine inputs assumed to obey the idle-only protocol) | k-induction proof, DW=64, DW=32, and RW=8/NCH=1 | `hop_engine_v2/results/formal.log` (`keyed_lean.sby`) |
| 3.2 | Wrapper: the same protocol obligations ASSERTED (key/slot/req only while idle), one engine action per clock, `hop_chan < M`, only OKAY/SLVERR responses, SLVERR reads return 0, req only with key loaded and EN | k-induction proof DW=64 and DW=32 (engine invariants included, not assumed) | `hop_engine_v2/results/formal.log` (`sync_axil.sby`) |
| 3.3 | LFSR state never 0, `chan < 13`, and the fold equals `state % 13` for every 16-bit value (combinational equivalence asserted inside the induction step) | proof FV=0 and FV=1 | `hop_engine_v2/results/formal.log` (`lfsr_fold.sby`) |
| 3.4 | Correlator mode controller: no illegal FSM state (`st <= COOL`), dwell counter bounded, `ex_q` equals its state, `ex_q` changes only in the clock after a frame tick or reset (mode switch cannot happen mid-frame, `ex_q` is a flop and not a state decode), COOL never with counter 0 | proof for DWELL=8 and DWELL=3 | `approx_correlator/results/formal.log` (`corr_mode.sby`) |
| 3.5 | Cover points reachable | engine hop with retry-free accept (step 38); wrapper: hop_valid (step 41), drift resync, overrun; LFSR hop; controller: APPROX state, COOL with exact, exact->approx and approx->exact switches (steps 2..10) | same formal logs |

Totals in the last run: 10 hop_engine_v2 sby tasks PASS / 0 FAIL, 3 corr_mode sby tasks PASS, 90/90 SAT equivalences.

## 4. Limits (read before quoting any number)

* Synthesis numbers are yosys + abc estimates with no placement, routing, clock tree, or setup/clk-to-q; delay values are optimistic combinational estimates and are not timing closure. abc results are not noise-free (e.g. LOA1 has more cells but less area than exact); compare differences below ~3 % with care.
* No power, no gate-level simulation, no FPGA/ASIC flow, no hardware.
* The AXI-lite-style port was only exercised by the supplied testbench (no protocol checker/VIP; WSTRB ignored, one outstanding transaction).
* Formal covers invariants listed above, not functional correctness of SipHash (that is simulation vs the Python model, which `hop_engine_v2/model/hop_model.py selftest()` - run by `gen_vectors.py` - checks against the SipHash paper vector and two reference vectors, plus exhaustive Lemire unbiasedness for small widths).
* BER comes from the Python model of the same adder trees (AWGN, ideal sync, random code per bit); the RTL is checked bit-exact against that model, not run in a channel. ETA/TRUNC/LOA4 vectors use COMP=0 (uncalibrated) in RTL tests; the BER table has calibrated COMP rows.
* Latency of the lean engine counts clocks from the sampled `req` to `valid` in simulation for retry-free hops (36 / 68); hops needing retries take longer (e.g. one extra attempt in the RW=8 tests).
* Mode-switch glitch-freedom is shown by (a) formal proof of the controller and (b) simulation monitors; there is no gate-level or timing check of the `ex` fan-out.
