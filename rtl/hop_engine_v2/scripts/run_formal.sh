#!/bin/bash
# SymbiYosys (upstream python sources run via formal/sby wrapper) with yosys 0.33 + z3.  k-induction proofs + cover.  Writes results/formal.log
cd "$(dirname "$0")/../formal"; : > ../results/formal.log; export PATH=$PATH:$PWD
for j in "lfsr_fold.sby prove_fv0" "lfsr_fold.sby prove_fv1" "lfsr_fold.sby cover_fv1" "keyed_lean.sby prove_dw64" "keyed_lean.sby prove_dw32" "keyed_lean.sby prove_rw8" "keyed_lean.sby cover_dw64" "sync_axil.sby prove_dw64" "sync_axil.sby prove_dw32" "sync_axil.sby cover_dw64"; do
  set -- $j; rm -rf ${1%.sby}_$2; echo "== sby -f $j" | tee -a ../results/formal.log
  ${SBY:-./sby} -f $j 2>&1 | grep -E "DONE|summary: (successful|engine_0 \(smtbmc z3\) returned)|Reached" | sed 's/^SBY *[0-9:]* //' | tee -a ../results/formal.log
done
