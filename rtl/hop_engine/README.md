# FHSS-Link keyed hop engine (RTL, simulation + synthesis estimates)

Small synthesizable hop-schedule engine that replaces the 16-bit LFSR schedule (`sim/schedule.py: lfsr_schedule`, pinned down by `sim/attack.py: LfsrBreaker` after 8 observed hops for 62.5 % of seeds and 9 for the rest, mean 8.375, exhaustive over all 65,535 seeds) with a keyed PRF, plus the LFSR itself as a hardware reference for comparison.

**Status in one line:** bit-exact against a Python model in simulation (iverilog and Verilator), formally checked for a few safety properties, synthesized with Yosys to generic gates and to sky130_fd_sc_hd cells. **Nothing here is silicon, FPGA-timing-closed, or power-measured.** All numbers are tool estimates, listed with their limits below.

## What is in here

| path | what |
|---|---|
| `rtl/hop_keyed.v` | keyed engine: SipHash-2-4 (iterative, 1 SipRound/clock) + Lemire unbiased reduction to 0..M-1 |
| `rtl/hop_lfsr.v` | reference engine: 16-bit LFSR, x^16+x^14+x^13+x^11+1, `hop = state mod M`, same as `sim/link_sim.py lfsr_hops` |
| `model/hop_model.py` | bit-exact Python reference (SipHash-2-4 validated against published vectors, keyed hop, LFSR) |
| `model/gen_vectors.py` | writes `vectors/*.mem` (expected channels, retry counts, SipHash digests, keys, start slots) |
| `tb/tb_hop_keyed.v`, `tb/tb_hop_lfsr.v` | self-checking testbenches (compare RTL to the vectors, count cycles, dump the RTL channel stream) |
| `model/randcheck.py` | randomness/predictability battery from `sim/randtests.py`, run on the RTL output streams; also runs the LFSR-break attacker |
| `model/lfsr_hops_exhaustive.py` | exact LFSR-break hop count over all 65,535 seeds (cross-checked against `sim/attack.py`) |
| `model/unbias_check.py` | exact integer proof that the Lemire reduction is unbiased (every RW/M combination tested) |
| `scripts/*.sh` | `run_all.sh` (everything), `run_sim.sh`, `run_verilator.sh`, `synth.sh` (+`abc_time.script`), `run_formal.sh`, `collect.py` |
| `formal/` | SymbiYosys job files (`keyed.sby`, `lfsr.sby`); the properties live in the RTL under `` `ifdef FORMAL `` |
| `results/` | (tracked snapshots of the script logs are kept as `*.log.txt`; re-copy them after re-running. Since Nov 2026 `.gitignore` also allows `rtl/**/results/*.log`, which is how the hop_engine_v2 and approx_correlator logs are tracked) all logs and extracted tables: `SUMMARY.txt` (synthesis), `sim_iverilog.log.txt`, `sim_verilator.log.txt`, `randcheck.txt`, `lfsr_hops_exhaustive.txt`, `formal.log.txt`, `unbias_check.txt`, `lint.txt`, `synth/` (raw yosys stat/ltp/abc output) |
| `vectors/` | generated test vectors (deterministic, regenerable with `model/gen_vectors.py`) |

No existing FHSS-Link file was modified; everything is new under `rtl/hop_engine/`.

## The keyed engine

```
digest  = SipHash-2-4(key[127:0], msg64)        msg64 = { retry[7:0], slot[55:0] }  (little-endian 8-byte message, 8 rounds)
chunks  = digest split into NCH pieces of RW bits, least significant first   (default RW=32, NCH=2)
Lemire  : p = x * M ; accept if (p mod 2^RW) >= (2^RW mod M) ; channel = p >> RW
reject all NCH chunks -> retry += 1 and re-hash (probability 4.4e-18 per hop for M=13)
```

* Primitive: SipHash-2-4 (Aumasson/Bernstein), 128-bit key, short-input PRF. Chosen because one round is only add/rotate/xor on 4x64 bits, and the algorithm has published test vectors (the Python model reproduces the paper's 15-byte vector `0xa129ca6149be45e5` and the reference `vectors.h` entries for lengths 0 and 8).
* The slot counter (56 bit) lives inside the engine and auto-increments on every delivered hop; load it with `slot_we` (time sync). The 128-bit key register is also inside the engine (`key_we`) and is counted in the area.
* Interface: `key_in/key_we`, `slot_in/slot_we` (only while idle), `req` pulse, `valid` 1-clock pulse with `chan` (registered). `M` (default 13), `RW`, `NCH` are parameters; `M >= 2`, `NCH <= 4`, `NCH*RW <= 64`.
* Cycles per hop: **12 clocks from `req` to `valid`** (1 idle->load, 1 load, 8 SipRounds, 1 digest xor, 1 reduction), measured in simulation. Each extra chunk tried adds 1 clock (RW=8,NCH=4 test config: 12-14), each full retry adds 11 clocks. At a 1 MHz engine clock a hop is 12 us; the ESP-NOW demo hop rates (hundreds of Hz) need only a few kHz.
* `RIPPLE=1` parameter swaps in explicit ripple-carry adders (simulation-equivalent, tested). It gave no area benefit in the Yosys/ABC flow and is far slower (see table), so the default is `RIPPLE=0`.
* Seed 0 on the LFSR is mapped to 1 (lock-up state); reset state is `0xACE1`, matching `sim/schedule.py`.

## Verification actually run (all in the cloud container; the laptop VM has no RTL tools)

| check | result |
|---|---|
| Python SipHash vs published vectors; exhaustive Lemire uniformity for small widths | pass (`results/model_selftest.txt`) |
| RTL vs Python, default config (M=13, RW=32, NCH=2): 3 keys x 20,000 consecutive slots = **60,000 hops**, third run crosses the 2^56 slot-counter wrap, random idle gaps | 0 channel errors, 0 retry-count errors; SipHash digest compared for the first 1,000 slots of each key: 3,000 checked, 0 errors |
| Same, forcing retries: M=13, RW=8, NCH=1, 20,000 hops (692 hops took a retry) | 0 errors, 1,000 digests ok |
| Same, forcing the chunk-shift path: RW=8, NCH=4, 20,000 hops (also repeated with `RIPPLE=1`, 2,000 hops; that RIPPLE run has no retries, so the ripple adder is validated only on the no-retry path) | 0 errors |
| Other M: M=37 and M=16 (power of two), 3,000 hops each | 0 errors |
| LFSR RTL vs Python: 4 seeds (incl. 0 and 0xFFFF) x 20,000 = 80,000 hops | 0 errors; 1 clock per hop |
| Verilator 5.020 (`--binary --timing`) re-run of the default, retry, chunk and LFSR benches | same results, all PASS |
| Mutation check on the testbench (hand-made RTL bugs: wrong rotation, wrong constant, missing xor, wrong threshold, wrong chunk shift, wrong retry increment; the mutant sources are not shipped and predate the `RIPPLE` parameter, so this row is not reproducible from this folder; an independent audit with 11 fresh mutants also found every one caught) | all caught (the threshold/chunk-shift bugs only by the RW=8 configs, which is why those configs exist) |
| Lint | `verilator --lint-only -Wall` and `iverilog -Wall` clean (`results/lint.txt`) |
| Formal (SymbiYosys, yosys 0.33, z3): FSM stays in legal states, step counters bounded, `valid -> chan < M`, `valid` follows the reduction state, slot counter advances by exactly 1 per hop and never otherwise; LFSR never reaches state 0 | **proved by k-induction** for the default config, for RW=8/NCH=1 and for the LFSR; a cover shows a normal hop is reachable (step 14). A deliberately broken multiplier constant is rejected by the same properties. These properties are safety/range checks, **not** a proof that the RTL equals SipHash (that evidence is the simulation above) |
| Unbiasedness of the reduction | exact integer count: for M=13, RW=32 every channel has exactly 330,382,099 accepted values; all (RW, M) combinations checked agree (`results/unbias_check.txt`) |

### Randomness checks on the RTL output (`results/randcheck.txt`, same tests as `sim/randtests.py`)

| stream | chi-square p | serial-corr p | runs p | entropy (max 3.700) | order-3 predictor accuracy (chance 0.0769) |
|---|---|---|---|---|---|
| keyed RTL, key 1 (20,000) | 0.567 | 0.701 | 0.555 | 3.70 | 0.0708 |
| keyed RTL, key 2 (20,000) | 0.150 | 0.407 | 0.669 | 3.70 | 0.0671 |
| keyed RTL, key 3 (20,000) | 0.627 | 0.227 | 0.255 | 3.70 | 0.0706 |
| keyed RTL, all 60,000 | 0.733 | 0.165 | 0.583 | 3.70 | 0.0759 |
| LFSR16 RTL (20,000) | 0.794 | **0.000** | 0.282 | 3.70 | **0.2356** |

The keyed stream looks uniform and unpredictable to these tests (no p-value below 0.05, predictor at or below chance). The LFSR passes uniformity but fails the serial-correlation test and is predicted 3x better than chance by a simple context predictor. These are statistical tests; passing them is necessary, not sufficient, for security.

## Synthesis (Yosys 0.33, `results/SUMMARY.txt`)

Flow: `synth -flatten` -> `dfflegalize/dfflibmap` -> `abc -liberty ... -D 10000` on **sky130_fd_sc_hd tt_025C_1v80** (liberty from the OpenROAD-flow-scripts sky130hd platform; cells with `dont_use` such as lpflow/probe/clkbuf/dlygate/x8/x16 excluded via a marked copy of the file). "GE" = area / 3.7536 um^2 (nand2_1).

| engine | generic cells (AND/OR/XOR/MUX gates + DFFs) | gate depth (yosys ltp) | sky130 cells | flops | area um^2 | GE | abc delay, no wire load / small wire load (from a separate buffered/upsized mapping, see the provenance note below) |
|---|---|---|---|---|---|---|---|
| LFSR16, M=16 (mod is wiring: LFSR core + seed load + output reg) | 58 | 6 | 79 | 21 | 797 | 212 | 0.68 / 0.79 ns |
| **LFSR16, M=13 (the reference engine)** | **218** | **67** | **245** | 21 | **1,828** | **487** | 8.15 / 10.36 ns |
| **Keyed SipHash-2-4 + Lemire, M=13** | **4,272** | **181** | **3,903** | 461 | **31,394** | **8,364** | 5.63 / 7.01 ns |
| Keyed, `RIPPLE=1` | 4,297 | 196 | 3,854 | 461 | 31,376 | 8,359 | 31.13 / 37.24 ns |

Reading the table honestly:

* The keyed engine is **about 17x the LFSR engine** (31,394 vs 1,828 um^2; 8,364 vs 487 GE) and 12 clocks per hop instead of 1.
* 461 of its flops are 9,229 um^2 (29%): 128 key + 56 slot counter + 256 SipHash state + 8 retry + control. The four 64-bit adders per round dominate the rest.
* In the LFSR engine the **`state mod 13` logic costs more than the LFSR itself** (1,828 vs 797 um^2); the LFSR core is only 16 flops, 3 xors and the seed/load muxing. A leaner mod-13 (e.g. folding with 2^12 = 1 mod 13) would shrink the LFSR figure; I did not do that, to keep the RTL identical in behaviour to `lfsr_hops`.
* Delay: the abc estimate for the keyed critical path is 5.6 ns (ideal wires) to 7.0 ns (small wire-load model), i.e. roughly 140-180 MHz *for the combinational round only*, before clk-to-q, setup, clock skew, placement and routing. Treat 100 MHz as the order of magnitude, not a promise. The first, unbuffered abc run reported 11.6 ns because it left a 324-fanout state-decode net unbuffered; that is a tool artifact and is not the number used (no log of that first run was kept, so the 11.6 ns figure cannot be re-checked from the shipped files). The LFSR delay (8-10 ns) is the mod-13 divider chain.
* Gate depth is the Yosys `ltp` level count on the generic gate netlist (181 levels for one SipRound plus select muxes); the level count differs from the ps estimate because the mapped netlist uses complex cells.
* Provenance: the area, cell and GE columns come from `abc -liberty -D 10000` (3,903 cells; 31,394 um^2 including 461 flops, so about 22,165 um^2 combinational). The delay column comes from a different mapping, `scripts/abc_time.script` (map, buffer, upsize, dnsize, `stime -p`; 3,963 gates, ABC combinational area 26,066 um^2 with no wire load and 27,544 um^2 with the small wire load, `results/synth/keyed_m13_timing_summary.txt`), which is about 18 to 24 % larger in combinational area than the area-column netlist. So area and delay are NOT from one netlist: a single mapping that reached 5.6 to 7.0 ns would cost roughly that much more area, and the area column alone says nothing about speed. Same Yosys version for both. Power and energy were **not** measured or estimated.

## Security per gate, linked to the existing LFSR break

Attacker model, as in `sim/attack.py`: knows the generator (Kerckhoffs), sees which channel is used each slot, does not know the key/seed.

| | LFSR16 | keyed SipHash-2-4 |
|---|---|---|
| secret size | 16-bit state (65,535 candidates) | 128-bit key |
| observed hops until the secret is pinned down (measured with the repo's `LfsrBreaker` logic, exhaustive over all 65,535 seeds, M=13) | **8 hops for 62.5 % of seeds, 9 for 37.5 %** (mean 8.375, exhaustive over all 65,535 seeds; an earlier 300-seed sample (`results/randcheck.txt`) gave mean 8.4; RTL stream with seed 0xACE1: 8). Repo notes that say "about 9 hops" are this figure rounded up | information-theoretic minimum about 128 / log2(13) = 35 hops before the key is unique, but finding it is a 2^128 search by the generic bound (no better published attack on full SipHash-2-4 is known to me; I did not search the literature further) |
| same attacker on the keyed RTL stream | n/a | candidate set empties after 2 hops (the LFSR model does not fit). This holds for any non-LFSR stream, so it is a sanity check on the attacker, not evidence about the keyed engine |
| area (sky130 estimate) | 487 GE | 8,364 GE |
| brute-force work bits per kGE | 16 / 0.487 = 32.9 | 128 / 8.364 = 15.3 (marginal: +112 bits for +7.9 kGE = 14.2 bits/kGE) |

The naive "bits per gate" ratio actually favours the LFSR, so it is the wrong figure of merit on its own. What matters is what survives an observer: after 8 to 9 hops (a few milliseconds of sniffing at 1 kHz hop rate) the LFSR's 16 bits are worth zero, so its *effective* security per gate is zero from then on; the keyed engine's cost of roughly 17x the area buys a secret that, assuming SipHash-2-4 behaves as a PRF with a 128-bit key (not proved, see Honest limits), stays computationally hidden however many hops are observed. Whether a 17x larger hop generator matters on an ESP32 link is a separate question: on the ESP32 the same PRF would simply be software (this Python model is the spec for a C port), and the RTL is for the FPGA/ASIC (Layer 3) demonstration.

## Honest limits

* **Simulation and synthesis estimates only.** No FPGA place-and-route, no sky130 place-and-route, no silicon, no power, no timing sign-off. The 12-clock latency and the area ratio are solid within the tool flow; the nanosecond figures are not.
* Area is dominated by the straightforward iterative design; a 16- or 32-bit serialized datapath would be smaller and slower. I did not build or measure one.
* SipHash-2-4 is a short-input PRF/MAC designed for hash-table protection, with a 64-bit output; it is not a NIST/IETF-standardized cipher. The "2^128" figure is the generic key-search bound, not a security proof. No side-channel, fault-injection or reset/power-glitch analysis was done. The retry path makes latency data-dependent with probability 4.4e-18 per hop (M=13).
* The engine only generates the schedule. Key distribution/pairing, time synchronisation of the slot counter, and re-keying are out of scope (the ExpressLRS advisory in `docs/LANDSCAPE.md` is a reminder that these are where real links get broken). The attacker is assumed to see channel indices only.
* Formal properties are range/protocol/FSM safety checks, run with a protocol assumption (key and slot loaded and `req` issued only while idle). They do not prove functional equivalence with SipHash.
* The RTL testbenches reach the 60,000+ hop level but are directed vectors from one model; the model and RTL were written together, so shared misreadings of the SipHash spec are possible. The independent anchors are the published SipHash vectors (model only) and the digest-level comparison of the RTL against the model.
* The `dont_use` liberty copy, the SymbiYosys sources and the sky130 liberty were fetched from public GitHub raw URLs at build time and are not included here (the liberty is 12.8 MB). `scripts/synth.sh` and `formal/sby` expect them at `../lib/` and `/home/claude/work/sby/` (cloud paths); adjust `LIB`/`SBY` to reproduce.
* Approach is a replication of a known pattern (a keyed hop engine in RTL, compare cirradio in `docs/LANDSCAPE.md`), not a novel result.

## Reproduce

Needs iverilog 12, Verilator 5, Yosys 0.33, z3, python3 + numpy; the laptop VM has only Python/numpy/gcc, so only `model/*.py` run there (vectors and the Python stream checks), not the RTL.

```
python3 model/hop_model.py        # selftest vs published SipHash vectors
python3 model/gen_vectors.py      # regenerate vectors/
scripts/run_all.sh                # lint, sims, verilator, randomness, synthesis, formal (about 6 minutes; writes results/)
```
