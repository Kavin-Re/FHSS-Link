# DEMO SCRIPT: 10-minute board demo, only things that run today

Everything below was run on the laptop (Python 3.10.12, numpy 2.2.6) on 8 Oct 2026 unless marked STORED. Timings are what I measured; the laptop was busy with parallel jobs, so run each once beforehand to see your own. No hardware appears anywhere in this demo (see the note at the end).

## Before you walk in (2 minutes, once)
```
cd ~/Github_projects/Projects/FHSS-Link
export PYTHONDONTWRITEBYTECODE=1        # stops __pycache__ appearing in the repo
```
Open these tabs/windows in advance (all work from file://, no network, checked headlessly: no console errors, no external requests):
1. `dashboard/index.html`  2. `../HopBench/break_the_hop/index.html`  3. `../VCD-Studio/index_final.html`  4. `../GNSS-Sentinel/examples/meacon_dashboard.html`

Start this in a second terminal at 0:00 and leave it running (it is the "prove it" background evidence; it is slow):
```
python3 lab6/test_lab6.py     # 11 tests, 25-58 s; prints "11/11 tests passed"
```
Do NOT run `./run_tests.sh` live: it now also runs lab4-lab7 and takes minutes. Run it the night before and keep the output.

## Timeline

| Time | Say (idea, your words) | Command | What you should see | If it fails |
|---|---|---|---|---|
| 0:00-1:00 | Problem: a fixed-frequency link dies under a narrowband interferer; scope: simulation + RTL + estimates, no hardware | none | | |
| 1:00-2:00 | Hopping gain | `python3 -m fhss_lab run` (0.7 s) | table: fixed BER 0.238 / 0.427 / 0.475 at JSR 0/10/20 dB; FH M=13 0.018 / 0.033 / 0.036; PDR M=13 0.9222 | open `sim/figures/2_ber_vs_jsr.png` and `sim/figures/3_fh_vs_M_jsr10.png` |
| 2:00-3:00 | Interactive version | in `dashboard/index.html` choose a reactive jammer, defender LFSR then keyed (source: simulator) | LFSR collapses to about 5 % delivery, keyed holds about 91 % (docs/RESULTS.md, Sat) | screenshot of the dashboard from the earlier headless run; or `sim/figures/9_adaptive_jammer.png` |
| 3:00-4:30 | BREAK IT: the 16-bit LFSR schedule | `python3 rtl/hop_engine/model/randcheck.py` (1.8 s) | last lines: `LFSR break over 300 random seeds: identified 300/300 ... min=8 ... max=9`; `same attacker vs keyed RTL stream: identified=False`; LFSR serial-corr p = 0.000, predictor 0.2356 vs chance 0.0769 | `cat rtl/hop_engine/results/randcheck.txt` (STORED, identical) |
| 4:30-5:00 | The exact figure | `cat rtl/hop_engine/results/lfsr_hops_exhaustive.txt` (STORED; recompute is 80 s, skip live) | 8 hops 62.5 %, 9 hops 37.5 %, mean 8.375, information floor 4.32 | say "8 or 9", never "about 9" |
| 5:00-6:00 | FIX IT: keyed engine, maths check | `python3 rtl/hop_engine/model/hop_model.py` then `python3 rtl/hop_engine/model/unbias_check.py` (1-3 s) | `selftest: True`; `330382099` accepted per channel, P(both chunks rejected) = 4.391e-18 | `cat rtl/hop_engine/results/model_selftest.txt unbias_check.txt` |
| 6:00-7:00 | PROVE IT: RTL evidence (STORED: the laptop has no iverilog/yosys, the audit session re-ran these in the cloud) | `tail -15 rtl/hop_engine/results/sim_iverilog.log.txt`; `cat rtl/hop_engine/results/formal.log.txt \| tail -12`; `cat rtl/hop_engine/results/SUMMARY.txt` | 7 benches PASS, 692 retries in the forced-retry bench, 12-cycle latency; proofs PASS; area 31,394 um2 / 8,364 GE vs LFSR 1,828 / 487 | state clearly these are stored logs from the cloud tools |
| 7:00-7:45 | Prove it, software side | `python3 lab4/silicon/run_tests.py \| tail -3` (about 7-26 s) and show the lab6 window | `36 passed, 0 failed`; `11/11 tests passed` | `cat` the stored outputs; or show `lab4/silicon/figures/fig1_cpa.png` |
| 7:45-8:30 | Where it still breaks (red team of my own model) | open `lab4/silicon/figures/fig1_cpa.png` and `lab6/figures/r8_scorecard.png` | CPA traces vs sigma; scorecard 5/8 broken baseline, 1/8 hardened | point at `lab6/outputs/scorecard.md` |
| 8:30-9:15 | Neighbours that actually run | `cd ../GNSS-Sentinel && python3 -m gnss_sentinel stream examples/meacon.csv --quiet \| tail -4` (7 s); `cd ../LifeLine-Mesh/c && make test \| tail -2` (<1 s) | alerts on cn0_agc/raim; `288113 checks, 0 failed` | show `GNSS-Sentinel/results/results.md` table; `LifeLine-Mesh/results/results.md` |
| 9:15-9:45 | Tooling | VCD-Studio `index_final.html`: Open .vcd, pick `../VCD-Studio/demos/hop_engine.vcd` (fixed file picker), show a hop; `HopBench/break_the_hop` game: guess, Reveal the attack | waveform of `req`/`valid`; game reveals LFSR is predictable | screenshots in `VCD-Studio/out/` and `HopBench/break_the_hop/screenshots/` |
| 9:45-10:00 | Limits sentence and what is next | none | | |

## Fallbacks
* A command errors with `FileNotFoundError: figures/...`: you ran a `sim/` script from the wrong folder. Scripts in `sim/` expect to be run from inside `sim/`, and `run_attack.py` rewrites `sim/figures`; avoid it in the demo, use `fhss_lab run` instead.
* HopBench CLI (`python -m hopbench ...`) will not start on this laptop: `SyntaxError: f-string expression part cannot include a backslash` in `hopbench/report.py` line 90 (needs Python 3.12). Use the stored `HopBench/results/results.md`, `radar.png` and the browser game. The unit tests `test_stats.py` and `test_schedules.py` do pass on 3.10.
* The laptop has no pytest. Use the `python3 file.py` forms above (ApproxKit: `python3 tests/test_units.py`, 10 passed; LifeLine Python: `python3 -m unittest discover -s tests`).
* RTL tools missing on laptop is expected. Show the `.log.txt` files and say where they were produced. Do not claim you ran them on stage.
* Browser tab blank: the four HTML files are self-contained; reload with Ctrl-Shift-R. Screenshots exist for each.
* Time overrun: drop 2:00-3:00 (dashboard) and 8:30-9:15 (neighbours). The spine is 1:00 -> 7:45.

## Optional if asked (not on the clock)
* `cd ~/Github_projects/Projects/ApproxKit && python3 tests/test_units.py` (11 s, 10 passed); `python3 examples/demo_apps.py` (8 s, rewrites `results/apps_*`, so do not run it live).
* `python3 rtl/hop_engine/model/lfsr_hops_exhaustive.py` (80 s) for a live exhaustive recomputation.
* `python3 lab5/test_lab5.py` (56 checks, 14-45 s).

## No-hardware-yet note (say it before they ask)
There is no board in this demo. The three-ESP32 ESP-NOW layer in docs/SPEC.md / ROADMAP.md is unbuilt; `firmware/` is not exercised. Hop dead-time, channel-switch time, Wi-Fi overlap, real RSSI and real clock drift are therefore unmeasured, and each simulated PDR above is a statement about my loss model (0.95 jammed / 0.01 clean), not a radio. The RTL has been simulated, formally checked for safety properties, and synthesised to sky130 cells by yosys/abc; it has not been placed and routed, put on an FPGA, or measured for power. The first hardware step that would turn this into evidence is in the "stronger" list: two boards, a logged jammed vs unjammed PDR run, and one FPGA synthesis report.
