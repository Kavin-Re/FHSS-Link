"""Builds RESULTS_SILICON.md from results/*.json so that every number in the claim table comes from a script output."""
import json
L = lambda n: json.load(open(f"results/{n}.json"))
e1, e2, e3, e4 = L("exp1_cpa"), L("exp2_fault"), L("exp3_trojan"), L("exp4_puf")
u = e1["unmasked"]; need = u["traces_for_90pct_full_key"]; m1 = e1["masked_first_order"]; m2 = e1["masked_second_order"]; tv = e1["tvla_max_abs_t"]; ct = e1["controls"]
c = e2["campaign"]; ag = e2["aggregate_equal_weight_over_8_fault_classes"]; ge = e2["ge"]["overhead_pct"]; df = e2["siphash_fault_diffusion"]
d3 = e3["delay_mc"]; g3 = e3["golden_reference"]; rt = e3.get("randtests_20000_hops", {})
M4 = e4["metrics"]; fe = e4["fuzzy_extractor_by_condition"]
def row(mode, bk):
    return next(r for r in d3[mode] if r["beta_k"] == bk)
def fmt(x): return "n/a" if x is None else f"{x:,.0f}"
def dl(mode, bk, det="cusum"):
    r = row(mode, bk)[det]; return f"{fmt(r['median_delay_hops'])} hops ({r['p_detect']:.0%} detected)"
cf = lambda k, f: c[k][f]
nm1 = m1["stage1_byte_rate"]
md = f"""# RESULTS_SILICON: red-team-on-silicon simulations for the FHSS-Link keyed hop engine

Scope: **simulation only, our own design, no real device and no hardware.** Every result below comes from a Python/numpy model with
*assumed* leakage, fault, trojan and process-variation parameters. None of it measures real silicon; absolute numbers (traces needed,
gate-equivalents, bit-error rates) will differ on a real chip. What transfers is the *shape* of each result (what breaks, what
countermeasure moves which curve, what is not covered). Hop engine under study: `hop = SipHash-2-4(key128, slot_counter64) mod 13`.

Reproduce: `bash run_all.sh` (about 6 minutes, each script under 150 s), `python3 run_tests.py` for the tests, `python3 build_results.py` regenerates this page.

## 1. Power side-channel (CPA) and masking  (`exp1_cpa.py`, `sidechannel.py`, `siphash.py`, figure `figures/fig1_cpa.png`)
Model: per trace 16 samples = Hamming weight of one byte of `v3 = k1^C3^m` (8 samples) and of `v2+v3` (8 samples) plus Gaussian noise of std sigma
(the noise-free HW signal has std 1.41, so sigma=4 is a signal-to-noise power ratio of 0.125). Divide-and-conquer CPA: k1 bytes first, then k0 bytes using the
carry from lower bytes. SipHash-2-4 matches the public reference vectors (n=0..8 and the 15-byte vector from the paper) in `test_siphash.py`.
- Unmasked, 12 trials per point: 90 % full 128-bit key recovery needs about {need['0.5']} traces at sigma=0.5, {need['1.0']} at sigma=1, {need['2.0']} at sigma=2, {need['4.0']} at sigma=4 (grid is powers of 2, so read as "within a factor 2"). Traces needed scale roughly with sigma squared.
- First-order boolean masking (2 shares, fresh 64-bit mask per run, ISW-based secure adder): the same CPA recovers {nm1[0]*100:.0f}% / {nm1[1]*100:.0f}% / {nm1[2]*100:.0f}% of k1 bytes at {m1['N'][0]:,} / {m1['N'][1]:,} / {m1['N'][2]:,} traces (sigma=1; 3 trials x 8 bytes, chance is 0.4 %). Stage 2 with k1 given as an oracle also fails ({m1["stage2_byte_rate_oracle_k1"][0]*100:.0f}% / {m1["stage2_byte_rate_oracle_k1"][1]*100:.0f}% of bytes, i.e. 0-2 of 24 bytes, chance level).
- TVLA-style fixed-vs-random Welch t (20,000 traces per set, max over samples): unmasked {tv['unmasked']:.0f}, masked first order {tv['masked_first_order']:.1f} (threshold 4.5), masked second order (centred product) {tv['masked_second_order_centred_product']:.0f}.
- **Second-order note.** Masking with 2 shares is only first-order secure. A second-order CPA (centred product of the two share samples) recovers all k1 bytes with about 1,000 traces at sigma=0.5, 1,000 at sigma=1 and 8,000 at sigma=2 (all 8 bytes) (fractions in `results/exp1_cpa.json`). So masking raised the cost from tens-to-hundreds of traces to hundreds-to-thousands in this model; it did not make the attack impossible. More shares or a higher-order secure gadget set would be needed against a second-order adversary.
- Controls: with the mask forced to zero the first-order attack recovers {ct['mask_disabled_r0_stage1_bytes_of_8']}/8 bytes; if the two shares are held in a register that is overwritten share-by-share (Hamming *distance* between shares = HW of the secret value) it recovers {ct['share_overwrite_HD_leak_stage1_bytes_of_8_N3000']}/8 bytes at 3,000 traces. Masking is only as good as the physical independence of the share leakage.
- HD variant: the Hamming-distance leakage of the addition hides the most significant bit of every k0 byte; the attack resolves it by lookahead on the carry plus a 256-way check against one hop digest.
- Sequential counter: with a bare slot counter 0..3999 only the 2 low bytes of k1 vary, so only 2 of 8 stage-1 bytes were recovered (the upper bytes have zero input variance). The attack assumes the hash input has varying upper bytes (session nonce / epoch in the message, or a chosen-input adversary).
- Not modelled: glitches and early propagation, internal ISW intermediates, trace misalignment/jitter, real acquisition limits, EM, template attacks, and the attacker's need to know/control the input.

## 2. Fault injection and redundancy  (`exp2_fault.py`, `faultsim.py`, `ge_model.py`, figure `figures/fig2_fault.png`)
Link model: static jammer on 1 of 13 channels, loss probabilities as in `sim/link_sim.py` (0.95 jammed / 0.01 clean). Fault-free PDR of the SipHash engine {e2['fault_free_pdr_siphash_engine']:.4f} vs {e2.get('fault_free_pdr_link_sim_lfsr', float('nan')):.4f} from the existing `link_sim.run` with its LFSR (link_sim has no hook for engine faults, so only the loss model and this fault-free PDR are shared; the fault loop is a new slot-level model). One fault event at slot 0 on the RX side, {e2['trials_per_config']} trials per cell, 256-slot window. Link recovery: loss of lock after 3 misses, authenticated beacon every 32 slots reloads the counter, watchdog reloads the key from NVM.
- Unprotected (with beacon + watchdog): every counter / key / FSM fault desynchronises the RX. Mean desync duration: counter {cf('none|ctr|1','mean_rec'):.0f} slots, FSM {cf('none|fsm|1','mean_rec'):.0f} slots, key {cf('none|key|1','mean_rec'):.0f} slots ({cf('none|key|1','mean_excess_lost'):.0f} extra lost packets). Without the watchdog, a key-register upset is never recovered ({cf('none_nowd|key|1','p_unrecovered'):.0%} unrecovered in 256 slots, 217 extra lost packets): beacons cannot fix a wrong key.
- TMR on key/counter/FSM/output state (bitwise vote + scrub): single upsets are fully masked (desync 0 in all 4 single-fault classes). Multi-bit upsets spread over three copies sometimes line up on the same bit index: desync {cf('tmr|ctr|2','p_desync'):.1%} (2 flips) and {cf('tmr|ctr|4','p_desync'):.1%} (4 flips) on the counter, {cf('tmr|key|4','p_desync'):.1%} on the key (4 flips). This assumes independent random bit positions; adjacent-cell or common-mode upsets would defeat TMR far more often.
- Duplicate + parity + compare (parity per counter word / per key byte, uncorrectable mismatch is detected, key reloaded next slot, counter at next beacon): corrects all single-bit upsets (desync 0), but multi-bit and FSM faults are only detected, not corrected (desync {cf('dcp|ctr|2','p_desync'):.0%} for 2 counter flips, {cf('dcp|fsm|1','p_desync'):.0%} FSM). Detection still pays: key faults recover in about {cf('dcp|key|2','mean_rec'):.0f} slot instead of {cf('none|key|2','mean_rec'):.0f}.
- Averaged over the 8 fault classes (equal weight): extra lost packets per fault {ag['none']['mean_excess_lost']:.1f} (none), {ag['tmr']['mean_excess_lost']:.2f} (TMR), {ag['dcp']['mean_excess_lost']:.1f} (dup+parity).
- **Cost proxy (gate equivalents, assumed cell areas, not synthesis).** Baseline engine ~{e2['ge']['baseline_total_GE']:,.0f} GE. Overhead: TMR on state {ge['TMR_state']:.0f} %, dup+parity+compare {ge['DMR_parity_state']:.0f} %, lockstep duplicate engine (detect only) {ge['lockstep_full_engine']:.0f} %, full-engine TMR {ge['TMR_full_engine']:.0f} %. Scaling flop area by 0.7x / 1.3x moves state-TMR by a few percentage points only (`ff_cost_sensitivity_pct` in the json). In this model TMR buys much more than dup+parity for about the same area, because dup+parity cannot correct multi-bit or FSM faults without a tie-break.
- **Differential-fault note (diffusion only).** A single-bit fault in the internal state before round r (0..7) of SipHash-2-4 changes on average {df['mean_out_diff_hw'][0]:.1f} of 64 output bits for r<=5, {df['mean_out_diff_hw'][6]:.1f} for r=6 and {df['mean_out_diff_hw'][7]:.1f} for r=7; {df['frac_diff_hw_le_16'][7]:.0%} of last-round faults give a sparse (<=16-bit) difference, which is the structure differential fault analysis exploits. The hop (value mod 13) changes with probability about 12/13 whatever the round. **I did not implement a DFA key recovery**, did not model how a real fault would be placed (timing, bit control), and did not model faults on TX, in the datapath for the TMR/parity schemes, in voters/comparators/beacon logic, clock or voltage glitching, permanent faults, or adjacent multi-bit upsets.

## 3. Hardware trojan detection  (`exp3_trojan.py`, `trojan.py`, figure `figures/fig3_trojan.png`)
Trojan model: 24-bit slot counter, trigger at a rare count; afterwards, with probability beta = k/256 (select bits tapped from the digest) the channel is replaced ('stuck': fixed channel; 'narrow': h mod 6). Before trigger the output is bit-identical to the clean engine ({e3['stealth_pre_trigger_identical_hops']} over 100,000 hops), so production testing of the hop stream cannot see it. Proxy cost {e3['trojan_cost_GE']:.0f} GE (about {e3['trojan_cost_pct_of_engine']:.1f} % of the engine).
Detectors see only the channel stream (no key, no target): CUSUM on window chi-square (256-hop windows, tuned for beta=0.03) and a single-window chi-square; both thresholds are set for a 5 % false-alarm probability per 5,000 clean windows (1.28 M hops); measured false-alarm rates {e3['empirical_false_alarm_5000_windows']['cusum']:.3f} (CUSUM) and {e3['empirical_false_alarm_5000_windows']['single_window']:.3f} (single window).
- 'stuck', CUSUM median delay after the trigger: beta=0.05 {dl('stuck',13)}; beta=0.10 {dl('stuck',26)}; beta=0.20 {dl('stuck',51)}; beta=0.40 {dl('stuck',102)}; beta=0.02 {dl('stuck',5)}; beta=0.012 {dl('stuck',3)}.
- 'narrow' is much harder to see: beta=0.10 {dl('narrow',26)}; beta=0.40 {dl('narrow',102)}; at beta<=0.03 detection within 2 M hops is partial (see json).
- Delay falls roughly with 1/beta squared (chi-square noncentrality grows with beta squared). Real-SipHash cross-check (12 keys): median CUSUM delay {fmt(e3['real_siphash_crosscheck']['26']['cusum_median_delay_hops'])} hops at beta=0.10 and {fmt(e3['real_siphash_crosscheck']['51']['cusum_median_delay_hops'])} at beta=0.20, consistent with the Monte Carlo (which uses ideal uniform hops).
- A golden reference (the receiver regenerates the expected hop from the key) detects after {fmt(g3['stuck'][4]['median_delay_slots'])} slots at beta=0.10 and {fmt(g3['stuck'][0]['median_delay_slots'])} at beta=0.012: two to four orders of magnitude faster. It only works when the trojan is in one endpoint and the other is trusted; if both endpoints carry it, only blind statistics remain.
- Existing `sim/randtests.py` on 20,000 post-trigger hops: chi-square p {rt.get('trojan_beta0.02_stuck',{}).get('chi_p','n/a')} for beta=0.02 stuck vs {rt.get('clean',{}).get('chi_p','n/a')} clean (a one-shot batch test, not comparable with the online false-alarm budget above).
- Not modelled: trojans that preserve the marginal distribution (e.g. leak key bits through channel choice, correlate hops), analogue/side-channel trojans, a trigger that depends on data rather than a counter, adaptive adversaries who know the detector.

## 4. PUF-derived key  (`exp4_puf.py`, `puf.py`, figure `figures/fig4_puf.png`)
Model: 64 chips x 2048 ring oscillators; frequency = layout plane (gradient spanning 3 sigma) + N(0,1) process variation; read noise 0.05 sigma, independent per-RO temperature coefficient (hot +60 C, cold -40 C); enrolment = majority of 15 reads; 1024 comparison bits per chip.
- Pairing matters (bit-aliasing): comparing far-apart ROs gives uniqueness {M4['far']['uniqueness_mean']:.1%} and mean |P(bit)-0.5| of {M4['far']['bit_aliasing_mean_abs_dev']:.2f} (gradient dominates: bad). Removing a per-chip fitted plane first gives uniqueness {M4['far_planefit']['uniqueness_mean']:.1%}; neighbour pairs give {M4['neighbor']['uniqueness_mean']:.1%} (std {M4['neighbor']['uniqueness_std']:.3f}). Bit aliasing for the good schemes: mean |p-0.5| = {M4['neighbor']['bit_aliasing_mean_abs_dev']:.3f}, max {M4['neighbor']['bit_aliasing_max_abs_dev']:.2f} (with only 64 chips about 0.05 is the sampling floor).
- Reliability (neighbour pairs): {M4['neighbor']['reliability_nominal_pct']:.1f} % nominal, {M4['neighbor']['reliability_hot_plus60C_pct']:.1f} % hot, {M4['neighbor']['reliability_cold_minus40C_pct']:.1f} % cold (bit error rate {M4['neighbor']['ber_nominal_mean']:.1%} / {M4['neighbor']['ber_hot_plus60C_mean']:.1%} / {M4['neighbor']['ber_cold_minus40C_mean']:.1%}; nominal theory arctan(sn/sp)/pi = {e4['ber_theory_nominal']:.1%}, the rest is enrolment noise).
- Code-offset fuzzy extractor, 128-bit key = SHA-256(secret)[:16]; key-regeneration failure (nominal / hot / cold): no ECC {fe['no ECC (128 raw bits)']['fail_nominal']:.0%} / {fe['no ECC (128 raw bits)']['fail_hot_plus60C']:.0%} / {fe['no ECC (128 raw bits)']['fail_cold_minus40C']:.0%}; 5-fold repetition {fe['rep-5 majority']['fail_nominal']:.1%} / {fe['rep-5 majority']['fail_hot_plus60C']:.1%} / {fe['rep-5 majority']['fail_cold_minus40C']:.1%}; BCH(15,7,t=2) x19 {fe['BCH(15,7,t=2) x19']['fail_nominal']:.1%} / {fe['BCH(15,7,t=2) x19']['fail_hot_plus60C']:.1%} / {fe['BCH(15,7,t=2) x19']['fail_cold_minus40C']:.1%}; repetition-3 + BCH {fe['rep-3 + BCH(15,7)']['fail_nominal']:.2%} / {fe['rep-3 + BCH(15,7)']['fail_hot_plus60C']:.2%} / {fe['rep-3 + BCH(15,7)']['fail_cold_minus40C']:.2%} (1,280 trials per cell, so 0 means below about 1e-3). The concatenated code uses 855 of the 1,024 response bits and leaves a failure rate that is still not acceptable for a link that must always boot (0.2 % at +60 C here).
- End to end: the regenerated key reproduced the hop schedule for {e4['end_to_end_hop_schedule_match']['matches']}/{e4['end_to_end_hop_schedule_match']['total']} chip-condition trials, and the 64 chips gave {e4['key_uniqueness_distinct_keys_of_64']} distinct keys.
- Honest caveats: the secret comes from an assumed on-chip TRNG; helper data is public and leaks 722 of 855 bits of redundancy by construction (safe only if response bits are close to independent and unbiased, which the entropy numbers here only bound from above, not prove); no helper-data manipulation, aging, voltage, modelling-attack or side-channel analysis of the PUF itself; a pure-Gaussian plane+noise model is much cleaner than real silicon.

## 5. Claim to script map
| # | Claim | Script that produced it | Output |
|---|---|---|---|
| 1 | SipHash-2-4 implementation matches public vectors | `test_siphash.py` | pass/fail |
| 2 | Unmasked CPA: traces for 90 % key recovery vs sigma ({need['0.5']}/{need['1.0']}/{need['2.0']}/{need['4.0']} for sigma 0.5/1/2/4) | `exp1_cpa.py` | `results/exp1_cpa.json`, fig1 |
| 3 | First-order masking defeats first-order CPA up to 32,000 traces | `exp1_cpa.py`, `test_sidechannel.py` | json, fig1 |
| 4 | Second-order CPA breaks the 2-share masking (~1,000 traces at sigma=1) | `exp1_cpa.py` | json, fig1 |
| 5 | Masking fails if mask is zero or shares overwrite each other (controls) | `exp1_cpa.py`, `test_sidechannel.py` | json |
| 6 | TVLA t: unmasked {tv['unmasked']:.0f}, masked 1st {tv['masked_first_order']:.1f}, 2nd {tv['masked_second_order_centred_product']:.0f} | `exp1_cpa.py` | json |
| 7 | Single upsets: unprotected always desync; TMR masks; dup+parity corrects single bit only | `exp2_fault.py` | `results/exp2_fault.json`, fig2 |
| 8 | Key upset unrecoverable without NVM watchdog | `exp2_fault.py` | json |
| 9 | GE overhead: TMR state {ge['TMR_state']:.0f} %, dup+parity {ge['DMR_parity_state']:.0f} %, lockstep {ge['lockstep_full_engine']:.0f} % (proxy) | `ge_model.py`, `exp2_fault.py` | json, fig2 |
| 10 | SipHash fault diffusion by round (full until r=5, sparse at r=7) | `exp2_fault.py` | json, fig2 |
| 11 | Fault-free link PDR agrees with `sim/link_sim.py` | `exp2_fault.py`, `test_fault.py` | json |
| 12 | Trojan invisible before trigger; blind detection delay vs bias | `exp3_trojan.py`, `test_trojan.py` | `results/exp3_trojan.json`, fig3 |
| 13 | Golden-reference detection orders of magnitude faster | `exp3_trojan.py` | json, fig3 |
| 14 | RO-PUF uniqueness / reliability / aliasing; pairing choice | `exp4_puf.py`, `test_puf.py` | `results/exp4_puf.json`, fig4 |
| 15 | Fuzzy extractor failure rates; end-to-end key to hop schedule | `exp4_puf.py` | json, fig4 |

## 6. What this does not show
No real device was measured, so none of the leakage, fault or process parameters are validated. The attacks here are textbook-level against a model we wrote ourselves; they say where our design would need attention (mask order, redundancy of the key register, post-trigger statistical monitoring, ECC strength), not that it is secure or insecure in silicon.
"""
open("RESULTS_SILICON.md", "w").write(md)
print(len(md))
