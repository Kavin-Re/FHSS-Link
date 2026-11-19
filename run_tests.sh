#!/bin/sh
# Runs the Python-only (numpy) tests listed below; prints PASS/FAIL/SKIP per entry and exits non-zero if any fails.
# Covered: sim/, lab/, lab2/, lab3/ (10 files), lab4/silicon (run_tests.py), lab5, lab6, lab7, rtl/hop_engine/model
# (SipHash/Lemire selftest, unbias check) and, when the sibling folder ../ApproxKit exists, ApproxKit/tests/test_units.py.
# NOT covered (needs EDA tools, not run here or in CI): the hop_engine RTL simulations (iverilog, Verilator), the formal
# proofs (SymbiYosys) and synthesis (Yosys), and the ApproxKit RTL regression (scripts/rtl_regress.py).
# Usage: ./run_tests.sh          (about 2-3 minutes; lab7 is the slowest)
cd "$(dirname "$0")" || exit 1
MPLBACKEND=Agg; export MPLBACKEND
PYTHONDONTWRITEBYTECODE=1; export PYTHONDONTWRITEBYTECODE
out=$(mktemp "${TMPDIR:-/tmp}/fhss_test.XXXXXX") || exit 1
trap 'rm -f "$out"' EXIT
fail=0
run() {  # run <dir> <script> [label]
  d=$1; f=$2
  if (cd "$d" && python3 "$f" >"$out" 2>&1); then echo "PASS $d/$f"; else echo "FAIL $d/$f"; tail -5 "$out"; fail=1; fi
}
for t in sim/test_sim.py sim/test_link.py sim/test_attack.py sim/test_fec.py sim/test_proto.py sim/test_safety.py sim/modelcheck.py lab/test_batchA.py lab2/test_batchB.py lab3/test_batchC.py \
         lab4/silicon/run_tests.py lab5/test_lab5.py lab6/test_lab6.py lab7/test_lab7.py \
         rtl/hop_engine/model/hop_model.py rtl/hop_engine/model/unbias_check.py; do
  run "$(dirname "$t")" "$(basename "$t")"
done
if [ -f ../ApproxKit/tests/test_units.py ]; then run ../ApproxKit tests/test_units.py; else echo "SKIP ApproxKit/tests/test_units.py (sibling folder ../ApproxKit not present)"; fi
exit $fail
