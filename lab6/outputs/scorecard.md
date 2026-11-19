# Red-team scorecard (simulation, own-link model)

Baseline: Thompson no forgetting; 1 rendezvous ch, D=60; no clock check; LCG24 schedule; fixed-threshold key, no monitor; slow dwell; periodic critical msgs, 1 try.

Hardened: floor 0.1 + discount 0.98 / switch-detect; 5 rendezvous ch, D=100; skew-rate check; HMAC schedule; entropy monitor; fast hop (latency = 1 dwell); randomised critical msgs, 3 tries.

| Attack | Idea | Attacker cost | Baseline damage | Verdict | Hardened damage | Verdict | Evidence (baseline / hardened) |
|---|---|---|---|---|---|---|---|
| R1 bandit poisoning | idea 1 | medium (jams 10 ch at 50% for 1500 slots) | 0.48 | DEGRADED | 0.03 | HOLDS | first-300-slot delivery 0.50 vs 0.97 unpoisoned / first-300-slot delivery 0.93 vs 0.95 unpoisoned |
| R2 learning-rate attack | idea 4 | medium (needs learner memory length) | 0.18 | HOLDS | 0.14 | HOLDS | worst 0.81 vs static-jammer 0.99 (uniform floor 0.77; 81% of learning advantage stripped) / worst 0.86 vs static-jammer 0.99 (uniform floor 0.77; 61% of learning advantage stripped) |
| R3 control-plane jamming | idea 6 | cheap (5% duty, 1 channel) | 0.85 | BROKEN | 0.00 | HOLDS | availability 0.14 vs 0.99 / availability 0.99 vs 0.99 |
| R4 time-pushing | idea 7 | medium (needs a growing-delay relay) | 1.00 | BROKEN | 0.67 | BROKEN | 100% of runs misaligned before any alarm (push 1.0 ppm) / 67% of runs misaligned before any alarm (push 1.0 ppm) |
| R5 weak-PRNG schedule | idea 9 | cheap (8 observed hops, LCG24) | 1.00 | BROKEN | 0.02 | HOLDS | LCG24: future-hop prediction accuracy 1.00 after <=20 hops seen / HMAC: future-hop prediction accuracy 0.09 after <=20 hops seen |
| R6 key-from-air drain | idea 10 | medium (control environment) | 0.53 | DEGRADED | 0.00 | HOLDS | weak key accepted: min-entropy 0.47 bit/bit / monitor aborts key (availability lost, key not weakened) |
| R7 myopic follower jammer | idea 11 | medium (fast detector) | 1.00 | BROKEN | 0.09 | HOLDS | follower delivery 0.05 (latency 0.1 dwell) / follower delivery 0.92 (latency 1.0 dwell) |
| R8 timing leak | idea 5 | cheap (10% airtime) | 0.94 | BROKEN | 0.00 | HOLDS | critical delivery 0.06 (periodic, 1 try) / critical delivery 1.00 (randomised, 3 tries) |
