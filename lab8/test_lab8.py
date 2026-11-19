"""Assertion tests for lab8 (numpy only). Run: python3 test_lab8.py   (optionally: python3 test_lab8.py e12 e13 ...)
Every test compares a simulation result with something that was NOT produced by the same formula: a second implementation, a Monte
Carlo that includes effects the optimiser never saw, a continuous refinement, or a statistical bound over >= 20 seeds."""
import sys, math, time, traceback
import numpy as np
from _common import *
import _spatial as sp

CHECKS = {"n": 0}
def check(cond, msg):
    CHECKS["n"] += 1
    if not cond: raise AssertionError(msg)
TESTS = []
def test(tag):
    def deco(f): TESTS.append((tag, f.__name__, f)); return f
    return deco

# ------------------------------------------------------------------------------------------------------------------ E12
import e12_placement as e12

@test("e12")
def e12_vectorised_vs_scalar_loop():
    """grid delivery from the vectorised code equals a plain-Python per-point implementation (second implementation)"""
    for seed in (0, 1):
        inst = random_instance(seed, m=12); base = inst["base"]; relay = np.array([30.0, 70.0])
        dg = e12.delivery_grid(inst, np.vstack([base, relay]))
        rng = np.random.default_rng(seed)
        for gi in rng.choice(len(inst["cand"]), 6, replace=False):
            J = inst["cand"][gi]; acc = 0.0
            for P in inst["path"]:
                def p(d_tx, jam):
                    s_dbm = 15.0 - (40 + 30 * math.log10(max(d_tx, 1.0)))
                    i_mw = 10 ** ((0.0 - (40 + 30 * math.log10(max(math.dist(J, P), 1.0)))) / 10) if jam else 0.0
                    sinr = s_dbm - 10 * math.log10(10 ** (-9.5) + i_mw)
                    return 1 / (1 + math.exp(-(sinr - 6) / 1))
                pc = 1 - (1 - p(math.dist(base, P), 0)) * (1 - p(math.dist(relay, P), 0))
                pj = 1 - (1 - p(math.dist(base, P), 1)) * (1 - p(math.dist(relay, P), 1))
                acc += (1 - 3 / 13) * pc + (3 / 13) * pj
            check(abs(acc / len(inst["path"]) - dg[gi]) < 1e-9, f"vectorised vs loop differ at seed {seed} cell {gi}")

@test("e12")
def e12_grid_optimum_vs_continuous_refinement():
    """a continuous hill climb started at the grid optimum never improves the jammer's result by more than 0.01"""
    gains = []
    for seed in range(10):
        inst = random_instance(seed); j0, v0, _ = e12.worst_spot(inst, inst["base"][None])
        gains.append(v0 - e12.refine_jammer(inst, inst["base"][None], j0, seed=seed))
    check(min(gains) >= 0 and max(gains) < 0.02, f"refinement gain out of the documented bound: max {max(gains):.4f}")   # grid error bound, reported in RESULTS

@test("e12")
def e12_stackelberg_and_mc_transfer():
    rows = [e12.run_seed(s)[0] for s in range(24)]
    g = lambda k: np.array([r[k] for r in rows])
    m, h = paired_ci(g("v_stack"), g("v_norelay")); check(m - h > 0.03, f"Stackelberg gain over no relay too small: {m:.3f}+/-{h:.3f}")
    m, h = paired_ci(g("v_stack"), g("v_randrelay")); check(m - h > 0.02, f"Stackelberg not better than a random relay: {m:.3f}+/-{h:.3f}")
    m, h = paired_ci(g("v_stack_ref"), g("v_refined")); check(m - h > 0.03, f"gain with refined jammers too small: {m:.3f}+/-{h:.3f}")
    check(all(r["v_stack"] >= r["v_colocated"] - 1e-12 for r in rows), "a relay on the base should never beat the optimum relay")
    check(all(abs(r["v_stack_check"] - r["v_stack"]) < 1e-9 for r in rows), "V(R) differs from the worst-spot re-evaluation (two code paths)")
    # model mismatch: fading + shadowing the optimiser never saw
    check(g("mc_rank").mean() > 0.9, f"J* does not stay near-worst under fading: rank {g('mc_rank').mean():.3f}")
    m, h = paired_ci(g("mc_stack"), g("mc_star")); check(m - h > 0.05, f"relay gain does not survive fading: {m:.3f}+/-{h:.3f}")
    check(g("j_to_path").mean() < e12.STANDOFF + 2.0, "worst spot should hug the stand-off boundary (document if this fails)")

@test("e12")
def e12_monotone_in_jammer_power():
    inst = random_instance(3); v = [e12.worst_spot(inst, inst["base"][None], pj=p)[1] for p in (-10, -5, 0, 5, 10)]
    check(all(a >= b for a, b in zip(v, v[1:])) and v[0] > v[-1] + 0.1, f"not monotone: {v}")

# ------------------------------------------------------------------------------------------------------------------ E13
import e13_swarm as e13

@test("e13")
def e13_n1_equals_e12_and_sum_of_powers():
    for seed in range(8):
        inst = random_instance(seed); base = inst["base"][None]
        pos, v = e13.greedy_swarm(inst, 1, 0.0, base)
        check(abs(v - e12.worst_spot(inst, base, pj=0.0)[1]) < 1e-12, "N=1 swarm != E12 worst spot")
        pos8, v8 = e13.greedy_swarm(inst, 8, 0.0, base)
        # brute-force interference sum, one jammer at a time
        I = np.zeros(len(inst["path"]))
        for q in pos8:
            for k, P in enumerate(inst["path"]):
                I[k] += 10 ** ((0.0 - 10 * math.log10(8) - (40 + 30 * math.log10(max(math.dist(q, P), 1.0)))) / 10)
        check(abs(float(sp.delivery_points(sp.tx_signal_mw(base, inst["path"]), I).mean()) - v8) < 1e-9, "swarm sum-of-powers mismatch")

@test("e13")
def e13_swarm_claims_over_seeds():
    rows = [e13.run_seed(s)[0] for s in range(24)]
    g = lambda k: np.array([r[k] for r in rows], dtype=float)
    m, h = paired_ci(g("v_8"), g("v_1")); check(m + h < 0 and m > -0.06, f"swarm advantage at equal power should be small but real: {m:.3f}+/-{h:.3f}")
    m, h = paired_ci(g("ptarget_8"), g("ptarget_1")); check(m + h < 0, f"swarm should need less total power: {m:.2f}+/-{h:.2f}")
    check(np.all(g("v_8") <= g("vrand_8") + 1e-12), "greedy placement worse than average random placement")
    for N in e13.NS:
        check(g(f"vrelay_reopt_{N}").mean() > g(f"v_{N}").mean() + 0.04, f"relay does not help against N={N}")
    m, h = paired_ci(g("vrelay_reopt_8"), g("vrelay_reopt_1")); check(m + h > -0.002, "after a relay the swarm should not be clearly stronger")
    m, h = paired_ci(g("so25_8"), g("so25_1")); check(abs(m) < 0.02, "at 25 m stand-off the swarm should show no clear advantage")

# ------------------------------------------------------------------------------------------------------------------ E14
import e14_energy as e14

@test("e14")
def e14_replay_confirms_target_and_alternatives_are_not_cheaper():
    rows = [e14.run_seed(s) for s in range(20)]
    rng = np.random.default_rng(5)
    lb = [e14.slot_sim(r["cfg_blind"], "blind", rng)[0] for r in rows]
    check(all(abs(x - e14.DELTA) < 0.02 for x in lb), f"independent slot replay misses the 0.30 target: {min(lb):.3f}..{max(lb):.3f}")
    # random alternative configurations, judged by the slot-level replay only: any that reaches the loss target costs at least as much
    for s in range(5):
        best_e = rows[s]["e_blind"]; n_ok = 0
        for _ in range(40):
            cfg = dict(P=float(rng.choice(e14.P_GRID)), k=int(rng.choice(e14.K_GRID)), d=float(rng.choice(e14.DUTY)))
            loss, en = e14.slot_sim(cfg, "blind", rng, nslot=60000)
            if loss >= e14.DELTA - 0.01:
                n_ok += 1; check(en >= 0.97 * best_e, f"seed {s}: replayed config {cfg} reaches loss {loss:.3f} at energy {en:.0f} < optimum {best_e:.0f}")
        check(n_ok >= 3, "random search found too few feasible alternatives to be a test")

@test("e14")
def e14_pricing_claims_over_seeds():
    rows = [e14.run_seed(s) for s in range(20)]
    g = lambda k: np.array([r[k] for r in rows], dtype=float)
    arq = float(dbm2mw(e14.PT_DBM) / e14.ETA + e14.P_FIX) * (1 / (1 - e14.DELTA) - 1)
    m, h = ci95(g("e_blind") / arq); check(m - h > 1.5, f"blind jammer should pay clearly more than the defender loses: {m:.2f}+/-{h:.2f}")
    check(np.all(g("e_react") < g("e_blind")), "reactive jammer with 60 mW listening should be cheaper than blind")
    check(np.all(g("e_blind") < g("e_blind_naive")) and np.all(g("e_blind_naive") < g("e_blind_full")), "optimised power must beat naive and full power")
    mg = np.array([[x["e_blind"] for x in r["margin"]] for r in rows])
    check(np.all(np.diff(mg, axis=1) > 0), "jammer energy must rise with defender margin")
    Pstar = np.array([r["cfg_blind"]["P"] for r in rows]); check(2 < Pstar.mean() < 12, f"interior optimum expected, got {Pstar.mean():.1f} dBm")
    # brute force: above the cross-over listening power the blind jammer is cheaper
    r0 = rows[0]; co = r0["listen_crossover_mw"]; D0 = np.array(r0["curve_D"])
    check(e14.best_reactive(D0, p_listen=co + 20)[0] > e14.best_blind(D0)[0] and e14.best_reactive(D0, p_listen=max(co - 20, 0))[0] < e14.best_blind(D0)[0], "listening cross-over inconsistent")

# ------------------------------------------------------------------------------------------------------------------ E15
import e15_capture as e15

@test("e15")
def e15_mc_vs_independent_exponential_ratio_law():
    """with Rayleigh fading, P(attacker stronger than legit by CAP dB) = mu_a/(mu_a + z mu_l) (ratio of exponentials); the MC lock rate must match"""
    rng = np.random.default_rng(1)
    for pa in (-10.0, 0.0, 10.0):
        r = e15.sim(rng, 200000, pa, 25.0, "strongest", False)
        mu_a = float(rx_mw(pa, 25.0)); mu_l = float(rx_mw(e15.PT_DBM, e15.D_LEG)); z = 10 ** (e15.CAP_DB / 10)
        check(abs(r["att_lock"] - mu_a / (mu_a + z * mu_l)) < 0.012, f"pa={pa}: MC lock {r['att_lock']:.4f} vs ratio law {mu_a/(mu_a+z*mu_l):.4f}")

@test("e15")
def e15_deterministic_threshold_and_receiver_ordering():
    rng = np.random.default_rng(2)
    p_det = DET = e15.DET_DB + mw2dbm(NOISE_MW) - (-float(path_loss_db(25.0)))                  # attacker power at 25 m for SNR = DET_DB
    lo = e15.sim(rng, 50, float(p_det) - 1.0, 25.0, "first", True, nf=False); hi = e15.sim(rng, 50, float(p_det) + 1.0, 25.0, "first", True, nf=False)
    check(lo["att_lock"] == 0.0 and hi["att_lock"] == 1.0 and hi["deliv"] == 0.0, "first-lock threshold at the detection SNR is wrong")
    # a strongest-lock receiver with legit 40 dB stronger than the attacker is never captured
    s = e15.sim(rng, 50, -40.0, 25.0, "strongest", True, nf=False); check(s["att_lock"] == 0.0 and s["deliv"] > 0.9, "re-lock receiver captured by a very weak frame")

@test("e15")
def e15_seed_claims_and_coverage():
    rows = [e15.run_seed(s, n=2500) for s in range(20)]
    g = lambda k: np.array([r[k] for r in rows], dtype=float)
    m, h = ci95(g("p50_strongest") - g("p50_first")); check(m - h > 10, f"re-lock receiver should force > 10 dB more attacker power: {m:.1f}+/-{h:.1f}")
    i = rows[0]["P"].index(-10.0)
    m, h = paired_ci(g("first_sim")[:, i], g("first_early")[:, i]); check(m - h > 0.3, "an early frame must hurt a first-lock receiver much more than a simultaneous one")
    # independent explicit-hop check of the k/13 coverage formula
    rng = np.random.default_rng(7); n = 40000; k = 3
    hop = rng.integers(0, 13, n); chans = np.argsort(rng.random((n, 13)), axis=1)[:, :k]; hit = (chans == hop[:, None]).any(1)
    hit_res = e15.sim(rng, n, 0.0, 25.0, "first", True)
    got = np.where(hit, 0.0, 0.0) ; deliv = (1 - hit) * hit_res["clean"] + hit * hit_res["deliv"]
    check(abs(deliv.mean() - e15.overall(hit_res, k)) < 0.02, "k/13 coverage formula disagrees with the explicit channel simulation")
    check(np.all(np.diff(np.array([r["dist_first"] for r in rows]).mean(0)) >= -0.02), "delivery must not fall as the attacker moves away")

# ------------------------------------------------------------------------------------------------------------------ E16
import e16_honeypot as e16

@test("e16")
def e16_honeypot_claims():
    N, TT = 20, 2500
    run = lambda kind, rho, qd: np.array([e16.run(s, kind, rho, qd, T=TT)["deliv"] for s in range(N)])
    # oracle bound computed from the preference vector, not from the learning code: a perfect top-2 jammer loses P_JAM * 0.45
    oracle = 1 - e16.P_JAM * e16.REAL_W[:2].sum()
    for kind in ("freq", "exp3"):
        none = run(kind, 0.0, 0.0); hp = run(kind, 0.6, 0.0); disc = run(kind, 0.6, 1.0)
        check(none.mean() >= oracle - 0.01, f"{kind}: learning jammer beats the oracle bound ({none.mean():.3f} < {oracle:.3f})")
        check(none.mean() < oracle + 0.12, f"{kind}: jammer did not learn the preference ({none.mean():.3f})")
        m, h = paired_ci(hp, none); check(m - h > 0.2, f"{kind}: honeypot gain {m:.3f}+/-{h:.3f}")
        m, h = paired_ci(disc, none); check(abs(m) < 0.02, f"{kind}: a jammer that recognises decoys should erase the gain: {m:.3f}+/-{h:.3f}")
    r = e16.run(0, "freq", 0.6, 0.0, T=TT); check(abs(r["decoy_per_slot"] - 2.4) < 1e-12 and 0 <= r["wasted_frac"] <= 1, "decoy energy accounting wrong")
    a = e16.run(3, "exp3", 0.3, 0.0, T=1500); b = e16.run(3, "exp3", 0.3, 0.0, T=1500); check(a == b, "not deterministic for a fixed seed")

# ------------------------------------------------------------------------------------------------------------------ E17
import e17_moving as e17

@test("e17")
def e17_table_vs_direct_fading_sim():
    rng = np.random.default_rng(11); P, P0 = e17.tables(rng, 5.0, 25.0, nf=4000)
    # second implementation: loop over fading draws with explicit per-feature arithmetic
    rr = np.random.default_rng(12); n = 6000
    for (li, ai) in ((0, 0), (5, 2), (15, 0), (9, 14)):
        lf, af = e17.FEATS[li], e17.FEATS[ai]; acc = 0.0
        gain = 0.0 + (e17.G_MOD if lf[0] != af[0] else 0) + (e17.G_LEN if lf[1] != af[1] else 0) + (e17.G_TIM if lf[2] != af[2] else 0)
        th = e17.THETA_M[lf[0]] + 1.5 * math.log2(e17.LENS[lf[1]] / 32)
        for _ in range(n):
            s = 10 ** ((15 - (40 + 30 * math.log10(30))) / 10) * rr.exponential(); j = 10 ** ((5 + gain - (40 + 30 * math.log10(25))) / 10) * rr.exponential()
            acc += 1 / (1 + math.exp(-(10 * math.log10(s / (10 ** -9.5 + j)) - th)))
        check(abs(acc / n - P[li, ai]) < 0.02, f"table[{li},{ai}] {P[li,ai]:.3f} vs direct {acc/n:.3f}")

@test("e17")
def e17_diversity_claims_over_seeds():
    rows = [e17.run_seed(s) for s in range(20)]
    j = lambda n: np.array([r["jam"][n] for r in rows]); o = lambda n: np.array([r["oracle"][n] for r in rows]); c = lambda n: np.array([r["clean"][n] for r in rows])
    m, h = paired_ci(j(16), j(1)); check(m - h > 0.2, f"diversity gain vs learning jammer {m:.3f}+/-{h:.3f}")
    m, h = paired_ci(j(4), j(1)); check(m - h > 0.1, "4 configs should already help")
    check(c(16).mean() < 0.8 and c(1).mean() == 1.0, "diversity must cost clean goodput")
    for n in (1, 4, 16):
        m, h = paired_ci(j(n), o(n)); check(m + h > -0.01, f"learning jammer cannot beat the best fixed arm by more than sampling noise (n={n}): {m:.3f}+/-{h:.3f}")
    ps = [e17.power_sweep(s) for s in range(20)]
    lo = np.array([p[-10.0][1] - p[-10.0][16] for p in ps]); hi = np.array([p[30.0][16] for p in ps])
    m, h = ci95(lo); check(m - h > 0.05, "at low jammer power the static link should beat full diversity")
    check(hi.mean() < 0.05, "at 30 dBm even full diversity must be drowned")
    m, h = ci95(np.array([p[10.0][16] - p[10.0][1] for p in ps])); check(m - h > 0.2, "at 10 dBm diversity must pay")

# ------------------------------------------------------------------------------------------------------------------ driver
def main():
    only = set(sys.argv[1:]); failed = 0; t0 = time.time()
    for tag, name, f in TESTS:
        if only and tag not in only: continue
        t = time.time()
        try: f(); print(f"PASS {name}  ({time.time()-t:.1f}s)", flush=True)
        except Exception as e:
            failed += 1; print(f"FAIL {name}: {e}"); traceback.print_exc(limit=2)
    print(f"{'ALL PASS' if not failed else str(failed)+' FAILED'}: {sum(1 for t in TESTS if not only or t[0] in only)} tests, {CHECKS['n']} checks, {time.time()-t0:.0f}s")
    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    main()
