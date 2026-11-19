# Umbrella brainstorm (7 Oct 2026): FHSS-Link as one corner of a bigger project
Working idea: a "resilient field node" platform. FHSS-Link is the radio corner. Name candidates: SENTINEL, KAVACH-NET, ANTARA, HALO. Pick later.

## Architecture (each layer is one place a corner can be added)
| Layer | Job | Status |
|---|---|---|
| L0 Medium | ESP32 radio now; later LoRa, acoustic, optical fallback; SDR/FPGA baseband | ESP32 plan, audio demo done |
| L1 Resilient link | hopping, spreading, coding, ladder | built in simulation (FHSS-Link) |
| L2 Trust | keys from the air, authenticated beacons, node fingerprint, tamper-evident log | built in simulation |
| L3 Awareness | spectrum sensing, jammer classification and localisation, GPS spoof check | built in simulation |
| L4 Mission payload | haptic cues, telemetry, drone control, sensors | NOT built |
| L5 Operator | map and dashboard, alerts, sound | dashboard v1 |
| L6 Assurance | digital twin, model checker, dataset, benchmark | built |
Gap: L0 beyond ESP32 and all of L4. Those are where new corners go.

## Directions, ranked
1. Silicon corner: an FHSS baseband IP in Verilog (hop sequencer, keyed schedule via HMAC/ChaCha, correlator, CRC, Viterbi), synthesised for the PolarFire board; later an open-source RTL-to-layout run. Ties to VLSID, NPTEL, the PolarFire contest (check originality rules) and your approximate-computing line (approximate correlator: area vs detection loss).
2. Multi-medium link: RF, then acoustic, then light, with the ladder switching medium when a whole band is jammed. Audio hopping already exists; add optical (LED/photodiode or screen-camera) and LoRa-class low rate.
3. Silent squad comms: haptic cues over the resilient link (your Haptic-Sense idea as the payload). Covert, hands-free, no screen or sound.
4. Spectrum guardian: a passive node that watches the band, classifies and localises interference, and raises alerts (exam halls, campus, labs). Detection only, no transmission.
5. Drone link guard: control-link ladder with return-to-home policy, GPS spoof monitor, networked-control thresholds already computed.
6. RF capture-the-flag range: red-vs-blue scoring platform with challenges built from our results (break the LFSR hop, find the jammer, recover the key). Fits a security university; run it as an event.
7. Resilience benchmark: a standard set of jammer scenarios and a 0-100 score for any link configuration; open leaderboard; the dataset becomes its test set.
8. Research paper: "Keyed schedules, learning defenders and graceful degradation: a simulation study with an open toolkit" (arXiv or IEEE student conference). You write the prose; Claude supplies numbers, reasoning and reproducible scripts.
9. Teaching kit: spread-spectrum lab kit (two or three ESP32 boards, web lab, worksheets) for colleges; workshops, course, small income. Uses explainer, ICE_Lab-style labs, dashboard.
10. Voice: push-to-talk over the survival link with a low-rate vocoder.

## Wild cards
- Satellite pass: LEO link with Doppler and hop-timing; reuses GPS acquisition.
- 3D "RF fog" view: spectrum as a live 3D surface in the browser.
- Co-simulation hub: any module (jammer, defender, channel model) plugs in through a small API; students swap parts.
- Hackathon packaging: Smart India Hackathon and similar problem statements on drones, GPS jamming, secure comms (verify current statements first).
- Defence-innovation programmes and grants: check eligibility and current calls before planning around them.

## How to organise
One repository (monorepo) with a folder per corner, a docs site, one daily log, and one commit per working day on a different corner. 30 days then show a visible spread across layers, not 30 commits in one file.
