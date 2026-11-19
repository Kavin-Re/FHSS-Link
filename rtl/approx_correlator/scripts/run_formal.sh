#!/bin/bash
# (a) SymbiYosys k-induction + cover on corr_mode_ctrl (b) SAT equivalence dual_adder vs ApproxKit cells.  Writes results/formal.log
cd "$(dirname "$0")/.."; : > results/formal.log
( cd formal; export PATH=$PATH:$PWD
  for j in prove prove_dwell3 cover; do rm -rf corr_mode_$j; echo "== sby -f corr_mode.sby $j" | tee -a ../results/formal.log
    ${SBY:-./sby} -f corr_mode.sby $j 2>&1 | grep -E "DONE|summary: (successful|engine_0 \(smtbmc z3\) returned)|Reached" | sed 's/^SBY *[0-9:]* //' | tee -a ../results/formal.log; done )
echo "== equiv_dual.sh (yosys sat)" | tee -a results/formal.log; formal/equiv_dual.sh | tee -a results/formal.log
