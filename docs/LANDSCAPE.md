# Landscape search (7 Oct 2026): what already exists around FHSS-Link
Method: web search plus fetching GitHub topic pages, repos and arXiv abstracts. GitHub's own repository search was not reachable from the cloud session, so GitHub coverage comes from the FHSS topic page and web search; it is not exhaustive. Claims below are only what the fetched pages stated.

## Closest existing work
| Work | What it is | Relevance |
|---|---|---|
| ExpressLRS (github.com/ExpressLRS/ExpressLRS, GPL-3.0, about 5.3k stars) | open-source FHSS radio-control link for drones, LoRa/FSK on Semtech radios with ESP32/STM32, binding phrase, up to 1000 Hz packet rate | the mature real-world open-source hopping link; sets the quality bar; its 2022 security advisory (Fox-IT) reported hijack of the control link via the pairing/sync design |
| Praetorian, "RF Fortune Telling: Frequency Hopping Predictability" | analysis of a commercial nRF24-based hopping device whose PRNG had about 9 bits of effective randomness, so the full sequence could be mapped | prior art for our "LFSR is predictable" result; they recommend a keyed hash with synchronised time |
| cirradio (mangobanaani, MIT, about 6 stars) | tactical UHF FHSS mesh radio: Zynq FPGA + AD9361, 11,480 channels, AES-256 hop sequencing, EMCON modes, 128 C++ tests, simulation-verified, board designed | the high-end "RTL hop engine" analogue; shows a hop engine in SystemVerilog is a known pattern, so a student version should be small and verified, not claimed as new |
| nRF24 FHSS repos (Max-62, about 104 stars; CABELL RC receiver, about 88 stars; FHSS_Research) | hobby firmware for nRF24L01 radios | no jamming or security analysis in the pages fetched |
| FHSS-Hopping-Estimation (jx9527, about 47 stars) | LSTM identification of hop points with HackRF | the attacker/analysis side of the same field |
| PyJama (ETH, arXiv 2407.15473) | open-source differentiable jamming and anti-jamming library on NVIDIA Sionna, OFDM, FEC, channel models | high-fidelity simulation; our simulator is deliberately simpler |
| StormWave (arXiv 2605.04290, 2026) | open-source portable SDR platform (USRP B210/N210) for interference resilience tests, ground and air-to-air | the hardware-test side at a much larger scale |
| JamShield (arXiv 2507.11483) and the IEEE DataPort jamming datasets | ML jamming detection, 97.9% detection on 802.11 features with a public dataset; a vehicular-network jamming dataset also exists | public real datasets exist, so our simulated classifier dataset has low standalone value; better to validate against these |
| "Reinforcement Learning for Deceiving Reactive Jammers" (arXiv 2103.14056) | decoy-channel deception against a reactive jammer, Q-learning | prior art for our honeypot-channel idea |
| "Frequency hopping does not increase anti-jamming resilience of wireless channels" (arXiv 1512.06645) | information-theoretic result: without common (shared) randomness, hopping gives no capacity benefit over a fixed channel when the jammer can match the sender's power; hopping helps once communication is possible | the theory backdrop for our results: our gains rely on a secret shared schedule and a power-limited jammer |

## What looks open for a student project
1. Honest, reproducible evidence on when hopping helps and when it does not, with theory, Monte Carlo and (later) hardware numbers side by side. Hobby repos have no such analysis; PyJama and StormWave are far heavier.
2. A hopping link on ESP32/ESP-NOW. The pages found cover nRF24, LoRa and FPGA/SDR systems; nothing specific on ESP-NOW hopping turned up. Physical constraints (channel-switch time, Wi-Fi overlap) are unknown until measured.
3. A design-attack-fix methodology for the schedule and protocol (PRNG break, timing leak, beacon jamming, replay) packaged as a runnable test suite. ExpressLRS's advisory and Praetorian's article show real systems get this wrong.

## What is not novel (say so in the viva)
LFSR/weak-PRNG hop prediction; decoy-channel deception; ML jammer detection on simulated data; spread-spectrum watermarking and GPS acquisition (textbook). Present these as replications or supporting experiments.

## Name check (shallow)
"HopGuard": no relevant project found. "Kavach": the name of a well-known Indian rail safety system, so confusing. "Chakravyuh": a common name. Searches were not exhaustive; check GitHub and Google before final use.

## Sources
github.com/topics/fhss; github.com/ExpressLRS/ExpressLRS; en.wikipedia.org/wiki/ExpressLRS; praetorian.com/blog/rf-fortune-telling-frequency-hopping-predictability; github.com/mangobanaani/cirradio; github.com/Max-62/nRF24L01-Frequency-Hopping-FHSS; arxiv.org/abs/2407.15473; arxiv.org/abs/2605.04290; arxiv.org/abs/2507.11483; arxiv.org/abs/2103.14056; arxiv.org/abs/1512.06645; fox-it.com technical advisory on ExpressLRS.
