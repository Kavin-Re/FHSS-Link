# lab5 results (all simulated; defensive/educational; no hardware)

Every number below is printed by the script named in its row and stored in `outputs/<exp>.txt` / `.json`; figures are in `figures/`. Tests: `python3 test_lab5.py` (56 checks, about 15 s). Regenerate: `python3 run_all.py [exp1..exp7]` (per-experiment runtime on the cloud container: 43, 38, 47, 72, 15, 23, 23 s).
Existing modules were imported from `../sim` (adaptive, game, ladder, fhss_sim) and never edited. `ladder.PHASES` / `ladder.jam_set` are re-pointed at runtime in exp 6 only, inside a context manager that restores them (tested).
Excluded as instructed: Approximate-SAD.

## 1. Approximate correlator (`approx_correlator.py`, fig1) - modest, honest gain
Setup: DS-SS, Gp=32, 6-bit ADC, 12-bit sequential accumulator. Energy proxy = full-adder cell counts with assumed OR/AND = 0.2 FA (an assumption, not a measurement).
- Exact fixed-point BER at Eb/N0 = 4 dB: 0.0127 (AWGN theory 0.0125); at 8 dB: 0.00019.
- At 4 dB, BER / energy: LOA(1) 0.0236 / 0.95 (1.9x worse); LOA(1)+constant bias correction 0.0139 / 0.95 (1.09x); truncate 1 LSB before the code multiply 0.0142 / 0.917 (1.12x); truncate 2 LSB 0.0204 / 0.833; LOA(l>=4) collapses (BER 0.06 at l=4, 0.45 at l=5). Naive floor truncation after the multiply is biased: t=2 gives 0.158 vs 0.020 for the pre-multiply version.
- Under a strong tone (8 dB, JSR 15 dB) the exact adder has BER 0.169 and the usable approximate adders (LOA/LOAC l<=4, truncate <=4) lie between 0.171 and 0.229, so approximation changes little there and exact mode costs little in value terms when jammed. Not every config follows this: LOA(5) is lower (0.067, the bias-sign-flip artefact in the caveats) and the collapsed configs are higher (truncate 5 0.419, truncraw 3 0.391, LOA(6) 0.501, LOAC(6,7) 1.000).
- Quality-scalable receiver over the sim/ladder.py scenario (3 seeds): NORMAL -> truncate-1, ADAPT -> LOAC(1), CODED/SURVIVAL -> exact. Ladder with exact adders: PDR 0.9325, energy 1.000. Ladder with scalable adders: PDR 0.9325, energy 0.947 (-5.3%; -8.3% while in NORMAL). Without the ladder, "always cheap" 0.7917 vs "always exact" 0.7933 (the 0.79 -> 0.93 jump is the ladder, not the adders). Looser tolerance (NORMAL = truncate-2): energy 0.919 but clean-phase PDR falls 0.997 -> 0.981.
- Caveats: the sequential accumulator lets LOA bias pile up (an adder tree would behave differently; not tested); packet errors assume independent bit errors over 16 bits; the jam condition is a tone, not a general jammer; LOA(5) shows a non-monotone dip caused by bias sign flip, an artefact of this model.

## 2. Fast-hop jammer vs adaptation loop (`fast_hop.py`, fig2)
k=2 open-loop jammer relocating every H slots; defender feedback delayed D slots; 3 seeds x 4000 slots. Keyed schedule is flat at about 0.845 (formula 0.8454).
- Smallest H at which a policy beats the keyed schedule by >= 0.02 (grid 1,2,4,...,1000): Thompson 4 / 16 / 64 for D = 0 / 8 / 32 (about 2D + 4); UCB 2 / 32 / 64; AFH 128 for all D (EWMA alpha = 0.05 needs hundreds of slots).
- At H=1 all adaptive policies equal the keyed value (0.842-0.849). At H=1000: Thompson 0.986 / 0.983 / 0.980, UCB 0.973 / 0.967 / 0.943, AFH 0.954 / 0.953 / 0.950 (D = 0 / 8 / 32).
- No policy was >= 0.02 worse than keyed anywhere on this grid, so "break" here means "advantage disappears", not "harm". Larger penalties would need a jammer that exploits the defender's state (that is the follower / EXP3 case, exps 4 and 7). Coarse grid; one jammer family.

## 3. Relay (convolution-style) attack (`relay_attack.py`, fig3)
Provenance: docs/ does not describe arXiv 1903.11261 (grep finds nothing), so this is NOT a reproduction of that paper. It is a generic signal-contingent relay written from the brief: it hears the whole band, re-radiates energy opposite to the tone it hears (zero latency, perfect detection = worst case), so its power lands on the active channel without any knowledge of the hop key. Complex baseband, non-coherent energy detection, Rayleigh fading, per-antenna Eb/N0 fixed (diversity, no array gain). MC matches the Rayleigh theory (N=1: 0.0826 vs 0.0833; N=2: 0.0193 vs 0.0197).
- Keyed hop alone: relay budget +6 dB over signal energy, Eb/N0 20 dB, fixed-tone BFSK: BER 0.797 (bits mostly inverted). The key is irrelevant because the relay never needs the hop pattern. Unattacked BER at 20 dB: about 0.010.
- Keyed tone positions (S=8 candidate tones per channel, pair and bit mapping keyed per hop) cut a one-guess relay to 0.122 (about 1/(S-1) x P(relay beats signal); floor 0.115). Worst-case attacker is 'spread' (R/(S-1) on every other position): 0.36 for N=1, 0.22 for N=4 at +6 dB; at +2 dB 0.189 (N=1) vs 0.027 (N=4).
- Honest limit: once per-bin relay power R/(S-1) reaches the signal (R about +8.5 dB for S=8; S=16 buys about 3.5 dB) the defence collapses and 4-antenna combining becomes worse than 1 antenna (BER 0.955 at R=14 dB, 1.000 for R >= 22 dB). Energy combining only helps below that point.
- A blind wideband jammer spreading the same total power over 13x8 bins needs roughly 20 dB (=10log10(104), a power-ratio argument, not a measured curve) more power for the same damage (the measured points are +6 dB: 0.043 vs 0.797): the relay's advantage is that it concentrates power on the active channel.
- Wideband error floor (Eb/N0 40 dB, per-bin jam relative to signal, S=8): at -8 dB N=1/2/4/8 antennas give 0.118 / 0.040 / 0.0055 / 0.0001; at -2 dB 0.278 / 0.189 / 0.100 / 0.033; at +4 dB 0.418 / 0.375 / 0.324 / 0.254. Keyed tones do nothing against a wideband jammer; only diversity and power margin lower the floor, and it never reaches zero.
- Not modelled: relay latency vs symbol time, antenna geometry, array gain, coherent detection, a relay that learns tone mappings across hops (mapping is re-keyed per hop here).

## 4. Soft-set hopping vs delayed reactive jammer (`soft_set.py`, fig4)
M=13, jammer holds the channels used in the last B=3 slots seen d slots ago; PDR with p_jam 0.95 / p_clean 0.01; 3 seeds x 4000 slots.
- d=0 (instant reaction): every defender 0.047-0.05.
- d>=1, dwell 1: blind keyed 0.79 (closed form 0.789); hard set of 6: 0.595; Thompson 0.73-0.77; soft set with cool-down w = d+B: 0.990 for d = 1..9 (0.958 / 0.935 / 0.918 at d = 10..12, where w > 12 cannot be honoured); fixed w=6: 0.990 for d<=4 then a dip to 0.644 at d=7.
- Price: the eligible set shrinks to M-B-d channels (10 at d=0, 1 at d=9, i.e. deterministic). A rule-aware jammer (knows w, sees history up to t-d) holds soft-set to 0.67 (d=1..9) vs 0.769 for blind hopping, so the worst-case PDR over the two jammers is better for the plain keyed schedule (0.769) than for the soft set (0.67). The jammer here is a model I wrote, not a measured attacker.
- Dwell: with d=2, L>=3 hands the delay back: soft 0.678 / blind 0.607 at L=3, 0.285 / 0.267 at L=8.

## 5. Replay with rolling counter + MAC (`replay_mac.py`, fig5)
HMAC-SHA256 truncated to 32 bits, window W=64, 20% loss, 30% reorder, attacker acts 30% of slots (3 seeds).
- Accepted fractions (replay_old / counter bumped / random-tag forge / legit): crc_only 1.00 / 1.00 / 1.00 / 1.00; counter_only 0.01 / 0.43 / 0.46 / 0.94 (forged counters also block genuine packets); mac_only 1.00 / 0 / 0 / 1.00; mac+counter 0.02 / 0 / 0 / 1.00.
- mac+counter never accepted a replay of an already-accepted packet (all seeds, tested). The 0.02 are replays of packets the receiver never got (jammed): authentic, delayed delivery; accepted iff delay < W (tested for W = 8, 32, 64).
- Forgery by random tag: measured 6.2e-2 / 1.6e-2 / 4.0e-3 / 1.1e-3 / 2.5e-4 / 1.5e-5 for 4/6/8/10/12/16-bit tags vs 2^-bits (200k guesses).
- Window W=1 falsely rejects 15% of genuine packets at 30% reorder; W>=16 rejects none.
- Limit (tested): an immediate relay of a genuine packet is accepted first; counter + MAC are freshness, not distance bounding. 32-bit counter wrap, reboot persistence and key distribution not modelled.

## 6. Graceful degradation (`graceful.py`, fig6)
Stationary jammer on k of 13 channels, 3 seeds x 3000 slots, critical-message delivery. The CLIFF baseline (watchdog: loss > 30% over 50 attempts -> link down 300 slots) is a strawman I defined; real links may differ.
- Static k=0..12 critical delivery: LADDER 0.99 1.00 1.00 1.00 1.00 0.99 1.00 1.00 0.99 0.98 0.94 0.88 0.74; NORMAL 0.99 -> 0.13 linearly (below 0.5 from k=7); CLIFF 0.99 0.90 0.75 0.38 0.16 ... 0.03.
- Largest one-step drop: LADDER 0.14 (k=11->12), NORMAL 0.08, CLIFF 0.38 (k=2->3). Mean critical delivery over k: 0.97 / 0.55 / 0.27. Random-k jammer gives the same picture.
- Cost, stated plainly: the ladder protects critical traffic by dropping bulk. Bulk goodput (static): 0.89 at k=0, 0.58 at k=4, 0.04 at k=7, 0 from k=8 (NORMAL keeps 0.12-0.37 there). The ladder's bulk curve is itself cliff-like by design.

## 7. Regret-matching+ cross-check (`cfr_check.py`, fig7)
Normal-form CFR with one information set per player is regret matching, so RM+ (both players, 20000 iterations, averaged strategies) is used; no LP.
- k=1: defender guarantees 0.91716, jammer concedes at most 0.91825, bracketing 0.91769 (gap 1.1e-3); max |x_avg - 1/13| = 6e-4 (uniform). k=2 (78 jammer sets): [0.84418, 0.84623] around 0.84538.
- EXP3 (gamma 0.07) vs uniform hopping, 60000 slots: mean delivery 0.9187 vs value 0.9177 (+0.001, about one standard error at 60000 slots, so this is consistent with EXP3 matching the value; it does not show that EXP3 is or is not a best response); its own mixed strategy has entropy 3.38 of 3.70 bits.
- Reproduces sim/game.py: delivery EXP3 extracts (last 5000, 3 seeds) blind 0.9197, afh 0.9183, ucb 0.9237, thompson 0.9238, mixed 0.9219 versus the value 0.9177: ucb, thompson and mixed are above it by 0.004 to 0.006, while blind (+0.002) and afh (+0.0006) are within the sampling noise of about 0.002 on 15000 samples. The guarantee of each policy's empirical usage (what a best-responding jammer could get) is blind 0.9153, afh 0.9153, ucb 0.9116, thompson 0.9064, mixed 0.9099: below the value for all, with the learning policies furthest below. Blind's 0.9153 is sampling noise in a 20000-slot usage histogram, not a real weakness.
- Not done: a sequential (extensive-form) CFR with a reactive jammer; value checks only for k=1 and 2, equal channel quality.

## Caveats (apply to everything)
All results are simulations with the sim/ constants (p_jam 0.95, p_clean 0.01, M=13); nothing was measured on hardware or RF. Energy numbers are a gate-count proxy. Attackers are models I wrote for defensive study; the relay is not a reproduction of arXiv 1903.11261. 3 seeds per point, no confidence intervals, small-sample noise of about 0.005 PDR: differences below that are not findings. Figures: `figures/fig1..fig7_*.png`.
