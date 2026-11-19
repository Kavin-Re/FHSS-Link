#!/bin/bash
# Reproduces everything in lab4/silicon. Run from this folder. Each step stays under ~150 s on a laptop-class CPU.
set -e
cd "$(dirname "$0")"; mkdir -p figures results
python3 run_tests.py
python3 exp1_cpa.py
python3 exp2_fault.py
python3 exp3_trojan.py
python3 exp4_puf.py
python3 build_results.py
