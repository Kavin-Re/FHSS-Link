#!/bin/bash
# approx_correlator: RTL vs Python bit-exact simulation (iverilog) + Verilator lint.  Usage: scripts/run_sim.sh
cd "$(dirname "$0")/.."; ROOT=$PWD; mkdir -p results build
python3 -I model/gen_corr_vectors.py > results/corr_vectors_summary.txt || exit 1
VD="\"$ROOT/vectors/\""; : > results/sim_iverilog.log
while read tag N A K C; do
  ncl=$(wc -l < vectors/stim_$tag.mem); nex=$(wc -l < vectors/exp_$tag.mem)
  iverilog -g2005 -o build/tb_$tag -DTAG="\"$tag\"" -DN=$N -DATYPE=$A -DK=$K -DCOMP=$C -DNCLK=$ncl -DNEXP=$nex -DVDIR="$VD" \
     tb/tb_approx_correlator.v rtl/approx_correlator.v rtl/corr_core.v rtl/corr_tree.v rtl/corr_mode_ctrl.v rtl/dual_adder.v rtl/ak_cells/exact_adder.v rtl/ak_cells/loa_adder.v rtl/ak_cells/trunc_adder.v rtl/ak_cells/eta_adder.v || exit 1
  vvp -n build/tb_$tag | tee -a results/sim_iverilog.log
done < <(python3 -I - <<'PY'
import re
for l in open("results/corr_vectors_summary.txt"):
    m = re.match(r"(\w+): N=(\d+) ATYPE=(\d+) K=(\d+) COMP=(-?\d+)", l); print(*m.groups())
PY
)
echo "PASS lines: $(grep -c 'RESULT .* PASS' results/sim_iverilog.log)  FAIL lines: $(grep -c 'RESULT .* FAIL' results/sim_iverilog.log)"
