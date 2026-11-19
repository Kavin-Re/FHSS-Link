#!/bin/bash
# SymbiYosys formal checks. sby is the upstream python source (YosysHQ/SymbiYosys, fetched from raw.githubusercontent.com) run with the apt yosys 0.33 and z3.
# Set SBY to your sby command (default: ./formal/sby wrapper). Writes results/formal.log
cd "$(dirname "$0")/../formal"; : > ../results/formal.log
export PATH=$PATH:$PWD
for j in "lfsr.sby" "keyed.sby prove_default" "keyed.sby prove_rw8" "keyed.sby cover_default"; do
  rm -rf $(echo $j | awk '{print $1}' | sed 's/.sby//')_* ; echo "== sby -f $j" | tee -a ../results/formal.log
  ${SBY:-./sby} -f $j 2>&1 | grep -E "DONE|summary: (successful|engine_0 \(smtbmc z3\) returned)|Reached" | tee -a ../results/formal.log
done
