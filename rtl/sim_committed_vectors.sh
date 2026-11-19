#!/bin/bash
# RTL-vs-Python-model simulation of every testbench with iverilog, using the COMMITTED vectors (rtl/*/vectors/*.mem).
# Unlike rtl/*/scripts/run_sim.sh it regenerates nothing and writes nothing into results/: build products and logs go to a
# scratch directory, so it needs only iverilog + vvp (no numpy, no ApproxKit checkout) and leaves the tree clean.
# Same compile commands and parameter sets as the three run_sim.sh scripts (26 testbench runs in total: 7 + 12 + 7).
# Usage: rtl/sim_committed_vectors.sh [scratch-dir]      exit status 0 only if all 26 runs print "RESULT <tag> PASS".
# NOTE: written for CI (apt-get install iverilog). It was NOT executed in the environment where it was written
#       (no iverilog there); the reference results of the original scripts are in rtl/*/results/sim_iverilog.log*.
set -u
RTL=$(cd "$(dirname "$0")" && pwd)
command -v iverilog >/dev/null 2>&1 && command -v vvp >/dev/null 2>&1 || { echo "iverilog/vvp not found (apt-get install iverilog)"; exit 2; }
B=${1:-$(mktemp -d "${TMPDIR:-/tmp}/fhss_rtl.XXXXXX")}; mkdir -p "$B"; LOG=$B/sim.log; : > "$LOG"
OD="\"$B/\""
sim() { out=$1; shift; if iverilog -g2005 -o "$B/$out" "$@"; then vvp -n "$B/$out" | tee -a "$LOG"; else echo "RESULT $out FAIL (compile)" | tee -a "$LOG"; fi; }

# ---- hop_engine (v1): keyed SipHash-2-4 + Lemire, and the LFSR reference -------------------------------- 7 runs
H=$RTL/hop_engine; VD="\"$H/vectors/\""
k1() { tag=$1; sim v1_$tag -DTAG="\"$tag\"" -DM=$2 -DRW=$3 -DNCH=$4 -DNKEY=$5 -DNSLOT=$6 -DVDIR="$VD" -DODIR="$OD" "$H/tb/tb_hop_keyed.v" "$H/rtl/hop_keyed.v"; }
k1 m13 13 32 2 3 20000
k1 m13_rw8 13 8 1 1 20000
k1 m13_rw8n4 13 8 4 1 20000
sim v1_ripple -DTAG='"m13_rw8n4"' -DM=13 -DRW=8 -DNCH=4 -DNKEY=1 -DNSLOT=2000 -DRIPPLE=1 -DVDIR="$VD" -DODIR="$OD" "$H/tb/tb_hop_keyed.v" "$H/rtl/hop_keyed.v"
k1 m37 37 32 2 1 3000
k1 m16 16 32 2 1 3000
sim v1_lfsr -DVDIR="$VD" -DODIR="$OD" "$H/tb/tb_hop_lfsr.v" "$H/rtl/hop_lfsr.v"

# ---- hop_engine_v2: lean keyed engine (DW=64/32), folded mod-13 LFSR (FV=0/1), AXI-lite/beacon wrapper -- 12 runs
H=$RTL/hop_engine_v2; VD="\"$H/vectors/\""
k2() { dw=$1; tag=$2; sim v2_${tag}_dw$dw -DDW=$dw -DTAG="\"$tag\"" -DM=$3 -DRW=$4 -DNCH=$5 -DNKEY=$6 -DNSLOT=$7 -DVDIR="$VD" -DODIR="$OD" "$H/tb/tb_hop_keyed_lean.v" "$H/rtl/hop_keyed_lean.v"; }
k2 64 m13 13 32 2 3 20000
k2 64 m13_rw8 13 8 1 1 20000
k2 64 m13_rw8n4 13 8 4 1 20000
k2 64 m37 37 32 2 1 3000
k2 64 m16 16 32 2 1 3000
k2 32 m13 13 32 2 3 20000
k2 32 m13_rw8 13 8 1 1 20000
k2 32 m13_rw8n4 13 8 4 1 20000
for fv in 0 1; do sim v2_lfsr_fv$fv -DFV=$fv -DVDIR="$VD" -DODIR="$OD" "$H/tb/tb_hop_lfsr_fold.v" "$H/rtl/hop_lfsr_fold.v"; done
nops=$(wc -l < "$H/vectors/wrap_ops.mem")
for dw in 64 32; do sim v2_wrap$dw -DDW=$dw -DNOPS=$nops -DVDIR="$VD" -DODIR="$OD" "$H/tb/tb_hop_sync_axil.v" "$H/rtl/hop_sync_axil.v" "$H/rtl/hop_keyed_lean.v"; done

# ---- approx_correlator: DS-SS despreading correlator built from ApproxKit adder cells ------------------- 7 runs
A=$RTL/approx_correlator; VD="\"$A/vectors/\""
# parameter sets come from the committed summary written by model/gen_corr_vectors.py: "<tag>: N=.. ATYPE=.. K=.. COMP=.. ..."
sed -n 's/^\([A-Za-z0-9_]*\): N=\([0-9]*\) ATYPE=\([0-9]*\) K=\([0-9]*\) COMP=\(-\{0,1\}[0-9]*\) .*/\1 \2 \3 \4 \5/p' "$A/results/corr_vectors_summary.txt" > "$B/corr_cfg.txt"
while read -r tag N AT K C; do
  ncl=$(wc -l < "$A/vectors/stim_$tag.mem"); nex=$(wc -l < "$A/vectors/exp_$tag.mem")
  sim corr_$tag -DTAG="\"$tag\"" -DN=$N -DATYPE=$AT -DK=$K -DCOMP=$C -DNCLK=$ncl -DNEXP=$nex -DVDIR="$VD" \
    "$A/tb/tb_approx_correlator.v" "$A/rtl/approx_correlator.v" "$A/rtl/corr_core.v" "$A/rtl/corr_tree.v" "$A/rtl/corr_mode_ctrl.v" "$A/rtl/dual_adder.v" \
    "$A/rtl/ak_cells/exact_adder.v" "$A/rtl/ak_cells/loa_adder.v" "$A/rtl/ak_cells/trunc_adder.v" "$A/rtl/ak_cells/eta_adder.v"
done < "$B/corr_cfg.txt"

EXPECT=26
pass=$(grep -c 'RESULT .* PASS' "$LOG"); nfail=$(grep -c 'RESULT .* FAIL' "$LOG")
echo "PASS lines: $pass (expected $EXPECT)  FAIL lines: $nfail  log: $LOG"
[ "$pass" -eq "$EXPECT" ] && [ "$nfail" -eq 0 ]
