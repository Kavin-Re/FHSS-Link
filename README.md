# FHSS-Link (working name): a frequency-hopping link that survives interference
Status: PLANNING (no code yet). Owner: Kavin K K. Built with Claude under supervision; every design decision is the owner's.

Goal: show, in simulation and on real ESP32 hardware, that a pseudo-random frequency-hopping link keeps working when a fixed-frequency link is knocked out by in-band interference. Defence framing: resilient field communications.
Layers: (1) Python simulator, (2) three-ESP32 hardware demo + dashboard, (3) Verilog PN generator/correlator (stretch), (4+) upgrades chosen later.
See docs/SPEC.md and docs/ROADMAP.md.
