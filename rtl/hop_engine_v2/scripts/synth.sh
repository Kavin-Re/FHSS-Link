#!/bin/bash
# Yosys synthesis, SAME METHOD as rtl/hop_engine/scripts/synth.sh (v1): (1) generic gate netlist (2) sky130_fd_sc_hd tt_025C_1v80 mapping (3) abc stime delay.
# The v1 RTL (../hop_engine/rtl) is re-synthesised here with this very script so v1 and v2 numbers come from one tool run on one machine.
# LIB = sky130 liberty with dont_use marks (see README), V1 = directory with v1 rtl (default: ../hop_engine/rtl).
cd "$(dirname "$0")/.."; mkdir -p results/synth build
LIB=${LIB:-/home/claude/work/lib/sky130hd_tt_du.lib}
V1=${V1:-../hop_engine/rtl}
synth_one() {  # name top "files" params...
  name=$1; top=$2; file=$3; shift 3; chp=""
  for p in "$@"; do chp="$chp; chparam -set ${p%%=*} ${p##*=} $top"; done
  yosys -q -l results/synth/${name}_generic.log -p "read_verilog -sv $file $chp; hierarchy -top $top; synth -top $top -flatten; abc -g AND,NAND,OR,NOR,XOR,XNOR,ANDNOT,ORNOT,MUX; opt_clean -purge; tee -o results/synth/${name}_generic_stat.txt stat; tee -o results/synth/${name}_generic_ltp.txt ltp -noff"
  yosys -q -l results/synth/${name}_sky130.log -p "read_verilog -sv $file $chp; hierarchy -top $top; synth -top $top -flatten; dfflegalize -cell \$_DFF_P_ x; dfflibmap -liberty $LIB; abc -liberty $LIB -D 10000; opt_clean -purge; tee -o results/synth/${name}_sky130_stat.txt stat -liberty $LIB"
  yosys -q -l results/synth/${name}_timing.log -p "read_verilog -sv $file $chp; hierarchy -top $top; synth -top $top -flatten; dfflegalize -cell \$_DFF_P_ x; dfflibmap -liberty $LIB; abc -liberty $LIB -script scripts/abc_time.script; opt_clean -purge"
  grep -E "ABC: (WireLoad|Start-point|End-point|Path|Gates)" results/synth/${name}_timing.log > results/synth/${name}_timing_summary.txt
}
case "${1:-all}" in
 v1)     synth_one v1_keyed hop_keyed $V1/hop_keyed.v M=13 ; synth_one v1_lfsr13 hop_lfsr $V1/hop_lfsr.v M=13 ;;
 lean64) synth_one lean64 hop_keyed_lean rtl/hop_keyed_lean.v M=13 DW=64 ;;
 lean32) synth_one lean32 hop_keyed_lean rtl/hop_keyed_lean.v M=13 DW=32 ;;
 fold)   synth_one lfsr_fold0 hop_lfsr_fold rtl/hop_lfsr_fold.v FV=0 ; synth_one lfsr_fold1 hop_lfsr_fold rtl/hop_lfsr_fold.v FV=1 ;;
 wrap64) synth_one wrap64 hop_sync_axil "rtl/hop_sync_axil.v rtl/hop_keyed_lean.v" DW=64 ;;
 wrap32) synth_one wrap32 hop_sync_axil "rtl/hop_sync_axil.v rtl/hop_keyed_lean.v" DW=32 ;;
 all)    for t in v1 lean64 lean32 fold wrap64 wrap32; do "$0" $t & if (( $(jobs -r | wc -l) >= 2 )); then wait -n; fi; done; wait ;;
esac
