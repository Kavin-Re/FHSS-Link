#!/bin/bash
# Cross-check with Verilator (--binary): default config + retry config + LFSR. Run after scripts/run_sim.sh (needs vectors/).
cd "$(dirname "$0")/.."; ROOT=$PWD; mkdir -p build/vl results; VD="\"$ROOT/vectors/\""; OD="\"$ROOT/build/vl/\""
: > results/sim_verilator.log
vl() { top=$1; tag=$2; shift 2
  verilator --binary --timing -Wno-fatal -Wno-lint -Wno-style --top-module $top -Mdir build/vl/obj_$tag -o v$tag -DVDIR="$VD" -DODIR="$OD" "$@" >/dev/null 2>&1
  build/vl/obj_$tag/v$tag | grep -E "TB\[|RESULT" | tee -a results/sim_verilator.log; }
vl tb_hop_keyed m13 -DTAG='"m13"' -DM=13 -DRW=32 -DNCH=2 -DNKEY=3 -DNSLOT=20000 tb/tb_hop_keyed.v rtl/hop_keyed.v
vl tb_hop_keyed m13_rw8 -DTAG='"m13_rw8"' -DM=13 -DRW=8 -DNCH=1 -DNKEY=1 -DNSLOT=20000 tb/tb_hop_keyed.v rtl/hop_keyed.v
vl tb_hop_keyed m13_rw8n4 -DTAG='"m13_rw8n4"' -DM=13 -DRW=8 -DNCH=4 -DNKEY=1 -DNSLOT=20000 tb/tb_hop_keyed.v rtl/hop_keyed.v
vl tb_hop_lfsr lfsr tb/tb_hop_lfsr.v rtl/hop_lfsr.v
