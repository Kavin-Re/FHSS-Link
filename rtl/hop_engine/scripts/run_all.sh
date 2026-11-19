#!/bin/bash
# Full flow: lint, vectors+iverilog sims, verilator cross-sim, yosys synth (generic + sky130), randomness checks, formal.
# Requires: iverilog 12, verilator 5, yosys 0.33, z3, numpy, SymbiYosys (formal/sby wrapper), sky130 liberty at ../lib/sky130hd_tt_du.lib (see README).
cd "$(dirname "$0")/.."; mkdir -p results build
{ echo "== verilator --lint-only -Wall"; verilator --lint-only -Wall rtl/hop_keyed.v --top-module hop_keyed 2>&1; verilator --lint-only -Wall rtl/hop_lfsr.v --top-module hop_lfsr 2>&1; echo "(no output above = clean)"; echo "== iverilog -Wall"; iverilog -g2005 -Wall -o /dev/null rtl/hop_keyed.v rtl/hop_lfsr.v 2>&1; echo "(no output above = clean)"; } > results/lint.txt
python3 model/hop_model.py > results/model_selftest.txt
scripts/run_sim.sh > results/run_sim.out 2>&1
scripts/run_verilator.sh > results/run_verilator.out 2>&1
python3 model/randcheck.py > results/randcheck.txt 2>&1
python3 model/unbias_check.py > results/unbias_check.txt
scripts/synth.sh > results/synth.out 2>&1
python3 scripts/collect.py > /dev/null
scripts/run_formal.sh > /dev/null 2>&1
echo ALL_DONE > results/ALL_DONE
