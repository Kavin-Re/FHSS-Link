# Beyond the jammer: adversary-style ideas across the whole stack (7 Oct 2026)
Same scope rule as RED_TEAM_IDEAS.md: simulation, models and our own test setup only; every idea ends in a defence or a measurement.

## Silicon and hardware
1. Hardware Trojan hunt: a tiny gate-level simulator in Python for the hop sequencer/correlator; insert a rare-trigger trojan (counter, comparator); find it by random-vector testing, toggle-count statistics and formal-style equivalence; how rare must the trigger be to escape N test vectors?
2. Adversarial inputs for APPROXIMATE hardware: craft frames or signals that maximise the error of an approximate SAD or correlator (your approximate-computing line) while an exact unit stays correct; defences: error monitors, occasional exact checks.
3. Fault injection: bit flips or clock glitches in the hop counter or key schedule (differential fault analysis), plus natural faults (single-event upsets): cost of TMR, parity or ECC in area, and where approximation is safe.
4. Side-channel power analysis: simulate Hamming-weight leakage of an HMAC/ChaCha/AES round, recover a key byte by correlation (CPA), then add masking and measure the traces needed.
5. Timing side channel: a non-constant-time tag comparison lets an attacker forge a beacon byte by byte; simulate with noisy timing, then fix with constant-time compare and report the measurements needed.

## Navigation, sensing and the physical world
6. GPS carry-off spoofing: simulate a tracking loop, let a spoofer pull it off slowly, detect the drag with an innovation test against a clock/IMU model (generalises the time-pushing attack).
7. Meaconing (delayed replay) and multi-antenna or clock-consistency defences.
8. Acoustic resonance injection into a MEMS gyro: model the resonance, show the drone's attitude estimate corrupted, defend with sensor redundancy and fusion.
9. Fingerprint forgery: an attacker emulates our crystal skew in software; at what precision does the fingerprint from the earlier module fail, and what second feature restores it?

## Machine learning and data
10. Adversarial perturbations against the modulation classifier (small input changes that flip the label) and robust training.
11. Poisoned logs: tamper with the data the digital twin or the dataset learns from; detect with the hash chain and statistical checks.

## Protocol, formal and implementation
12. Fuzzing: property-based fuzzer for the serial parser, dashboard and packet codec; our CRC already accepted 2 of 2416 corrupted messages in one test, so there is real material.
13. Dolev-Yao model check of the safety-guard token protocol: an attacker controls the network; verify the node never emits without a fresh token.
14. Crypto denial of service: flood invalid packets to burn the node's CPU on MAC checks; cheap pre-filters, rate limits, and a cost model for a small microcontroller.
15. Permutation hopping leaks: if each epoch visits every channel once (required by some regimes), the attacker's guess improves from 1/M to 1/(M-i). Quantify and design a fix (keyed overlapping epochs).
16. Traffic analysis: even with encryption and hopping, timing, length and energy reveal who talks when; measure the leak as mutual information and the bandwidth cost of cover traffic and padding.
17. Covert channels: hide data in free protocol fields or timing; statistical detection (ties to the watermark module).

## Supply chain and operations
18. Secure update path: signed firmware, rollback protection, a software bill of materials, reproducible builds; simulate a poisoned update and show it is rejected.
19. Alert psychology: a deceiver causes false alarms to wear down the operator; ROC-based alert thresholds and explanation text.

## Nature-inspired and out-of-field
20. Jamming avoidance in electric fish and jamming between bats: implement the fish's simple "shift away from the interferer" rule as a defender and compare with the bandit policies.
21. Maximum-entropy hopping under constraints (spectral mask, no-go channels, regulatory minimum channel counts): constrained randomness as an optimisation problem.
22. RF incident forensics: reconstruct a timeline from the hash-chained logs and the twin, classify what happened and produce a report (fits a forensic and security university).

## Meta
23. AI red-team and blue-team loop: Claude agents attack the simulator (writing attack code), another patches the defence, a referee scores both; guard rails: sandbox only, simulator only, every action logged. This could be the project's most distinctive idea.
