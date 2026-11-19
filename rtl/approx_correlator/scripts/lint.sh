#!/bin/bash
cd "$(dirname "$0")/.."; { echo "== verilator --lint-only -Wall"
for cfg in "16 1 3" "32 1 3" "64 2 2" "32 3 3" "32 0 0"; do set -- $cfg; echo "-- approx_correlator N=$1 ATYPE=$2 K=$3"
  verilator --lint-only -Wall --top-module approx_correlator -GN=$1 -GATYPE=$2 -GK=$3 rtl/approx_correlator.v rtl/corr_core.v rtl/corr_tree.v rtl/corr_mode_ctrl.v rtl/dual_adder.v rtl/ak_cells/*.v 2>&1; done
echo "(no output under a heading = clean)"; echo "== iverilog -Wall"; iverilog -g2005 -Wall -o /dev/null rtl/*.v rtl/ak_cells/*.v 2>&1; echo "(no output above = clean)"; } > results/lint.txt 2>&1; cat results/lint.txt
