# Firmware plan (Layer 2) - ESP32 FIRMWARE NOT YET WRITTEN OR TESTED
Update: the portable link logic described below now exists as a host-tested C99 reference in `ref/` (see `ref/README.md` and `ref/docs/VALIDATION.md`); it uses the keyed SipHash schedule, not the LFSR named in this plan. The ESP32 radio HAL port and everything on real hardware are still open. The original plan follows unchanged.

Toolchain not installed on the dev laptop yet (no PlatformIO / arduino-cli). Design from sim/link_sim.py:
- Hop schedule: same 16-bit LFSR as the simulator, hop = state mod M (M = 13 default), seed shared at pairing.
- Slot timing: fixed slot (start 20 ms); TX stamps each packet with slot number; RX resets its slot clock on every good packet.
- Re-acquisition: if no packet for N slots, RX parks on one channel and waits for a beacon (TX sends beacons there periodically).
- ARQ: ACK on the same channel; retry in the next slot, max 3 transmissions.
- Interference node: third board, transmits on one chosen channel at minimum power, own test link only.
- Metrics sent to the laptop over serial: slot, channel, ok/lost, retries. Dashboard reads these.
Open: ESP-NOW channel switch time per hop (measure on the existing board first, 14-20 Oct).
