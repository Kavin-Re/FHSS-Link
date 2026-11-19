#!/bin/bash
# Yosys synthesis: (1) generic gate netlist  (2) sky130_fd_sc_hd tt_025C_1v80 mapping for area / abc delay estimate.
# Needs LIB=/path/to/sky130_fd_sc_hd__tt_025C_1v80.lib (not shipped; downloaded from OpenROAD-flow-scripts platforms/sky130hd/lib).
cd "$(dirname "$0")/.."; mkdir -p results/synth build
LIB=${LIB:-../lib/sky130hd_tt_du.lib}
DONT=""   # dont_use cells are marked inside lib copy sky130hd_tt_du.lib (yosys 0.33 abc has no -dont_use option)
synth_one() {  # name top file params...
  name=$1; top=$2; file=$3; shift 3; chp=""
  for p in "$@"; do chp="$chp; chparam -set ${p%%=*} ${p##*=} $top"; done
  # generic
  yosys -q -l results/synth/${name}_generic.log -p "read_verilog -sv $file $chp; hierarchy -top $top; synth -top $top -flatten; abc -g AND,NAND,OR,NOR,XOR,XNOR,ANDNOT,ORNOT,MUX; opt_clean -purge; tee -o results/synth/${name}_generic_stat.txt stat; tee -o results/synth/${name}_generic_ltp.txt ltp -noff"
  # sky130
  yosys -q -l results/synth/${name}_sky130.log -p "read_verilog -sv $file $chp; hierarchy -top $top; synth -top $top -flatten; dfflegalize -cell \$_DFF_P_ x; dfflibmap -liberty $LIB; abc -liberty $LIB $DONT -D 10000; opt_clean -purge; tee -o results/synth/${name}_sky130_stat.txt stat -liberty $LIB"
}



synth_one keyed_m13 hop_keyed rtl/hop_keyed.v M=13
synth_one keyed_m13_ripple hop_keyed rtl/hop_keyed.v M=13 RIPPLE=1
synth_one lfsr_m13  hop_lfsr  rtl/hop_lfsr.v  M=13

# (3) delay estimate: abc map + buffer/upsize/dnsize + "stime -p" with the sky130 tt liberty (no placement/routing; WireLoad none or Small as printed)
timing_one() { name=$1; top=$2; file=$3; shift 3; chp=""
  for p in "$@"; do chp="$chp; chparam -set ${p%%=*} ${p##*=} $top"; done
  yosys -q -l results/synth/${name}_timing.log -p "read_verilog -sv $file $chp; hierarchy -top $top; synth -top $top -flatten; dfflegalize -cell \$_DFF_P_ x; dfflibmap -liberty $LIB; abc -liberty $LIB -script scripts/abc_time.script; opt_clean -purge"
  grep -E "ABC: (WireLoad|Start-point|End-point|Path|Gates)" results/synth/${name}_timing.log > results/synth/${name}_timing_summary.txt; }
timing_one keyed_m13 hop_keyed rtl/hop_keyed.v
timing_one lfsr_m13  hop_lfsr  rtl/hop_lfsr.v
timing_one keyed_m13_ripple hop_keyed rtl/hop_keyed.v RIPPLE=1

# LFSR breakdown: M=16 makes "state mod M" pure wiring, so this is the LFSR core + seed load only (no mod-13 logic)
synth_one lfsr_m16  hop_lfsr  rtl/hop_lfsr.v  M=16
timing_one lfsr_m16 hop_lfsr  rtl/hop_lfsr.v  M=16
