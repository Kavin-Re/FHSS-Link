"""Assertion tests for lab6. Run: python3 test_lab6.py   (about 25 s). Every assertion encodes a claim made in RESULTS_LAB6.md."""
import sys, random, numpy as np
import exp1_bandit_poison as e1, exp2_learning_rate as e2, exp3_control_plane as e3, exp4_time_push as e4
import exp5_prng_graveyard as e5, exp6_keyfromair_drain as e6, exp7_myopic_jammer as e7, exp8_scorecard as e8
OK = []
def t(name):
    def deco(f):
        try: f(); print("PASS", name); OK.append(True)
        except AssertionError as ex: print("FAIL", name, "->", ex); OK.append(False)
        return f
    return deco

@t("R1 poisoning hurts a no-forgetting Thompson learner right after the switch")
def _():
    c = np.mean([e1.run("ts", poison=False, seed=s)["p2_first300"] for s in range(6)]); p = np.mean([e1.run("ts", poison=True, seed=s)["p2_first300"] for s in range(6)])
    assert c - p > 0.2, (c, p)
@t("R1 discounting (gamma 0.98) removes most of the damage; uniform is unaffected")
def _():
    p = np.mean([e1.run("ts", poison=True, seed=s, gamma=0.98)["p2_first300"] for s in range(6)]); q = np.mean([e1.run("ts", poison=True, seed=s)["p2_first300"] for s in range(6)])
    u = np.mean([e1.run("uniform", poison=True, seed=s)["p2"] for s in range(6)])
    assert p > q + 0.2 and abs(u - 0.77) < 0.03, (p, q, u)
@t("R2 no learner falls below uniform for any relocation period (attack does not beat the floor); fast relocation costs most")
def _():
    Ls = [10, 100, 6000]; r = e2.sweep(seeds=range(2), Ls=Ls, T=4000); u = np.mean(r["uniform (no memory)"])
    for n, v in r.items():
        if "uniform" not in n: assert min(v) > u - 0.01, (n, v, u)
    v = r["gamma=1.0 (no forgetting)"]; assert v[0] < v[2] - 0.1, v
    assert r["gamma=1.0 + switch-detect"][0] > v[0] + 0.02, (r["gamma=1.0 + switch-detect"][0], v[0])
@t("R3 beacon-only jamming kills the naive rendezvous design at 5% duty; R=5,D=100 holds; data jam costs about 1/13")
def _():
    n = e3.avg(1, 60, "control", T=30000); h = e3.avg(5, 100, "control", T=30000); d = e3.avg(1, 60, "data", T=30000)
    assert n["avail"] < 0.3 and h["avail"] > 0.95 and abs(d["avail"] - 0.917) < 0.02 and abs(n["duty"] - 0.05) < 1e-3, (n, h, d)
@t("R4 slow timestamp ramp: NIS gate sees nothing at 0.1 ppm; guard violated at about guard/r; no false alarms; detector wins only for fast ramps")
def _():
    out, fa, nis0 = e4.evaluate(rs=(0.1, 1.0, 5.0), seeds=range(8))
    assert abs(out[0.1]["nis"] - nis0) < 1.0 and fa == 0.0, (out[0.1], nis0, fa)
    assert out[1.0]["viol_frac"] == 1.0 and 25 <= out[1.0]["t_viol"] <= 40, out[1.0]
    assert out[5.0]["det_frac"] == 1.0 and out[5.0]["t_det"] < out[5.0]["t_viol"], out[5.0]
    assert out[0.1]["det_frac"] == 0.0     # documented limitation: below the skew-check threshold nothing alarms
@t("R5 helpers: untemper inverts MT tempering; xorshift solver reproduces state")
def _():
    def temper(y):
        y ^= y >> 11; y ^= (y << 7) & 0x9D2C5680; y ^= (y << 15) & 0xEFC60000; y ^= y >> 18; return y & 0xFFFFFFFF
    rr = random.Random(5)
    for _ in range(200): x = rr.getrandbits(32); assert e5.untemper(temper(x)) == x
    x0 = 0xDEADBEEF; x = x0; o = []
    for _ in range(12): x = e5.xs32(x); o.append(x & 15)
    sol, rank = e5.xorshift_attack(o); assert sol == x0, (sol, rank)
@t("R5 LCG24 and xorshift32 broken in <= 12 hops, MT19937 cloned from 624 outputs, HMAC at chance")
def _():
    r = e5.run(seed=3); assert r["LCG24"]["max"] <= 12 and r["xorshift32"]["max"] <= 12 and r["MT19937"]["clone_ok"] and r["HMAC-SHA256"]["accuracy"] < 0.12, r
@t("R6 holding the environment still drives secret rate below the monitor level; monitor accepts the normal case")
def _():
    rates = [e6.measure(a, 0.0)["rate"] for a in e6.ALPHAS]
    assert all(rates[i] >= rates[i + 1] - 0.01 for i in range(len(rates) - 1)) and rates[0] > 0.2 and rates[-2] < 0.02, rates
    assert e6.monitor(1.0, 0.0) and not e6.monitor(0.3, 0.0) and not e6.monitor(0.3, 0.3)
@t("R6 mean nudge + still environment leaves under 90 bits of 128 guessable-key entropy")
def _(): assert e6.measure(0.1, 0.3)["key128_bits"] < 90, e6.measure(0.1, 0.3)
@t("R7 Monte Carlo matches closed form; late detection is worthless; history predictor at chance")
def _():
    for a in (0.25, 0.5, 1.0):
        for d in (0.0, 0.5, 0.9): assert abs(e7.delivery_mc(a, d, seed=1) - e7.delivery_cf(a, d)) < 0.01, (a, d)
    blind = e7.delivery_cf(0.0, 0.0); assert abs(e7.delivery_cf(1.0, 0.75) - blind) < 1e-9 and e7.delivery_cf(1.0, 0.0) < 0.06
    assert abs(e7.history_predictor(N=40000) - 1 / 13) < 0.008
@t("R8 scorecard: 8 rows, hardened never worse than baseline, >=5 baseline BROKEN, at least one hardened row still not HOLDS (R4 limitation)")
def _():
    sc = e8.build(); assert len(sc) == 8
    assert all(r["hardened"] <= r["baseline"] + 1e-9 for r in sc) and sum(r["base_verdict"] == "BROKEN" for r in sc) >= 5
    assert any(r["hard_verdict"] != "HOLDS" for r in sc)
print(f"\n{sum(OK)}/{len(OK)} tests passed"); sys.exit(0 if all(OK) else 1)
