import numpy as np
from trojan import *
from siphash import split_key

KEY = split_key(bytes(range(16)))

def test_pre_trigger_identical_post_trigger_biased():
    T = 6000
    clean, troj = HopEngine(KEY), TrojanEngine(KEY, trigger=T, beta_k=64, mode="stuck", target=3)
    a, b = clean.hops(0, T), troj.hops(0, T)
    assert np.array_equal(a, b)                                  # stealth before trigger
    a, b = clean.hops(T, 20000), troj.hops(T, 20000)
    frac3 = np.mean(b == 3)
    exp = 1 / 13 + 0.25 * 12 / 13
    assert abs(frac3 - exp) < 0.02 and np.mean(a != b) > 0.15

def test_bias_pmf_normalised():
    for mode in ("stuck", "narrow"):
        p = bias_pmf(0.2, mode); assert abs(p.sum() - 1) < 1e-12 and p.min() > 0

def test_chi2_tail_exact_values():
    assert abs(chi2_sf_even(21.0261, 12) - 0.05) < 2e-4         # chi2(12) 95th percentile = 21.026
    assert abs(chi2_threshold(0.05) - 21.026) < 0.01

def test_clean_clean_false_alarm_rate_matches_threshold():
    rng = np.random.default_rng(0); W = 256
    c = rng.multinomial(W, [1 / 13] * 13, size=200000)
    thr = chi2_threshold(0.001)
    assert abs((chi2_stat(c, W) > thr).mean() - 0.001) < 0.0007

def test_detectors_flag_strong_trojan_not_clean():
    rng = np.random.default_rng(1); W = 256
    cl = rng.multinomial(W, [1 / 13] * 13, size=400); tr = rng.multinomial(W, bias_pmf(0.4), size=400)
    thr = chi2_threshold(1e-5)
    assert (chi2_stat(cl, W) > thr).mean() < 0.01 and (chi2_stat(tr, W) > thr).mean() > 0.9

def test_real_engine_stream_is_flagged_by_randtests_when_biased():
    import refsim
    rt = refsim.load("randtests")
    if rt is None: return
    T = 0
    h = TrojanEngine(KEY, trigger=0, beta_k=51, mode="stuck").hops(0, 20000)
    res = rt.tests(h, 13)
    assert res["chi_p"] < 1e-3
    assert rt.tests(HopEngine(KEY).hops(0, 20000), 13)["chi_p"] > 0.001
