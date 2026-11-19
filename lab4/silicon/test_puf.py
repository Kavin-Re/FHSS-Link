import numpy as np
from puf import *
from siphash import hop_channels

def test_bch_min_distance_5_and_corrects_2():
    msgs = ((np.arange(128)[:, None] >> np.arange(7)[None, :]) & 1).astype(np.uint8)
    cw = bch_encode(msgs)
    wts = cw.sum(1); assert wts[1:].min() == 5
    rng = np.random.default_rng(0)
    for nerr in (0, 1, 2):
        r = cw.copy()
        for i in range(len(r)):
            for p in rng.choice(15, nerr, replace=False): r[i, p] ^= 1
        m, ok = bch_decode(r); assert ok.all() and np.array_equal(m, msgs)

def test_bch_flags_or_miscorrects_3_errors_never_silently_equal():
    msgs = ((np.arange(128)[:, None] >> np.arange(7)[None, :]) & 1).astype(np.uint8)
    cw = bch_encode(msgs); r = cw.copy(); r[:, [0, 5, 11]] ^= 1
    m, ok = bch_decode(r)
    assert not np.array_equal(m, msgs)           # t=2 code cannot fix 3 errors

def test_ber_matches_theory_ideal_reference():
    rng = np.random.default_rng(1)
    puf = ROArray(40, grad=0.0, sigma_noise=0.1, rng=rng)
    a, b = pairings(puf.n, puf.cols, "neighbor")
    truth = (puf.static[:, a] > puf.static[:, b]).astype(np.uint8)
    got = (puf.read()[:, a] > puf.read()[:, b]).astype(np.uint8)
    # two independent noisy reads differ from truth by ~theory
    ber = (truth != (puf.read()[:, a] > puf.read()[:, b])).mean()
    assert abs(ber - ber_theory(0.1)) < 0.006, (ber, ber_theory(0.1))

def test_gradient_causes_aliasing_and_planefit_fixes_it():
    rng = np.random.default_rng(2)
    puf = ROArray(64, grad=3.0, rng=rng)
    pa = {}
    for k in ("far", "far_planefit", "neighbor"):
        ref = enrol_reference(puf, k); pa[k] = np.abs(ref.mean(0) - 0.5).mean()
    assert pa["far"] > 0.15 and pa["far_planefit"] < 0.08 and pa["neighbor"] < 0.08, pa

def test_fuzzy_extractor_roundtrip_and_key_to_hops():
    rng = np.random.default_rng(3)
    puf = ROArray(8, grad=3.0, sigma_noise=0.05, rng=rng)
    ref = enrol_reference(puf, "neighbor")
    fe = FuzzyExtractor("rep+bch", R=3)
    helper, s = fe.enrol(ref, rng)
    ok = 0
    for hot in (0, 60):
        s2 = fe.regenerate(get_response(puf, "neighbor", dT=hot), helper)
        ok += (s2 == s).all(1).sum()
    assert ok >= 15
    key = FuzzyExtractor.key_from_secret(s[0]); key2 = FuzzyExtractor.key_from_secret(fe.regenerate(get_response(puf, "neighbor"), helper)[0])
    assert key == key2 and len(key) == 16
    assert np.array_equal(hop_channels(key, np.arange(200)), hop_channels(key2, np.arange(200)))

def test_different_chips_give_different_keys():
    rng = np.random.default_rng(4)
    puf = ROArray(6, rng=rng); ref = enrol_reference(puf, "neighbor")
    fe = FuzzyExtractor("rep+bch", R=3); helper, s = fe.enrol(ref, rng)
    keys = {FuzzyExtractor.key_from_secret(x) for x in s}
    assert len(keys) == 6
