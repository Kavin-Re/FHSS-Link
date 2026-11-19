#!/bin/bash
# RTL-vs-Python simulations of hop_engine_v2 with iverilog. Usage: scripts/run_sim.sh [quick]   (quick = fewer hops)
cd "$(dirname "$0")/.."; ROOT=$PWD; mkdir -p results build
python3 -I model/gen_vectors.py > results/vectors_summary.txt && python3 -I model/wrap_model.py >> results/vectors_summary.txt
VD="\"$ROOT/vectors/\""; OD="\"$ROOT/build/\""
: > results/sim_iverilog.log
NS=${NS:-20000}
run() { dw=$1; tag=$2; M=$3; RW=$4; NCH=$5; NK=$6; NS=$7
  iverilog -g2005 -o build/tb_${tag}_dw$dw -DDW=$dw -DTAG="\"$tag\"" -DM=$M -DRW=$RW -DNCH=$NCH -DNKEY=$NK -DNSLOT=$NS -DVDIR="$VD" -DODIR="$OD" tb/tb_hop_keyed_lean.v rtl/hop_keyed_lean.v || exit 1
  vvp -n build/tb_${tag}_dw$dw | tee -a results/sim_iverilog.log; }
# DW=64 : full-size vector set (same as v1); DW=32 : same vectors (the .mem stride is fixed at 20000 slots per key)
run 64 m13 13 32 2 3 20000
run 64 m13_rw8 13 8 1 1 20000
run 64 m13_rw8n4 13 8 4 1 20000
run 64 m37 37 32 2 1 3000
run 64 m16 16 32 2 1 3000
run 32 m13 13 32 2 3 20000
run 32 m13_rw8 13 8 1 1 20000
run 32 m13_rw8n4 13 8 4 1 20000
for fv in 0 1; do
  iverilog -g2005 -o build/tb_lf$fv -DFV=$fv -DVDIR="$VD" -DODIR="$OD" tb/tb_hop_lfsr_fold.v rtl/hop_lfsr_fold.v && vvp -n build/tb_lf$fv | tee -a results/sim_iverilog.log
done
for dw in 64 32; do
  nops=$(wc -l < vectors/wrap_ops.mem)
  iverilog -g2005 -o build/tb_wrap$dw -DDW=$dw -DNOPS=$nops -DVDIR="$VD" -DODIR="$OD" tb/tb_hop_sync_axil.v rtl/hop_sync_axil.v rtl/hop_keyed_lean.v && vvp -n build/tb_wrap$dw | tee -a results/sim_iverilog.log
done
echo "PASS lines: $(grep -c 'RESULT .* PASS' results/sim_iverilog.log)  FAIL lines: $(grep -c 'RESULT .* FAIL' results/sim_iverilog.log)"
