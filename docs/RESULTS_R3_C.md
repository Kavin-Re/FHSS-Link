# Results, round 3, batch C (software-only modules)

Every number below was printed by the scripts in `lab3/`; the raw printouts are saved in `lab3/outputs/*.txt` (same file names as the scripts).
Everything is simulation or synthetic data; nothing was measured on hardware or on a real Wi-Fi network. Assumptions sit in each file's docstring.
`python3 lab3/test_batchC.py` runs 82 checks and ended with ALL PASSED (`lab3/outputs/test_batchC.txt`).

## 1. Survival telemetry codec (`lab3/survival_codec.py`, figures `survival_rd.png`, `survival_loss.png`)
Setup: 10 km box, 1 msg/s random-waypoint patrols (30 training and 12 test trajectories of 600 messages), 0.7 m GPS jitter, canonical Huffman per delta field
trained on the training set, CRC-8 (poly 0x07), keyframe every 20 messages unless stated.
- Keyframe at 1 m / 5 deg / 0.5 m/s / 1 %: 66 bits, 9 bytes (4-bit sequence number, 14+14 bit position, 7-bit battery, 4 flags, 7-bit heading, 6-bit speed, stop, CRC-8).
- Delta + Huffman: 4.01 bytes per message on average, against 9.00 for all-keyframe at the same quality (55 % smaller).
- Rate-distortion (bytes/msg -> position RMS error): 4.44 -> 0.41 m (1 m, 1 deg); 4.01 -> 0.41 m (1 m, 5 deg); 3.65 -> 0.82 m (2 m); 3.37 -> 1.63 m (4 m);
  3.26 -> 3.28 m (8 m); 3.21 -> 6.51 m (16 m); 3.15 -> 13.06 m (32 m, 45 deg). Coarser quantisation saves little after the first step: the curve flattens near
  3.15 bytes because type/sequence/flags/stop/CRC bits and at least one Huffman bit per field remain. The 0.41 m at 1 m step is quantisation error only (0.29 m per axis x sqrt 2),
  measured against the already-noisy GPS value.
- Dead-reckoning predictor (delta against previous position + previous delta) did not help: 4.03 vs 4.01 bytes at 1 m / 5 deg; 4.38 vs 4.44 at 1 m / 1 deg. GPS jitter dominates the residual.
- Single-bit corruption (every bit position of 60 messages, 2416 flips): 2220 detected, 194 hit only the unprotected padding bits (decoded identical), 2 accepted with wrong content.
  The two are a real weakness: a flip can change how the variable-length code is parsed, then the CRC is read from the wrong place (about 1/256 false-accept chance for such flips).
- Lost messages, mean position error / fraction of messages more than 5 m off / fraction flagged stale (N = naive decoder that applies every delta; G = gap-aware decoder that holds the last good state and waits for a keyframe):

  | K | bytes/msg | loss 5 %: N | loss 5 %: G | loss 20 %: N | loss 20 %: G |
  |---|---|---|---|---|---|
  | 1 | 9.00 | 0.5 m, 0.005 | 0.5 m, 0.005, stale 0.048 | 3.6 m, 0.024 | 3.6 m, 0.024, stale 0.197 |
  | 5 | 4.80 | 0.7 m, 0.018 | 1.2 m, 0.058, stale 0.146 | 16.0 m, 0.107 | 17.8 m, 0.222, stale 0.455 |
  | 20 | 4.01 | 1.6 m, 0.068 | 8.1 m, 0.298, stale 0.377 | 62.2 m, 0.372 | 79.0 m, 0.678, stale 0.790 |
  | 50 | 3.85 | 3.2 m, 0.156 | 27.7 m, 0.543, stale 0.590 | 152.6 m, 0.671 | 195.0 m, 0.867, stale 0.908 |

  Reading: a lost delta leaves a wrong or stale state until the next keyframe, so the damage scales with K x loss rate. Honest finding: in this slow-patrol model the naive decoder shows
  the smaller position error (a missed delta only shifts the position by the few metres the node moved), but it hardly ever knows it is wrong (stale fraction at most 0.018, except 0.109 for K=50 at 20 % loss); the gap-aware decoder knows
  (it flags stale) but its held position drifts from the moving node. A decoder that dead-reckons while stale, or a faster-moving node, would change this comparison; not tested.
  Cost of resynchronisation: K=5 costs 4.80 bytes/msg versus 4.01 at K=20.
- Caveats: simulated motion only; Huffman tables are specific to this motion model (retrain on real patrol logs); message length is assumed to come from the framing layer;
  4-bit sequence cannot detect 16 consecutive losses; no forward error correction.

## 2. Tamper-evident decision log (`lab3/hashchain.py`, `lab3/verify_log.py`, `lab3/sample_log.jsonl`, `lab3/sample_log_hmac.jsonl`)
Log of 71 decisions (17 mode-switch records from three `sim/ladder.py` runs, 54 `sim/safety.py` Guard events), SHA-256 chain, Merkle root per block of 16 (5 blocks).
- Without recomputation by the attacker, for every position of the 71-record log: edit 71/71 detected and flagged at exactly the edited index; delete 71/71 at exactly that index;
  insert 71/71 at exactly that index; swap of neighbours 70/70 at the first of the two. The Merkle block check independently flagged the affected block in the CLI test (edit of record 40 also reported block 32..47).
- Tail truncation is not caught by the chain alone: dropping the last seal and 2 records still verified OK; it is caught with an anchored head hash. Dropping the last 3 records while keeping their block seal is flagged (first index 68).
  A clean cut at a block boundary also verified OK alone and was flagged with an anchored count or head.
- This is integrity, not authenticity. An attacker who edits record 20 and recomputes the whole chain is ACCEPTED by the plain verifier (ok=True); it is caught only with an anchored head hash. With the HMAC variant
  (`hmac-sha256`, key held by the verifier) a log rebuilt without the key is rejected (first flagged index 0, because the whole log was rebuilt with a wrong key); with the wrong key the genuine log is rejected too.
  HMAC is symmetric: anyone with the key can forge, and it cannot prove to a third party who wrote the log; a public-key signature would be needed for that (not implemented). The demo key is printed in the repo and is not secret.
- Merkle inclusion proof for one record in a 16-record block: 4 hashes (128 bytes), verifies; against a different record it fails.
- Speed: 20,000 records written in 0.24 s and verified in 0.34 s.
- CLI exit codes: 0 consistent, 1 tampering (names the index), 2 usage/missing key. Timestamps inside records are just data and are not trusted.

## 3. Adaptive interference cancellation (`lab3/lms_cancel.py`, figures `lms_overview.png`, `lms_drift_hop.png`)
Setup: fs = 2000 Hz, white +-1 chips, 400 Hz tone (+-5 Hz drift) at +30 dB, 50/150/250 Hz hum at +20 dB, noise at -10 dB, so SINR_in = -30.4 dB; 64-tap adaptive line enhancer, delay 1.
Step sizes were tuned on the same scenario (optimistic); 3 seeds, 16,000 samples.
- SINR improvement at the best setting: LMS 34.2 dB (normalised step 0.1), NLMS 33.7 dB (0.1), RLS 32.8 dB (forgetting 0.9995). LMS and NLMS are nearly identical at every step size.
  Improvement vs step size (LMS): 9.4 dB at 0.001, 19.1 at 0.01, 27.4 at 0.03, 34.2 at 0.1, 32.9 at 0.3, 28.8 at 1.0: too small is slow, too large adds misadjustment noise.
- Convergence time (within 3 dB of final, sustained): LMS 0.1 takes 4667 samples (2.3 s), LMS 1.0 takes 600 samples (0.3 s) but reaches 28.8 dB; RLS 0.99 takes 400 samples (200 ms) with 30.8 dB; RLS 0.9995 takes 1200 samples with 32.8 dB.
- Linear frequency drift (best grid step per rate, improvement dB, LMS/NLMS/RLS): 0 Hz/s 33.9/33.1/32.6; 100 Hz/s 29.2/28.3/28.0; 500 24.4/23.8/22.0; 2000 18.2/17.8/10.4; 8000 7.5/7.5/0.3.
- Hopping interferer (random frequency 150-900 Hz every `dwell` samples, 2000 samples = 1 s; LMS/NLMS/RLS): 4000 samples 21.0/21.5/22.3 dB; 1000: 16.8/16.9/18.7; 400: 12.6/12.6/14.5; 200: 10.3/10.3/12.2;
  100: 7.1/7.1/8.8; 50: 4.5/4.5/5.0. With a wideband interferer of the same power the RLS gain was 0.0 dB.
- Spreading gain for the same chip stream (fresh random code per bit, bit-level SINR): despreading alone gives -18.3 / -12.2 / -6.6 dB for Gp = 16 / 64 / 256 (= -30.4 + 10 log Gp within 0.3 dB);
  canceller alone (chip level) +2.5 dB (about 33 dB improvement); canceller followed by despreading 14.5 / 20.8 / 26.9 dB. BER at Gp = 64 over 8 seeds: despreading only 0.4006 (1282/3200);
  canceller + despreading 0 errors in 1600 bits; canceller only (1 chip = 1 bit) 0.0936.
- When it fails: the canceller needs the interferer to stay put for longer than its convergence time. In this setup RLS improvement falls below the Gp = 64 spreading gain (18.1 dB) between dwell 1000 (18.7 dB)
  and dwell 400 (14.5 dB), i.e. when the tone moves faster than about every 0.2-0.5 s, and below the Gp = 16 gain (12.0 dB) at about 200 samples dwell (12.2 dB at 200, 8.8 at 100). Spreading gain does not depend on the hop rate. It also fails for a wideband interferer (0.0 dB).
- Reasoning, not a measured result: the two methods work on different properties and stack. The canceller removes what is predictable (narrowband, slowly moving) at no bandwidth cost but only works because the wanted signal is wideband/white;
  despreading buys a fixed Gp at the price of Gp times the bandwidth.
- Caveats: single-input line enhancer (no separate reference), white +-1 signal is the best case for it, absolute times depend on the assumed 2000 Hz sample rate, hop dwell results use the best step per dwell (optimistic), only 2-3 seeds.
  The full script takes about 2 minutes to run.

## 4. Campus Wi-Fi survey tooling (`lab3/wifi_survey.sh`, `lab3/wifi_survey.py`, `lab3/synthetic_wifi_survey.csv`, `lab3/synthetic_channel_loss.json`, figure `wifi_survey.png`)
The shell script was NOT run against a real radio (no scan was performed). It passed `bash -n` and tests with a fake `nmcli` and a fake `iw` on PATH: 5 GHz rows dropped, dBm = pct/2 - 100 for nmcli,
iw SSID/BSSID text never appears in the CSV, an empty scan writes a channel-0 marker row, bad arguments exit 2. The nmcli call is exactly `-t -f CHAN,SIGNAL,FREQ dev wifi list`; the iw fallback reads `scan dump` (cached results, no root).
The pct to dBm mapping is the common NetworkManager convention, not a calibration of any driver.

Everything below is from the SYNTHETIC file (36 fake APs, 3 days, scan every 10 minutes = 432 scans; header and JSON are labelled synthetic). It shows that the analyser works, not what the campus looks like.
- Busiest channels: 6 (6.66 APs/scan), 11 (6.06), 1 (4.96); 30 % of APs sit on channels other than 1/6/11. 1/6/11 view (APs per scan): ch 1 group 5.85, ch 6 group 9.95, ch 11 group 9.53.
- Effective channels for hopping over the 13-channel grid: M_eff_sum = 7.36 (sum of availability), M_eff_ipr = 12.73 (barely informative here: availability is fairly even), 3 non-overlapping Wi-Fi channels,
  3.7 independent 22 MHz slots in the grid; one mid-band AP shadows 4.45 channel-equivalents (triangular overlap model).
- Loss map with the ASSUMED u = 0.10 airtime per AP: from 0.246 (channel 13) to 0.547 (channel 6); mean 0.434. The mapping (documented in the file and in the JSON) is an assumption: presence and strength are surveyed, airtime is not.
- Time of day (built into the generator): 32.4 APs/scan and M_eff_sum 6.04 at 12h and 13h versus about 21.2-22.0 APs/scan and M_eff_sum 8.0-8.2 between 00h and 07h.

## 5. Congested venue model (`lab3/venue.py`, figures `venue_delivery.png`, `venue_jain.png`)
Defaults: M = 13, critical load 0.1 per slot, bulk load 0.5, background Wi-Fi busy 0.2 per channel and slot, residual loss 0.01, critical messages get 3 attempts, sensing reliability rho = 0.9.
- Analytic vs Monte Carlo (plain): per-attempt success 0.792 (N=1), 0.518 (N=10), 0.323 (N=20), 0.125 (N=40), 0.019 (N=80); the Monte Carlo matched within 1.77 times its 95 % half-width at every one of 10 values of N.
- Priority (critical picks first, bulk avoids sensed critical channels): critical message delivery at N = 40 is 0.331 without priority and 0.878 analytic / 0.880 Monte Carlo with it; bulk per-attempt delivery at N = 40 falls from 0.125 to 0.100 analytic / 0.101 MC (priority is paid for by bulk).
  Critical-priority analytic is exact for the model; the bulk-priority formula is an approximation that stayed within 0.01 of the MC in the printed table.
- Knee (smallest N with critical delivery < 0.95), M = 4 / 8 / 13 / 16 / 32: plain 3 / 4 / 6 / 7 / 13; priority (rho 0.9) 7 / 14 / 21 / 26 / 50; priority with perfect sensing (rho 1) 10 / 19 / 31 / 38 / 74.
  MC at the M = 13 priority knee: 0.952 at N = 20 and 0.949 at N = 21. Sensitivity (M = 13): background 0.0 / 0.1 / 0.2 / 0.3 / 0.4 gives plain knee 11 / 9 / 6 / 3 / 1 and priority knee 40 / 31 / 21 / 10 / 1;
  critical load 0.05 / 0.1 / 0.2 / 0.4 gives priority knee 31 / 21 / 13 / 8. A knee of 1 means critical delivery is already below 0.95 for a single link: at background 0.4, or with one attempt (R = 1, per-attempt success 0.79 at background 0.2).
- Jain index, M = 13, bulk loads drawn from U(0.1, 0.9): delivery ratio per link 0.9998 (N=5) to 0.9951 (N=80) without priority, but with priority 0.9786 at N = 40 and 0.8588 at N = 80, because links with more bulk traffic lose more.
  Throughput Jain is 0.82-0.88 (offered-load Jain 0.83-0.89), i.e. the unfairness there is the unequal offered load, not the channel access. Identical links: 0.9998.
- A structured background (three channel blocks busy in turn) with the same average gave single-link success 0.7895 versus 0.7920 for the uniform formula.
- Caveats: aligned slots, independent uniform hopping, no capture effect, retries not added to the load, background iid per channel and slot, the priority mechanism is a model (not implemented in firmware). Analytic and Monte Carlo share the same assumptions, so their agreement checks the maths, not the assumptions.

## 6. Packaging (`pyproject.toml`, `fhss_lab/`, `Dockerfile`, `.github/workflows/tests.yml`)
`python -m fhss_lab --help` and the `run`, `emulate`, `classify`, `bench` subcommands work (called through subprocess in the test file). Example outputs: `run` prints BER at Eb/N0 10 dB and JSR 10 dB of 0.42985 (fixed), 0.03295 (FH) and 0.04880 (DS Gp 32) with 20,000 bits;
`emulate` wrote 200 CRC-valid serial lines; `classify` printed rule-based 0.940 and softmax 1.000 on 150 fresh simulated windows (small sample); `bench --only test_proto.py test_safety.py` printed ALL PASSED.
- The Dockerfile and the GitHub workflow were NOT built or run (no docker in the VM; no GitHub run). The workflow YAML parsed with PyYAML. `pip install -e .` was not run.
- Finding: `run_tests.sh` pipes every test into `tail -1`, so the shell reports success even when a test fails (checked: `sh -c 'false | tail -1'` exits 0). The workflow therefore runs `./run_tests.sh` as asked and then `python -m fhss_lab bench`, which uses the real exit codes. Suggest changing `run_tests.sh` (not edited here).
- `fhss_lab` imports `sim/` by path (appended to `sys.path`, or `FHSS_SIM_DIR`); it works from a checkout or an editable install, not from a plain wheel.

## 7. Dataset (`lab3/make_dataset.py`, `lab3/dataset/`)
6500 simulated windows (1300 per class: none, static, sweep, random, reactive) with M in {8, 13, 16, 24, 32}, W in {100, 150, 200}, duty in {1, 0.75, 0.5, 0.25}, jammer strength 0.5-0.99; stratified split 5200 train / 1300 test (seed 12345); four raw serial logs of 1500 CRC-valid lines.
922 windows (14.2 %) have fewer than 3 lost packets, so their structure features are zero (none 577, static 73, sweep 131, random 141, reactive 0); they are ambiguous on purpose.
Baseline test accuracy (`dataset/baseline.py`): majority 0.200, nearest centroid 0.739, softmax 0.816. Softmax per-class recall: none 0.988, static 0.719, sweep 0.727, random 0.673, reactive 0.973; by M: 0.924 (M=8), 0.839 (13), 0.823 (16), 0.788 (24), 0.711 (32).
The errors are mostly static/sweep/random windows predicted as none (28, 36 and 50 of 260) and confusion among the three. The dataset is simulated (README says so) and MIT licensed; accuracy here says nothing about real RF.
