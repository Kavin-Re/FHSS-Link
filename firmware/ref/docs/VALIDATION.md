# What is and is not validated (firmware reference, host only)
Everything below ran on x86-64 Linux with gcc, in the cloud container and on the laptop. **Nothing has run on an ESP32 or any radio.**

## Validated (evidence = `make test`, `make san`, `make fuzz`)
| item | how | result |
|---|---|---|
| SipHash-2-4 | paper vector (15 bytes), reference vectors for lengths 0 and 8 | pass |
| CRC-16/CCITT-FALSE, CRC-8 | check values 0x29B1 and 0xF4 for "123456789" | pass |
| Keyed hop schedule | all 5 vector sets in `rtl/hop_engine/vectors`: M=13 (3 keys x 20,000, incl. the 2^56 wrap run), RW=8 NCH=1 (retries) and NCH=4, M=16, M=37: 106,000 hops, channel AND retry count (vector word = retries<<8 \| channel; this encoding was inferred from the files and then confirmed by 0 mismatches, including the 692 retry cases) | 0 mismatches |
| Hop vs Python model | 4,000 random (key, slot, M, RW, NCH) cases vs `hop_model.hop`, including channel, retries, first digest | 0 mismatches |
| Serial protocol | 3,000 encodes byte-identical to `sim/serial_proto.encode`; 6,000 valid/mutated lines: every line the C parser accepts is accepted by the Python parser with the same fields, and every line Python rejects C rejects; all 5 demo logs parse with `serial_proto.parse` | 0 mismatches |
| Safety guard policy | the ORIGINAL `sim/safety.py` (time constants rescaled seconds->ms by text substitution) vs C on 300 random traces: 62,532 requests, 2,637 token events | 0 mismatches. The C token tag is SipHash-2-4 (64-bit), Python's is HMAC-SHA256; only accept/reject is compared |
| Degradation ladder | C vs a Python transcription of the controller in `sim/ladder.py`, 60 random outcome sequences | 0 mismatches (a transcription: this checks the port, not the design) |
| Packet layer | round trip; all single-bit flips rejected; CRC-fixing forger without key rejected by MAC; wrong key; length/type/plen errors; replay window; rolling counter | pass |
| Sync state machine | acquisition on beacon only, replayed old beacon rejected, guard window, TRACK/LOST/SEARCH transitions, rendezvous dwell | unit tests pass |
| Whole link on the host | `sim/demo.c`: TX, RX (starts unsynchronised with a different boot offset and +35 ppm clock) and JAM in one process; deterministic (same seed gives byte-identical logs, checked by md5) | runs; see `logs/*.summary.txt` |
| Memory safety | ASan+UBSan: unit tests, 2 x 2,000,000 fuzz iterations (packet / serial / sync / guard / hop-map mutation), full 3,000-slot demo | clean. The fuzz run found and fixed one real defect: `fh_sync_search_channel` looped for ~2^64 iterations when `now_us < dwell_start_us` |
| No allocation | `nm -u` on every src object: no malloc/calloc/realloc/free | pass |
| Strict build | `-std=c99 -Wall -Wextra -Wpedantic -Wshadow -Wconversion -Werror` | clean (sanitizer builds add `-Wno-sign-conversion`; a gcc quirk at -O1 with sanitizers) |

## Not validated / known limits
- Timing: every constant in `fh_cfg_default` is an assumption. The mock has zero air time, zero channel-switch time, zero callback latency, so the slot timing and guard windows are exercised only against the modelled crystal drift (+35 ppm / -20 ppm), not against real jitter.
- The radio, interference and loss models are mine: loss 95 % on a jammed channel and 1 % otherwise are copied from `sim/emu_device.py`, the 30 % corrupted-instead-of-dropped share, the 1.1 ms burst and the RSSI figures are arbitrary. Results in `logs/*.summary.txt` show the state machines behave sensibly under that model; they are not performance claims about the real link.
- AFH sampling is an approximation (mean + uniform noise with the Beta standard deviation), NOT a Beta draw, so it is not statistically identical to the numpy Thompson sampler; tested only for behaviour (jammed channels leave the map). The counts update (gamma 0.99, floor 0.001) follows `sim/adaptive.py`.
- CODED mode: only the 5-try critical budget and the blind hop are implemented; the (7,4) erasure code for bulk data is NOT implemented, so bulk goodput in CODED mode is not comparable to `sim/ladder.py`. SURVIVAL sends 1-byte probes instead of bulk so the loss estimate keeps running.
- The wide/multi-channel jam scenarios (`phases`) emulate the multi-emitter jammer of `sim/ladder.py` and count as ONE emission in the guard; the real single-board jam node can only occupy one channel. The jam burst timing is aligned to the master's slots (worst case for the defender, unrealistic for an unsynchronised jammer). The control token reaches the jam node by a direct function call, not over the radio. The jam node does not know the hop key (as intended); a reactive jammer is not modelled.
- Guard differences from `sim/safety.py`: `gap_reset_ms` (burst counter restarts after a pause; the Python version only resets it on a denial), fail-safe deny when the 128-entry decision ring is full, hard compile-time caps (`FH_HARD_*`, relaxed only by `FH_SIM_UNSAFE_LIMITS`, which only the host demo defines). The kill switch is a function call; no physical input exists.
- Serial parser is stricter than Python's: decimal only, 0/1 for `ok`, uint32 slot, rssi in -128..127, hex tag of 1-2 digits. Python accepts things like `+5`, `1_0`, `0x1F`.
- `fh_slot_extend` assumes the receiver's slot estimate is within 2^31 slots of the sender's; a follower that has never synchronised extends from 0, so a master already past slot 2^32 (about 2.7 years at 20 ms) would need the beacon to carry the high bits.
- Rolling counter needs the caller to persist `boot`; the ref never touches non-volatile storage. The demo master key is public.
- Fuzzing the sync state machine with random packets rarely reaches deep states (11 accepted acquisitions in 2M iterations); the unit tests and the demo cover those paths instead. No coverage measurement was run. No fuzzing of `fh_link.c` beyond the demo.
- Replay of the SAME slot data frame through the link is stopped by the per-(origin,class) replay window, but a delayed (not duplicated) valid data frame inside its time guard is accepted; there is no encryption of payloads (REPO SPEC: out of scope).
- Stack/RAM/flash footprints and execution time on the target were not measured.
- `firmware/ref_stage/` on the laptop is an empty directory left by the delivery transfer (deletion was not permitted); `firmware/ref/_transfer/*.tgz` holds the transfer archives. Both can be deleted.
