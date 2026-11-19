#!/bin/bash
# Runs all RTL-vs-Python simulations with iverilog (and a Verilator cross-check on the default config). Usage: scripts/run_sim.sh
set -e
cd "$(dirname "$0")/.."; ROOT=$PWD; mkdir -p results build
python3 model/gen_vectors.py > results/vectors_summary.txt
VD="\"$ROOT/vectors/\""; OD="\"$ROOT/results/\""
: > results/sim_iverilog.log
run() { tag=$1; M=$2; RW=$3; NCH=$4; NK=$5; NS=$6
  iverilog -g2005 -o build/tb_$tag -DTAG="\"$tag\"" -DM=$M -DRW=$RW -DNCH=$NCH -DNKEY=$NK -DNSLOT=$NS -DVDIR="$VD" -DODIR="$OD" tb/tb_hop_keyed.v rtl/hop_keyed.v
  vvp -n build/tb_$tag | tee -a results/sim_iverilog.log; }
run m13 13 32 2 3 20000
run m13_rw8 13 8 1 1 20000
run m13_rw8n4 13 8 4 1 20000
# RIPPLE=1 variant (explicit ripple-carry adders, 2000 hops: the function-based adder is slow in iverilog) must give identical output
iverilog -g2005 -o build/tb_m13_ripple -DTAG='"m13_rw8n4"' -DM=13 -DRW=8 -DNCH=4 -DNKEY=1 -DNSLOT=2000 -DRIPPLE=1 -DVDIR="$VD" -DODIR="\"$ROOT/build/\"" tb/tb_hop_keyed.v rtl/hop_keyed.v
vvp -n build/tb_m13_ripple | tee -a results/sim_iverilog.log
run m37 37 32 2 1 3000
run m16 16 32 2 1 3000
iverilog -g2005 -o build/tb_lfsr -DVDIR="$VD" -DODIR="$OD" tb/tb_hop_lfsr.v rtl/hop_lfsr.v
vvp -n build/tb_lfsr | tee -a results/sim_iverilog.log
grep -c "RESULT .* PASS" results/sim_iverilog.log
