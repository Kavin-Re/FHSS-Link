"""Tests for lab5 (simulation only). Run: python3 lab5/test_lab5.py   (prints PASS/FAIL per check; 'ALL PASSED' at the end; non-zero exit on any failure)."""
import sys, time
import numpy as np
import _common as cm
from _common import check
T0 = time.time(); ok = []
def chk(*a, **k): ok.append(check(*a, **k))

# ---------------------------------------------------------------- common
chk("game value M=13,k=1 is 0.9177 (4 dp) and k=2 is 0.8454", round(cm.game_value(13, 1), 4) == 0.9177 and round(cm.game_value(13, 2), 4) == 0.8454)

# ---------------------------------------------------------------- 1 approximate correlator
import approx_correlator as ac
rng = np.random.default_rng(0); a = rng.integers(-2000, 2000, 5000); b = rng.integers(-40, 40, 5000)
chk("exact adder equals integer addition (12-bit, no overflow in range)", np.array_equal(ac.add_exact(a, b), a + b))
for l in (1, 3, 5):
    err = ac.add_loa(a, b, l) - (a + b)
    chk(f"LOA(l={l}) per-add error bounded by 2^l", np.abs(err).max() <= (1 << l), f"max {np.abs(err).max()}")
chk("LOA low bits are OR of operands, upper part exact + carry-in", int(ac.add_loa(np.array([0b0110_0101]), np.array([0b0000_1011]), 4)[0]) == ((0b0110 + 0b0000 + (0 & 1)) << 4 | (0b0101 | 0b1011)))
chk("energy proxy: exact = 1, monotone in l and t", ac.energy(("exact",)) == 1.0 and ac.energy(("loa", 3)) < ac.energy(("loa", 2)) < 1.0 and ac.energy(("trunc", 2)) < ac.energy(("trunc", 1)) < 1.0)
b_ex = ac.correlate_ber(("exact",), 4.0, 100_000)
chk("exact fixed-point correlator BER at 4 dB within 15% of AWGN theory (quantisation allowed)", abs(b_ex / __import__("fhss_sim").ber_awgn_theory(4.0) - 1) < 0.15, f"{b_ex:.4f} vs {__import__('fhss_sim').ber_awgn_theory(4.0):.4f}")
chk("naive post-multiply floor truncation is much worse than pre-multiply truncation (t=2)", ac.correlate_ber(("truncraw", 2), 8.0, 60_000) > 10 * ac.correlate_ber(("trunc", 2), 8.0, 60_000))
chk("LOA bias correction helps (LOAC(1) BER < LOA(1) BER at 4 dB)", ac.correlate_ber(("loac", 1), 4.0, 100_000) < ac.correlate_ber(("loa", 1), 4.0, 100_000))
chk("jammed condition is hard for every adder (BER > 0.1)", ac.correlate_ber(("exact",), 8.0, 20_000, 15.0) > 0.1)
res = {c: dict(energy=ac.energy(c), **{k: ac.correlate_ber(c, e, 60_000, j) for k, (e, j) in ac.COND.items()}) for c in [("exact",), ("trunc", 1), ("loac", 1), ("loa", 1), ("trunc", 2)]}
modes = ac.pick_modes(res); per = {c: {k: ac.per_from_ber(res[c][k]) for k in ac.COND} for c in res}
r_le = ac.scalable_run("ladder_exact", modes, per, seed=1, T=6000); r_ls = ac.scalable_run("ladder_scalable", modes, per, seed=1, T=6000)
chk("quality-scalable receiver uses less energy than exact ladder", r_ls["energy"] < r_le["energy"], f"{r_ls['energy']:.3f} vs {r_le['energy']:.3f}")
chk("quality-scalable receiver keeps PDR within 0.02 of exact ladder", r_ls["pdr"] >= r_le["pdr"] - 0.02, f"{r_ls['pdr']:.3f} vs {r_le['pdr']:.3f}")
chk("scalable receiver is exact in CODED/SURVIVAL modes", modes["CODED"] == ("exact",) and modes["SURVIVAL"] == ("exact",))

# ---------------------------------------------------------------- 2 fast hop
import fast_hop as fh
kref = cm.game_value(13, 2)
chk("keyed schedule vs k=2 jammer ~ 0.8454", abs(np.mean([fh.simulate("keyed", 50, 0, seed=s, slots=4000) for s in (1, 2)]) - kref) < 0.02)
th = np.mean([fh.simulate("thompson", 1000, 0, seed=s, slots=4000) for s in (1, 2)])
chk("Thompson beats keyed by > 0.10 against a slow jammer (H=1000, D=0)", th > kref + 0.10, f"{th:.3f}")
th2 = np.mean([fh.simulate("thompson", 1, 8, seed=s, slots=4000) for s in (1, 2)])
chk("Thompson advantage vanishes against a per-slot jammer (H=1, D=8): within 0.03 of keyed", abs(th2 - kref) < 0.03, f"{th2:.3f}")
u = np.mean([fh.simulate("ucb", 1000, 0, seed=s, slots=4000) for s in (1, 2)]); u2 = np.mean([fh.simulate("ucb", 1000, 32, seed=s, slots=4000) for s in (1, 2)])
chk("feedback delay hurts UCB (D=32 worse than D=0 at H=1000)", u2 < u, f"{u2:.3f} < {u:.3f}")

# ---------------------------------------------------------------- 3 relay attack
import relay_attack as ra
for N in (1, 2):
    m = ra.ber(N=N, S=2, ebn0_db=10, nbits=200_000); t = ra.ber_theory(N, 10 ** (10 / 10))
    chk(f"energy-combining BFSK MC matches Rayleigh theory, N={N}", abs(m - t) < max(0.004, 0.08 * t), f"{m:.4f} vs {t:.4f}")
sw = ra.ber(N=1, S=2, ebn0_db=20, attack="relay", R_db=6, strat="swap", nbits=100_000)
chk("swap relay breaks fixed-tone BFSK despite keyed hop (BER > 0.5 at +6 dB budget, 20 dB Eb/N0)", sw > 0.5, f"{sw:.3f}")
rng = np.random.default_rng(1); S = 8
pairs = np.array([rng.permutation(S)[:2] for _ in range(60000)]); act = pairs[:, 0]; opp = pairs[:, 1]
guess = np.array([rng.choice([x for x in range(S) if x != a_]) for a_ in act[:20000]]); hitr = float(np.mean(guess == opp[:20000]))
chk("random guess of the opposite tone among S-1 positions hits with prob 1/(S-1)", abs(hitr - 1 / 7) < 0.01, f"{hitr:.3f}")
g1 = ra.ber(N=1, S=8, ebn0_db=20, attack="relay", R_db=6, strat="guess1", keyed_tones=True, nbits=100_000)
chk("keyed tone positions cut the guess-relay BER well below the swap relay and near (1/7)*P(beats) ~ 0.115", g1 < 0.2 and g1 < sw / 3, f"{g1:.3f}")
sp1 = ra.ber(N=1, S=8, ebn0_db=20, attack="relay", R_db=0, strat="spread", keyed_tones=True, nbits=100_000); sp4 = ra.ber(N=4, S=8, ebn0_db=20, attack="relay", R_db=0, strat="spread", keyed_tones=True, nbits=100_000)
chk("energy combining helps when per-bin relay power is below signal (R=0 dB, S=8: N=4 << N=1)", sp4 < sp1 / 5, f"{sp4:.4f} vs {sp1:.4f}")
big4 = ra.ber(N=4, S=8, ebn0_db=20, attack="relay", R_db=24, strat="spread", keyed_tones=True, nbits=50_000)
chk("honest limit: a strong enough relay (R=24 dB) defeats keyed tones + 4-antenna combining (BER > 0.9)", big4 > 0.9, f"{big4:.3f}")
f1 = ra.ber(N=1, S=8, ebn0_db=40, attack="wideband", J_db=-8, nbits=200_000); f4 = ra.ber(N=4, S=8, ebn0_db=40, attack="wideband", J_db=-8, nbits=200_000)
chk("wideband jamming leaves a non-zero error floor at infinite SNR (N=1 floor > 0.05), diversity lowers it (N=4 < N=1/10)", f1 > 0.05 and f4 < f1 / 10, f"N1 {f1:.4f} N4 {f4:.5f}")

# ---------------------------------------------------------------- 4 soft set
import soft_set as ss
tb = ss.theory_blind(3); mb = np.mean([ss.simulate("blind", 3, seed=s, slots=4000)["pdr"] for s in (1, 2, 3)])
chk("blind hopping vs reactive jammer matches closed form 1-(12/13)^3 mix (0.789)", abs(mb - tb) < 0.02, f"{mb:.3f} vs {tb:.3f}")
sm = np.mean([ss.simulate("soft", 3, seed=s, slots=4000)["pdr"] for s in (1, 2)])
chk("matched soft set vs reactive jammer ~ clean-channel delivery 0.99", sm > 0.97, f"{sm:.3f}")
d0 = max(np.mean([ss.simulate(p, 0, seed=s, slots=3000)["pdr"] for s in (1, 2)]) for p in ("blind", "soft", "hardset"))
chk("d=0 (instant reaction): every defender collapses to ~0.05", d0 < 0.10, f"{d0:.3f}")
ra_soft = np.mean([ss.simulate("soft", 3, jammer="rule-aware", seed=s, slots=4000)["pdr"] for s in (1, 2)]); ra_bl = np.mean([ss.simulate("blind", 3, jammer="rule-aware", seed=s, slots=4000)["pdr"] for s in (1, 2)])
chk("honest cost: rule-aware jammer makes soft set WORSE than blind hopping", ra_soft < ra_bl - 0.05, f"soft {ra_soft:.3f} blind {ra_bl:.3f}")
lg = np.mean([ss.simulate("soft", 2, L=6, seed=s, slots=3000)["pdr"] for s in (1, 2)])
chk("long dwell (L=6 > d=2) hands the delay back: soft-set PDR < 0.5", lg < 0.5, f"{lg:.3f}")

# ---------------------------------------------------------------- 5 replay + MAC
import replay_mac as rm
pay = b"abcdefgh"; rx = rm.Receiver("mac_counter", 64, 32); t0 = rm.tag_of(7, pay, 32)
chk("genuine fresh packet accepted", rx.accept(7, pay, t0))
chk("verbatim replay of a delivered packet rejected", not rx.accept(7, pay, t0))
chk("tampered payload rejected", not rm.Receiver("mac_counter", 64, 32).accept(8, b"abcdefgX", rm.tag_of(8, pay, 32)))
chk("counter bumped on old packet rejected (MAC covers the counter)", not rm.Receiver("mac_counter", 64, 32).accept(9, pay, rm.tag_of(7, pay, 32)))
chk("mac_only accepts verbatim replay (why a counter is needed)", (lambda r: (r.accept(7, pay, t0), r.accept(7, pay, t0))[1])(rm.Receiver("mac_only", 64, 32)))
chk("counter_only accepts a forged counter (why a MAC is needed)", rm.Receiver("counter_only", 64, 32).accept(1000, b"evil....", 0))
sc = rm.scenario("mac_counter", seed=2, n=3000)
chk("mac+counter: forge and counter-bump attacks accepted 0 times", sc["forge"] == 0 and sc["replay_inc"] == 0)
chk("mac+counter: legitimate packets all accepted at W=64 with loss/reorder", sc["legit_accept"] > 0.999, f"{sc['legit_accept']:.4f}")
chk("mac+counter: accepted verbatim replays are only packets the receiver never got (delayed delivery), < 5% of replay_old", sc["replay_old"] < 0.05, f"{sc['replay_old']:.3f}")
chk("mac+counter: a replay of an already-accepted packet is NEVER accepted (all seeds)", all(rm.scenario("mac_counter", seed=s, n=2000)["dup_accepted"] == 0 for s in (1, 2, 3)))
chk("sanity: mac_only DOES accept duplicates in the same scenario", rm.scenario("mac_only", seed=1, n=2000)["dup_accepted"] > 50)
fr8 = rm.forgery_rate(8, 100_000)
chk("8-bit tag forgery success ~ 2^-8 (within 30%)", abs(fr8 / 2 ** -8 - 1) < 0.30, f"{fr8:.5f}")
chk("delayed replay of a jammed packet accepted iff delay < W", all(rm.delayed_jammed_replay(d, 32) == (d < 32) for d in (0, 5, 31, 32, 33, 80)))
rx = rm.Receiver("mac_counter", 64, 32); chk("limit: immediate relay of a genuine packet is accepted (no distance bounding)", rx.accept(5, pay, rm.tag_of(5, pay, 32)))
chk("window W=1 rejects reordered legit packets, W=16 does not (p_reorder=0.3)", rm.false_reject(1, 0.3, n=3000) > 0.05 and rm.false_reject(16, 0.3, n=3000) < 0.005)

# ---------------------------------------------------------------- 6 graceful degradation
import graceful as gd, ladder
ph0, js0 = ladder.PHASES, ladder.jam_set
lad = gd.ladder_point("LADDER", 6, "static", T=2000, seeds=(1, 2)); nor = gd.ladder_point("NORMAL", 6, "static", T=2000, seeds=(1, 2)); cl = np.mean([gd.cliff_run(6, "static", s, 2000) for s in (1, 2)], axis=0)
chk("ladder module state restored after the stationary-jammer context", ladder.PHASES is ph0 and ladder.jam_set is js0)
chk("k=6: ladder keeps critical delivery >= 0.9 while NORMAL < 0.7 and CLIFF < 0.2", lad[0] >= 0.9 and nor[0] < 0.7 and cl[0] < 0.2, f"{lad[0]:.2f} {nor[0]:.2f} {cl[0]:.2f}")
cr = [np.mean([gd.cliff_run(k, "static", s, 2000)[0] for s in (1, 2)]) for k in (2, 3)]
chk("cliff baseline drops by > 0.25 between k=2 and k=3", cr[0] - cr[1] > 0.25, f"{cr[0]:.2f} -> {cr[1]:.2f}")
chk("honest cost: ladder bulk goodput at k=9 is ~0 (critical traffic protected at bulk's expense)", gd.ladder_point("LADDER", 9, "static", T=2000, seeds=(1,))[1] < 0.05)

# ---------------------------------------------------------------- 7 regret matching
import cfr_check as cc
A = cc.payoff(13, 1); x, y, _ = cc.rm_plus(A, 8000); lo, up = cc.gap(A, x, y)
chk("RM+ brackets the exact value: lower <= 0.91769 <= upper", lo <= cm.game_value(13, 1) <= up, f"[{lo:.5f}, {up:.5f}]")
chk("RM+ value within 2e-3 of 0.9177 and average strategy ~ uniform", up - lo < 4e-3 and np.abs(x - 1 / 13).max() < 3e-3, f"gap {up-lo:.1e}")
A2 = cc.payoff(13, 2); x2, y2, _ = cc.rm_plus(A2, 6000); lo2, up2 = cc.gap(A2, x2, y2)
chk("RM+ brackets the k=2 value 0.8454", lo2 <= cm.game_value(13, 2) <= up2, f"[{lo2:.5f}, {up2:.5f}]")
chk("empirical_guarantee(uniform) equals game value; a concentrated strategy is far below", abs(cc.empirical_guarantee(np.ones(13) / 13) - cm.game_value()) < 1e-12 and cc.empirical_guarantee(np.r_[0.5, np.ones(12) * 0.5 / 12]) < 0.6)
pay, pavg = cc.exp3_vs_uniform(T=30000)
chk("EXP3 jammer vs uniform hopping extracts no more than the value (mean delivery >= 0.9177 - 0.005)", pay.mean() >= cm.game_value() - 0.005, f"{pay.mean():.4f}")
chk("EXP3's own mixed strategy is far from a pure strategy (entropy > 3 bits of 3.70)", -(pavg * np.log2(pavg)).sum() > 3.0)

print(f"\n{sum(ok)}/{len(ok)} checks passed in {time.time() - T0:.0f}s")
print("ALL PASSED" if all(ok) else "SOME FAILED"); sys.exit(0 if all(ok) else 1)
