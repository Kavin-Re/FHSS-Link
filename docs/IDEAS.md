# Ideas backlog (software only, ranked). Hardware stays untouched until Kavin says so.
Status: DONE / NEXT / LATER. "Wow" = how well it shows in a demo or viva.

| # | Idea | Why it is good | Wow | Status |
|---|---|---|---|---|
| 1 | Keyed hop schedule + adaptive jammer that breaks the LFSR one | Real security finding, defence-relevant | high | DONE |
| 2 | Adaptive channel selection (like Bluetooth AFH): blacklist bad channels from ACK statistics; then bandit (UCB / Thompson) | Handles a static or slow jammer better than blind hopping; real cognitive-radio idea | high | DONE |
| 3 | Jammer vs defender game: jammer learns with a small neural net / Q-learning, defender adapts; plot the arms race | Shows where hopping stops being enough | high | DONE (EXP3 jammer, not neural) |
| 4 | FEC and interleaving across hops: Hamming (7,4), then convolutional + Viterbi, then a Reed-Solomon-style erasure code across 4 hops | Turns lost hops into recovered data; goodput vs overhead trade-off | medium | DONE (Hamming, conv+Viterbi, erasure) |
| 5 | Jammer detection and classification from RSSI/PDR time series (static, sweeping, random, follower) | Dashboard shows "what is attacking me" | high | DONE (99% on simulated data) |
| 6 | Live laptop dashboard (web page): channel waterfall, PDR, jammer type, schedule state; fed by the simulator now, by serial from the boards later | The demo surface; same code works with hardware | high | DONE (v1, offline single file) |
| 7 | Protocol spec with golden test vectors (slot timing, packet format, key derivation, resync) and a C reference hop generator tested against Python | Firmware becomes copy-paste later, and the spec is a viva document | medium | PARTLY (serial format + CRC, no C yet) |
| 8 | Emulated device: a software "board" speaking the future serial format, so the dashboard and tests run with no hardware | Lets everything be finished before the boards are touched | medium | DONE |
| 9 | Anti-replay and authenticated beacons (HMAC tag, counter window) | Stops a spoofed beacon from desynchronising the link | medium | LATER |
| 10 | Layer 3 early: Verilog LFSR PN + correlator, testbench, FPGA-ready; show processing gain on a waveform | Ties to your VLSI work; DS-SS side of the story | high | LATER |
| 11 | Hybrid FH/DS-SS (hop plus spread) and optimal split between hop count and Gp for a fixed bandwidth | New design question the literature treats | medium | LATER |
| 12 | Energy and latency cost model: what hopping and retries cost per delivered byte | Honest engineering trade-off | low | LATER |

Order for the week (software only, 30-60 min of your attention a day): see WEEK_PLAN.md.

# Round 2: out-of-the-box ideas (6 Oct). SW = can be built and tested with no hardware. Effort S/M/L. Wow = demo or viva impact.
| # | Idea | What it is | SW | Effort | Wow | Status |
|---|---|---|---|---|---|---|
| 13 | Data in the hop (FH-MFSK) | Let the channel index carry data: hop = (secret schedule + data symbol) mod M, so each hop moves log2(M) bits. Compare throughput and jam resistance with packet-per-hop | yes | M | high | DONE |
| 14 | Key from the air (physical-layer key generation) | TX and RX both measure the same reciprocal RSSI; quantise, reconcile with our Hamming/conv code, hash into the hop key. No pre-shared secret. | yes | M | very high | DONE |
| 15 | Jammer localisation | Three boards measure RSSI of the interferer; trilaterate its position (path-loss model + noise). "Fox hunting" on our own test link. | yes | M | very high | DONE |
| 16 | Low probability of detection | How easily does an eavesdropper's energy detector find us? ROC curves for fixed, FH, DS-SS (below noise floor). Shows why spreading exists in military links. | yes | M | high | DONE |
| 17 | Interactive "Jam the Link" mode | In the dashboard the examiner clicks channels to jam or picks a jammer type and tries to break the link live; the system adapts. Built-in demo hook. | yes | S | very high | DONE |
| 18 | Graceful degradation ladder | Mode switching driven by the classifier: normal, adaptive, repetition code, erasure code, low-rate survival beacon. Critical messages (heartbeat, stop command) get priority over bulk data. | yes | M | high | DONE |
| 19 | Mesh and relay under jamming | Third board as relay; link breaks on one path, route over the other. Graph simulation with per-link loss. | yes | M | medium | DONE |
| 20 | Energy-depletion attack | Jammer forces retries to drain a battery node; defence = backoff and sleep. Battery life vs jammer duty cycle. | yes | S | medium | DONE |
| 21 | Protocol model checker | Exhaustive state-space search of the sync protocol (drift, loss, resync) to find deadlocks; we already found one by accident (never recovers after excess drift). | yes | M | high | DONE |
| 22 | Randomness test suite for schedules | Frequency, runs, serial correlation and entropy tests for LFSR, keyed PRF and chaotic-map schedules; measures what the attack already showed. | yes | S | medium | DONE |
| 23 | Digital twin and auto-calibration | Fit the model's loss parameters per channel from a measured log, then predict the next run; show sim vs real side by side. | yes | M | high | DONE |
| 24 | Mission scenario simulator | Moving nodes, path loss, a fixed jammer on a hill, link margin vs distance (patrol/convoy/UAV command link). A map view in the dashboard. | yes | L | high | DONE |
| 25 | Adversarial classifier test | A jammer that imitates benign traffic to fool the classifier; measure the drop and add a defence. | yes | M | medium | DONE |
| 26 | Poor man's spectrum analyser | ESP32 promiscuous mode scans RSSI per channel into the dashboard waterfall. Hardware phase only. | no | S | high | needs hardware |
| 27 | Safety guard for the interference node | Hard power cap, own-link-only check, duty-cycle limit, kill switch, all logged. Shows responsible design. | partly | S | medium | DONE (policy logic; firmware later) |
| 28 | Opportunistic timing | Derive coarse hop timing from ambient Wi-Fi beacons instead of a dedicated sync channel. Risky research idea. | no | L | medium | needs hardware |
| 29 | Explainable link decisions | A log that says why each channel switch or mode change happened; auditable. | yes | S | medium | DONE |
| 30 | One design, two submissions | Reuse the correlator / hop sequencer RTL (Layer 3) in the PolarFire contest entry. Check the contest's originality rules first. | yes | M | high | blocked: no Layer 3 yet, check contest rules |

## Picks
Most distinctive for a university presentation: 14 (key from the air) and 15 (localisation) are research-flavoured and new for a student project; 17 makes the demo interactive; 13 is the most surprising idea; 18 ties everything built so far into one system story.
Cheap and safe additions: 22, 27, 29.
Suggested next three: 17 (S, demo hook), 22 (S, quick credibility), 14 (M, the showpiece). Then 13 and 15 if time remains.


# Round 3: different areas (7 Oct). Same toolbox (spreading, hopping, correlation, coding, learning), new fields. SW = no boards needed.
| # | Area | Idea | What it is | SW | Effort | Wow | Status |
|---|---|---|---|---|---|---|---|
| 31 | Navigation | GPS-style acquisition and anti-jam | Gold-code generator, Doppler x code-phase search, ranging from the correlation peak; show spreading gain against a jammer and detect a spoofer by its too-clean peak. The civil GPS signal is the world's biggest DS-SS system. | yes | M | very high | DONE |
| 32 | Multimedia security | Spread-spectrum watermark for images and video | Hide a key-seeded pseudo-random pattern in an image, detect it by correlation; test against JPEG, crop, noise and a simple video codec (your codec work). Processing gain = robustness. | yes | M | very high | DONE |
| 33 | Audio | Frequency hopping over sound | Hop between audio tones, generate .wav files with noise and a "jammer" tone, decode with FFT/Goertzel; you can play it on a laptop speaker. A real signal chain with no radio. | yes | M | high | DONE |
| 34 | Real data | Campus 2.4 GHz survey | Your laptop's Wi-Fi card lists every access point's channel and signal strength. Log it for days (channel number and dBm only, no network names) and feed the real occupancy into the simulator. | yes | S | very high | DONE (tooling + synthetic sample; real scan needs you) |
| 35 | Control | Control loop over a hopping link | Simulate a quadrotor altitude or inverted-pendulum controller whose commands arrive over our link; find the delivery rate below which it goes unstable and use it to set the ladder's thresholds. | yes | M | very high | DONE |
| 36 | Time | Clock tamer | A Kalman filter estimates offset and drift from beacon timestamps with jitter, predicts when the next hop falls, and shrinks the guard time. Fewer resyncs, more airtime. | yes | M | high | DONE |
| 37 | Identity | Transmitter fingerprinting | Each crystal has its own ppm error; classify nodes from drift and timing jitter, so a spoofer with the right key but the wrong clock is caught. | yes | M | high | DONE |
| 38 | Game theory | Optimal jammer and defender strategies | Solve the zero-sum game with a linear program (power budget, k channels, costs) and check it against the learning simulations. Gives the guaranteed delivery number. | yes | M | high | DONE |
| 39 | Information theory | Capacity of a jammed link | Capacity of erasure and arbitrarily-varying channels vs hop count; how much of the theoretical limit our codes reach. Matches your ICE unit 5. | yes | S | medium | DONE |
| 40 | Compressed sensing | Find the jammer with few measurements | A wideband spectrum is sparse; recover which channels are occupied from far fewer samples (orthogonal matching pursuit / L1). | yes | M | high | DONE |
| 41 | Evolution | Evolve hop patterns against an evolving jammer | Genetic algorithm co-evolution; see whether it rediscovers uniform randomness or finds structure we missed. | yes | M | medium | DONE |
| 42 | Source coding | Survival-mode codec | Squeeze telemetry (position, battery, status) into a few bytes: delta coding, quantisation, Huffman; rate-distortion curve (your video-codec background). | yes | M | high | DONE |
| 43 | Audit | Tamper-evident decision log | Hash-chained log (optionally a Merkle tree) of the safety guard and ladder decisions; edit one line and verification fails. Touches the blockchain ideas from your friend's project without needing a blockchain. | yes | S | medium | DONE |
| 44 | Signal processing | Adaptive interference cancellation | An LMS/RLS filter removes a known-structure interferer (mains hum, a narrowband tone) from a signal; compare with the spreading approach. | yes | S | medium | DONE |
| 45 | Machine learning | Automatic modulation classification | Tell BPSK, FSK, ASK and DS-SS apart from noisy samples using features and a small network; ties to your ICE modulation unit. | yes | M | high | DONE |
| 46 | Sonification | Hear the link | Dashboard plays a tone per channel; a jammer sounds like a buzz; delivery rate controls pitch. Demo gimmick, also an accessibility view. | yes | S | medium | DONE (dashboard Sound button) |
| 47 | Education | Interactive spread-spectrum explainer | A web page (and short video script) that lets a visitor spread, jam and despread a bit stream step by step; hosted on GitHub Pages. Good for your GitHub profile. | yes | S | high | DONE (docs/explainer.html) |
| 48 | Community | "Classify the jammer" open dataset | Publish emulator logs with labels and a baseline notebook as a small challenge. | yes | S | medium | DONE (lab3/dataset) |
| 49 | Packaging | `fhss-lab` toolkit | pip-installable package, command line (`fhss-lab run`, `emulate`, `bench`), Docker image, GitHub Actions; a real open-source project. | yes | M | medium | DONE (fhss_lab, Docker/CI untested) |
| 50 | Humanitarian | Congested-venue and disaster scenario | Stadium or relief camp with hundreds of phones on Wi-Fi: how many hopping links coexist (collision model, density sweep) and what a message-priority scheme delivers. | yes | M | high | DONE (lab3/venue.py) |
| 51 | ICE study lab (urgent, personal) | Visual lab for your syllabus | Sliders for AM index, FM bandwidth, PCM quantisation SNR, matched filter, eye diagram, TDM/FDM, Huffman; each with the exam formula. Useful before the ICE test. | yes | M | very high | DONE (lab/ICE_Lab.html) |

## Picks
- Biggest jump in diversity: 31 (GPS), 32 (watermarking, uses your codec background), 35 (control), 34 (real campus data).
- Fast and portfolio-friendly: 34, 43, 46, 47.
- Strongest viva answers: 35 (why 90% delivery is enough or not), 38 (the guaranteed number), 36.
- Tie to your tests and contests: 51 for ICE; 31/32 correlators fit the Layer 3 / PolarFire direction; 39 for ICE unit 5.
