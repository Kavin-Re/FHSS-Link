#!/bin/bash
# Yosys area/delay estimate, SAME METHOD as hop_engine_v2/scripts/synth.sh (and v1): generic gates, sky130_fd_sc_hd tt_025C_1v80 mapping (abc -D 10000), abc stime.
# Estimates only: no placement, no routing, ideal clock.  Usage: scripts/synth.sh [all]
cd "$(dirname "$0")/.."; mkdir -p results/synth
LIB=${LIB:?set LIB to a sky130_fd_sc_hd tt_025C_1v80 liberty file with dont_use marks (see rtl/hop_engine/README.md)}
RTL="rtl/approx_correlator.v rtl/corr_core.v rtl/corr_tree.v rtl/corr_mode_ctrl.v rtl/dual_adder.v rtl/ak_cells/exact_adder.v rtl/ak_cells/loa_adder.v rtl/ak_cells/trunc_adder.v rtl/ak_cells/eta_adder.v"
synth_one() {  # name top params...
  name=$1; top=$2; shift 2; chp=""
  for p in "$@"; do chp="$chp; chparam -set ${p%%=*} ${p##*=} $top"; done
  yosys -q -l results/synth/${name}_generic.log -p "read_verilog -sv $RTL $chp; hierarchy -top $top; synth -top $top -flatten; abc -g AND,NAND,OR,NOR,XOR,XNOR,ANDNOT,ORNOT,MUX; opt_clean -purge; tee -o results/synth/${name}_generic_stat.txt stat; tee -o results/synth/${name}_generic_ltp.txt ltp -noff"
  yosys -q -l results/synth/${name}_sky130.log -p "read_verilog -sv $RTL $chp; hierarchy -top $top; synth -top $top -flatten; dfflegalize -cell \$_DFF_P_ x; dfflibmap -liberty $LIB; abc -liberty $LIB -D 10000; opt_clean -purge; tee -o results/synth/${name}_sky130_stat.txt stat -liberty $LIB"
  yosys -q -l results/synth/${name}_timing.log -p "read_verilog -sv $RTL $chp; hierarchy -top $top; synth -top $top -flatten; dfflegalize -cell \$_DFF_P_ x; dfflibmap -liberty $LIB; abc -liberty $LIB -script scripts/abc_time.script; opt_clean -purge"
  grep -E "ABC: (WireLoad|Start-point|End-point|Path|Gates)" results/synth/${name}_timing.log > results/synth/${name}_timing_summary.txt
}
job() { case $1 in
  core)  # static combinational tree, ApproxKit cells instantiated unmodified (DYN=0), COMP=0
    N=$2; a=$3; k=$4; nm=$5; synth_one core_N${N}_$nm corr_core N=$N ATYPE=$a K=$k DYN=0 COMP=0 ;;
  dyn)   # full runtime-switchable block (dual_adder + mode controller + output registers)
    N=$2; a=$3; k=$4; c=$5; nm=$6; synth_one dyn_N${N}_$nm approx_correlator N=$N ATYPE=$a K=$k COMP=$c ;;
 esac; }
JOBS=()
for N in 16 32 64; do
  JOBS+=("core $N 0 0 exact" "core $N 1 1 LOA1" "core $N 1 2 LOA2" "core $N 1 3 LOA3" "core $N 2 2 TRUNC2" "core $N 3 3 ETA3")
  comp=$(python3 -I -c "import sys;sys.path.insert(0,'model');from ber_model import calib;print(calib($N,1,3)[0])")
  JOBS+=("dyn $N 0 0 0 exact_ctrl" "dyn $N 1 3 $((comp & 0xFFFFFFFF)) LOA3")   # yosys 0.33 chparam cannot decode negative literals: pass the 32-bit two's complement
done
for j in "${JOBS[@]}"; do [[ -n "$FILTER" && ! "$j" =~ $FILTER ]] && continue; job $j & if (( $(jobs -r | wc -l) >= 2 )); then wait -n; fi; done; wait
