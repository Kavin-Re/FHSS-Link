#!/bin/bash
# RTL wave 2 (FHSS-Link): hop_engine_v2 + approx_correlator.  Simulation + synthesis estimates + formal only; no hardware.
# Usage: ./run_all.sh            full flow (~15-20 min: sims, yosys/sky130 synth, formal, BER Monte Carlo 200000 bits/point)
#        QUICK=1 ./run_all.sh    lint + sims + formal + collect from EXISTING synth/BER results (skips synthesis and the BER Monte Carlo)
# Tools used (cloud container): iverilog 12, verilator 5.020, yosys 0.33, z3, SymbiYosys (upstream python via formal/sby wrapper, SBY=... to override),
#   python3 + numpy, sky130hd liberty (LIB=..., default /home/claude/work/lib/sky130hd_tt_du.lib), ApproxKit python package (APPROXKIT=... or /home/claude/work/approxkit).
cd "$(dirname "$0")/.."; ROOT=$PWD; H=$ROOT/hop_engine_v2; A=$ROOT/approx_correlator; LOG=$ROOT/wave2/run_all.log; : > $LOG
step() { echo "[$(date +%H:%M:%S)] $*" | tee -a $LOG; }
step "hop_engine_v2: vectors + iverilog sims (keyed lean DW=64/32, LFSR fold FV=0/1 incl. exhaustive 65535 states, AXI-lite wrapper DW=64/32)"
$H/scripts/run_sim.sh > $H/results/run_sim.out 2>&1; tail -1 $H/results/run_sim.out | tee -a $LOG
step "hop_engine_v2: mutation check of the testbenches"
python3 -I $H/scripts/run_mutation.py > $H/results/mutation.txt 2>&1; tail -1 $H/results/mutation.txt | tee -a $LOG
step "approx_correlator: vectors + iverilog sims (7 configurations, N=16/32/64)"
$A/scripts/run_sim.sh > $A/results/run_sim.out 2>&1; tail -1 $A/results/run_sim.out | tee -a $LOG
step "approx_correlator: verilator lint"; $A/scripts/lint.sh > /dev/null 2>&1; grep -c "^%" $A/results/lint.txt | sed 's/^/verilator messages: /' | tee -a $LOG
step "formal: hop_engine_v2 (k-induction + cover)"; $H/scripts/run_formal.sh > /dev/null 2>&1; grep -cE "DONE \(PASS" $H/results/formal.log | sed 's/^/sby PASS: /' | tee -a $LOG; grep -cE "DONE \((FAIL|ERROR)" $H/results/formal.log | sed 's/^/sby FAIL: /' | tee -a $LOG
step "formal: approx_correlator (corr_mode_ctrl + dual_adder SAT equivalence)"; $A/scripts/run_formal.sh > /dev/null 2>&1; grep -cE "DONE \(PASS" $A/results/formal.log | sed 's/^/sby PASS: /' | tee -a $LOG; grep "equiv_dual:" $A/results/formal.log | tee -a $LOG
if [ -z "$QUICK" ]; then
  step "synthesis estimates (yosys + sky130)"; $H/scripts/synth.sh > /dev/null 2>&1; $A/scripts/synth.sh > /dev/null 2>&1
  step "BER vs SNR (Python bit-exact model)"; (cd $A && NBITS=${NBITS:-200000} python3 -I model/ber_model.py > results/ber_run.out 2>&1)
fi
step "collect"; python3 -I $H/scripts/collect.py > /dev/null; python3 -I $A/scripts/collect.py > /dev/null
echo "== summary" | tee -a $LOG
for f in $H/results/run_sim.out $A/results/run_sim.out; do tail -1 $f | tee -a $LOG; done
echo "ALL_DONE" | tee -a $LOG
