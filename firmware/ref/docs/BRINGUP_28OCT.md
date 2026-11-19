# Bring-up checklist, 28 Oct (no hardware work before that date)
Status marks: **UNVERIFIED** = not taken from a cited datasheet/manual in this work; check before relying on it. **REPO** = stated in an existing FHSS-Link file. Nothing in this checklist has been tried on a board.

## 0. Before touching hardware
- [ ] `make test` and `make san` green on the laptop and in the cloud (see VALIDATION.md). Re-run after any edit.
- [ ] Decide the open SPEC items that change constants here: hop rate / channel count, success target PDR, dashboard style (REPO: docs/SPEC.md "Decisions the owner must make"). The code assumes 13 channels, 20 ms slot.
- [ ] Toolchain: REPO says PlatformIO / arduino-cli were not installed on the laptop (firmware/README.md). Install and pin versions first. Exact board package/IDF version: UNVERIFIED.
- [ ] Safety (REPO, SPEC): closed room, own devices only, minimum power, jam node on the owner's own test link, declared to the faculty. The jam node must run the `fh_guard_*` logic below with the production limits (build WITHOUT `FH_SIM_UNSAFE_LIMITS`).

## 1. HAL port (`hal/fh_radio.h`) - to be written, does not exist yet
| HAL call | needs on ESP32 | status |
|---|---|---|
| `set_channel(logical 0..12)` | logical n -> physical Wi-Fi channel n+1 (assumed) | **UNVERIFIED** (regulatory domain may allow fewer channels; channel-switch API and settling time unknown) |
| `tx / rx` | ESP-NOW send + receive callback feeding a small queue; frame max 34 bytes here (`FH_MAX_FRAME`) | **UNVERIFIED** (ESP-NOW payload limit, ACK behaviour - ESP-NOW has its own MAC-level ack/retry that must not be confused with the application ACK) |
| `rx_ts_us` | timestamp of frame START; callback latency vs true start unknown | **UNVERIFIED** (needs measurement; the sync guard window `guard_us` must cover it) |
| `rssi()` / `rxinfo.rssi_dbm` | per-packet RSSI from the receive metadata; channel-energy read for `rssi()` may not exist | **UNVERIFIED** |
| `set_power(level)` | level 0 = lowest TX power setting | **UNVERIFIED** (mapping of level 0/1 to dBm unknown; guard caps at level 1) |
| `now_us` | free-running 64-bit microsecond timer | **UNVERIFIED** (use the platform's 64-bit timer; check it does not stop in light sleep) |
| jam node noise burst | `tx` of a short frame as a burst; real airtime of an ESP-NOW frame unknown (mock uses 1.1 ms) | **UNVERIFIED** |
| Pins | no pin is used by the reference code; USB-serial console only. Any LED/button (kill switch!) pin assignment | **UNVERIFIED**: choose from the board's pinout page, do not guess |
| Serial | `$FH` lines over USB serial; REPO says "115200 baud later" (docs/SERIAL_FORMAT.md) | REPO for the baud rate; the USB-UART/CDC behaviour of the chosen board is **UNVERIFIED** |

## 2. Measurements that replace assumed constants (`fh_cfg_default`, all **UNVERIFIED** until measured)
- [ ] Channel switch time (REPO lists this as the open item, "measure on the existing board first, 14-20 Oct"). Sets the earliest `tx_off_us`.
- [ ] Frame airtime and receive-callback latency. Sets `tx_off_us`, `ack_off_us`, `ack_end_us` (assumed 2 / 8 / 14 ms inside a 20 ms slot).
- [ ] Clock error between boards (assumed 40 ppm worst case relative: `drift_ppm`), `guard_us` (assumed 1.5 ms).
- [ ] Rendezvous: logical channels 1/6/11 chosen by analogy with the non-overlapping Wi-Fi channels (**UNVERIFIED** choice); check the room's real Wi-Fi occupancy first. Search dwell is (nrdv*beacon_period+1) slots per channel = about 1 s with the defaults: measure time-to-acquire.
- [ ] Packet loss on a clean channel (the mock uses 1 % per frame, copied from sim/emu_device.py `p_clean`; not a measurement).
- [ ] Peak stack/RAM of `fh_node_t` (the struct is a few hundred bytes; not measured on target).

## 3. Staged bring-up order
1. Two boards, fixed channel (`hop_enable=0`), run `fh_node_poll` loops, check `$FH` lines parse in the dashboard (Source = Serial) and CRC counter stays 0.
2. Enable hopping, no jammer; compare the channel sequence printed by both boards with the host `fh_hop` for the same key/slots (the host reference is bit-exact with the RTL vectors).
3. Beacon rendezvous: power-cycle the follower at random times; log time-to-acquire; check replayed old beacon is rejected (record one, replay after reboot).
4. AFH/ladder with the guarded jam node at minimum power on ONE channel (host demo scenario `static`/`sweep`); compare qualitatively with `logs/fw_*.log`.
5. Guard: verify with the production build that duty (10 %), burst (2 s), token expiry (5 s) and the kill switch actually stop emission, on a spectrum observation if available. The kill switch input and its debouncing: **UNVERIFIED**/not written.
6. Persist `boot` counter in non-volatile storage and increment it on every boot (rolling counter relies on it); storage API **UNVERIFIED**.
7. Replace the demo master key (public in the repo) with a provisioned secret. Pairing/provisioning flow: not designed.
