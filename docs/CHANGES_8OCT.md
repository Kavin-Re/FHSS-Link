# CHANGES_8OCT: edits made on 8 Oct 2026 after docs/AUDIT_WAVE1.md

Every edited file has a pristine copy next to it named `<file>.bak_8Oct` (git-ignored by `*.bak*`; `diff <file>.bak_8Oct <file>` shows the change). Files created are marked new. No code logic, stored outputs or numbers from experiments were changed; only prose, labels, test runner and CI. No git, no hardware.

Review of the first batch (edited by an earlier session that was cut off): each diff was checked against the stored outputs and the audit. All were correct, none was reverted.

## Edited files

| File | What changed | Audit item | Backup |
|---|---|---|---|
| lab5/RESULTS_LAB5.md | Tone-jam bullet rewritten (exact 0.169; usable approx adders 0.171-0.229; LOA(5) 0.067 and the collapsed configs listed). Section 4 numbers set to the stored json: 0.990, 0.958/0.935/0.918, 0.644, blind 0.769 (x2), 0.678/0.607, 0.285/0.267 (checked against outputs/exp4_soft_set.txt and exp1 table). Later in this session: 20 dB sentence marked as a power-ratio argument; EXP3 vs value (+0.001) no longer claimed as "not a best response"; "all above 0.9177" restated with noise; caveat now says no CIs | 5, 6, 11, 21 | lab5/RESULTS_LAB5.md.bak_8Oct |
| lab6/RESULTS_LAB6.md | Test time 25 s; R1 row 0.52 (0.50 scorecard run) and where the clean 0.97 is stored; R6 row now min-entropy 60.2 bits, about 68 of 128 known, nudge caveat; R5 text says the 8 hops is for LCG24 and the LFSR needs 8 or 9, xorshift 0.7 (0.66 stored); later: HMAC 0.084 vs 0.077 is about 1.5 SE; R4 false-alarm bound about 22 %, 1 ppm gate hits 3.0 vs 2.2 | 7, 8, 9, 11, 15 | lab6/RESULTS_LAB6.md.bak_8Oct |
| lab6/test_lab6.py | Docstring timing "about 25 s" (comment only) | 15 | lab6/test_lab6.py.bak_8Oct |
| lab6/exp8_scorecard.py, lab6/outputs/scorecard.md, lab6/outputs/run_all_log.txt | R5 label "cheap (8 observed hops)" now "cheap (8 observed hops, LCG24)" so it is not read as the LFSR figure (label text only; numbers not regenerated) | 7 | each `.bak_8Oct` |
| lab4/silicon/RESULTS_SILICON.md | Masked-CPA stage 2 "chance level" replaced: 2 of 24 at 8,000 traces has p about 0.004, 32,000-trace entry not run, 3 trials cannot separate a weak leak from luck; trojan "1/beta^2" claim replaced with the measured ratios, censoring of the 61 % cell, 299/300; PUF "below 1e-3" replaced with "none observed" and the rule-of-three bound; dup+parity "corrects all single-bit upsets" limited to counter and key words | 10, 11, 15 | lab4/silicon/RESULTS_SILICON.md.bak_8Oct |
| rtl/hop_engine/README.md | LFSR statement (8 hops for 62.5 % of seeds, 9 for 37.5 %, mean 8.375, exhaustive); keyed-engine area/delay provenance paragraph (two different abc netlists, delay mapping about 18-24 % larger); 11.6 ns run has no stored log; "stays hidden" made conditional on SipHash being a PRF; keyed-RTL "empties after 2 hops" row marked a sanity check; RIPPLE run only validates no-retry path; log snapshot names `*.log.txt`; new exhaustive script listed; mutation row says mutants are not shipped; the table label now says exhaustive, not 300 seeds | 1, 2, 3, 7, 14, 17 | rtl/hop_engine/README.md.bak_8Oct |
| docs/RESULTS.md | LFSR sentence: 8 or 9 hops, mean 8.375, exhaustive, replaces "about 9 on average (max 9 in 39 trials)" | 7 | docs/RESULTS.md.bak_8Oct |
| docs/PLAN_V2.md | "about 9 hops" -> 8 to 9 hops with split and mean | 7 | docs/PLAN_V2.md.bak_8Oct |
| docs/RED_TEAM_IDEAS.md | "about 9" -> 8 to 9 hops, mean 8.375 | 7 | docs/RED_TEAM_IDEAS.md.bak_8Oct |
| docs/DAILY_LOG.md | "~9 hops" -> 8 or 9 hops, split, mean 8.375 | 7 | docs/DAILY_LOG.md.bak_8Oct |
| run_tests.sh | Now also runs lab4/silicon/run_tests.py, lab5, lab6, lab7, hop_model.py, unbias_check.py and (if present) ../ApproxKit/tests/test_units.py; real exit code kept; private temp file instead of shared /tmp/fhss_test.out; header states what is NOT run | 4 | run_tests.sh.bak_8Oct |
| .github/workflows/tests.yml | Same run_tests.sh step, outdated "tail -1" comment removed, states RTL tools and ApproxKit are not run in CI | 4 | .github/workflows/tests.yml.bak_8Oct |
| docs/INDEX.md | "Run all tests (10 test files)" replaced by what is and is not covered | 4 | docs/INDEX.md.bak_8Oct |

## New files

- rtl/hop_engine/model/lfsr_hops_exhaustive.py and results/lfsr_hops_exhaustive.txt (exhaustive LFSR-break distribution over all 65,535 seeds; cross-checked against sim/attack.py on seeds 1..500). Created by the earlier session.
- rtl/hop_engine/results/sim_iverilog.log.txt, sim_verilator.log.txt, formal.log.txt: byte-identical copies (cmp checked) of the git-ignored `.log` files the README cites; the README now cites the `.log.txt` names. The scripts still write `.log`, so re-copy after a re-run.
- docs/CHANGES_8OCT.md (this file).

## Note on the LFSR figure

The audit sampled 100 keys (mean 8.51); the exhaustive run over every seed gives 8 hops for 62.5 % and 9 for 37.5 % (mean 8.375). The exhaustive figure is the one used everywhere. The older sampled "mean 8.4" remains only in rtl/hop_engine/results/randcheck.txt (a stored output, left as is) and is described as a sample in the README.

## Not fixed

- ApproxKit docs (ETA k=2 NMED 0.14 vs 0.135 %, ETA/truncation identical dot-product errors, sub-1 % area differences): outside this repo, not edited.
- FHSS-Link/README.md line 2 still says "PLANNING (no code yet)"; xorshift/other stale counts elsewhere not searched.
- lab4 baseline of 6,890 GE vs synthesised 8,364 GE (overhead percentages) not re-derived.
- Tests that cannot fail (lab6 R7/R8, lab4 TMR, lab5 formula-vs-formula, vacuous skip if sim/ missing) not rewritten; hop_engine mutate.sh not written; 3 test keys not extended; sample sizes (12 trials, 3 seeds) not increased (needs new runs).
- Cloud paths in formal/sby, synth.sh, TOOLS_READY.txt, refsim.py; TOOLS_READY.txt not moved.
- RTL sims, formal, synthesis and ApproxKit RTL regression not re-run (no tools on the laptop).
- lab6 R1 clean-first-300 figure still not printed in run_all_log.txt (documented where it is stored instead).
