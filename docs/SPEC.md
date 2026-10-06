# SPEC (DRAFT for Kavin's approval; nothing below is decided until you say so)
## Purpose
Demonstrate anti-interference behaviour of frequency hopping (FH-SS) against a fixed-frequency link, and relate it to direct-sequence spreading (DS-SS) through processing gain.
## Layer 1: simulator (Python)
- Models: fixed-frequency, FH-SS, DS-SS over an AWGN channel with a narrowband or partial-band interferer.
- Outputs: BER vs SNR, BER vs interferer power, effect of hop rate / number of channels, processing gain Gp = Tb/Tc.
- Deliverable: reproducible scripts + figures + a short results note.
## Layer 2: hardware (3x ESP32, ESP-NOW)
- TX and RX hop over Wi-Fi channels 1..13 using a shared PN schedule, time-synchronised. A third board (interference node) transmits on ONE chosen channel of the owner's own test link at minimum power.
- Metrics: packet delivery ratio (PDR), per-channel loss, recovery after interference starts. Dashboard on the laptop (serial/USB).
- Safety: closed room, own devices only, minimum power, owner declares the node to the faculty. No jamming of other people's networks.
## Layer 3 (stretch): Verilog PN (LFSR) generator + correlator, Vivado simulation, resource report.
## Decisions the owner must make (open)
1. Hop rate and number of channels in the demo.
2. What counts as "success" (target PDR with and without hopping).
3. Dashboard style (terminal vs simple web page).
4. Whether Layer 3 is in scope.
5. Final project name and repository visibility.
## Out of scope
Real RF jamming of third-party systems; SDR hardware; encryption of payloads (possible later upgrade).
