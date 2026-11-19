#!/bin/bash
# SAT equivalence (yosys 'sat -prove ne 0 -verify', exhaustive, combinational) of dual_adder against the ApproxKit cells:
#   ex=0 : dual_adder == loa_adder / trunc_adder / eta_adder  (unmodified ApproxKit RTL in rtl/ak_cells)
#   ex=1 : dual_adder == exact_adder
# for every width n = 6..11 used by the correlator trees (W=6, N<=64) and K = 1..5 (K capped at n-1).
cd "$(dirname "$0")/.."; mkdir -p results; OUT=results/equiv_dual.log; : > $OUT
T=$(mktemp -d); pass=0; fail=0
for ty in 1 2 3; do case $ty in 1) cell=loa_adder;; 2) cell=trunc_adder;; 3) cell=eta_adder;; esac
 for n in 6 7 8 9 10 11; do for k in 1 2 3 4 5; do
  cat > $T/m.v <<V
module m(input [$((n-1)):0] a, b, output ne0, ne1);
  wire [$n:0] yd0, yr0, yd1, yr1;
  dual_adder #(.N($n), .K($k), .TYPE($ty)) d0 (.a(a), .b(b), .ex(1'b0), .y(yd0));
  $cell #(.N($n), .K($k)) r0 (.a(a), .b(b), .y(yr0));
  dual_adder #(.N($n), .K($k), .TYPE($ty)) d1 (.a(a), .b(b), .ex(1'b1), .y(yd1));
  exact_adder #(.N($n)) r1 (.a(a), .b(b), .y(yr1));
  assign ne0 = (yd0 != yr0);
  assign ne1 = (yd1 != yr1);
endmodule
V
  if yosys -q -p "read_verilog -sv $T/m.v rtl/dual_adder.v rtl/ak_cells/exact_adder.v rtl/ak_cells/$cell.v; hierarchy -top m; proc; flatten; opt; sat -prove ne0 0 -prove ne1 0 -verify" >$T/log 2>&1; then
    echo "PASS type=$ty($cell) n=$n K=$k" >> $OUT; pass=$((pass+1)); else echo "FAIL type=$ty n=$n K=$k"  >> $OUT; fail=$((fail+1)); fi
 done; done; done
echo "equiv_dual: pass=$pass fail=$fail" | tee -a $OUT
rm -rf $T
