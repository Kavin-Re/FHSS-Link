# FHSS-Link: where everything is (7 Oct 2026). Simulation only; hardware untouched.
Run the Python tests: `./run_tests.sh` (10 files in sim/ lab/ lab2/ lab3/, plus lab4/silicon, lab5, lab6, lab7, the rtl/hop_engine Python model checks and, if the sibling ../ApproxKit folder exists, its unit tests; about 2-3 minutes). It does not run the hop_engine RTL simulations, formal proofs or synthesis (iverilog, Verilator, SymbiYosys, Yosys needed; see rtl/hop_engine/README.md) or the ApproxKit RTL regression. Results notes: RESULTS.md (Layers 1-2, attack, adaptive, game, dashboard, coding, classifier), RESULTS_ROUND2.md (ideas 13-29), RESULTS_R3_A.md (GPS, watermark, audio FH, modulation classifier), RESULTS_R3_B.md (control, clock, fingerprint, game LP, capacity, compressed sensing, evolution), RESULTS_R3_C.md (survival codec, hash chain, LMS, Wi-Fi survey tooling, venue, dataset, packaging).
| Folder | Content |
|---|---|
| sim/ | core simulators, attack, adaptive, game, coding, serial protocol, emulator, classifier, ladder, mesh, locate, lpd, plkg, twin, mission, safety |
| lab/ lab2/ lab3/ | Round 3 modules, figures, audio demo (lab/audio/*.wav), dataset (lab3/dataset/) |
| lab/ICE_Lab.html | study lab for the Communication Engineering syllabus (also copied to Documents/University/Coursework/Sem 5/) |
| dashboard/index.html | live dashboard: simulator or log replay, manual jam mode, sound |
| docs/explainer.html | step-by-step spread-spectrum explainer |
| fhss_lab/ | command line: `python -m fhss_lab --help` |
Needs you: run lab3/wifi_survey.sh on your laptop (real scan), review, then commit.
