import numpy as np
from sidechannel import *
from siphash import split_key, siphash24, MASK, C2, C3

KEY = bytes.fromhex("5f0c3a91d27e48b6a1c4098e7d3b2f60")

def test_leakage_points_match_real_siphash():
    # trace-level intermediates must equal the values inside the scalar implementation
    k0, k1 = split_key(KEY); m = 0x1122334455667788; p = {}
    siphash24(KEY, m.to_bytes(8, "little"), probe=p)
    rng = np.random.default_rng(0)
    T = leak_unmasked(KEY, np.array([m], dtype=np.uint64), 0.0, rng)
    exp1 = [bin((p["v3_after_xor"] >> (8 * i)) & 255).count("1") for i in range(8)]
    exp2 = [bin((p["v2_after_add"] >> (8 * i)) & 255).count("1") for i in range(8)]
    assert list(T[0, :8]) == exp1 and list(T[0, 8:]) == exp2

def test_secadd_correct():
    rng = np.random.default_rng(3)
    x, y = rand64(rng, 500), rand64(rng, 500)
    xr, yr = rand64(rng, 500), rand64(rng, 500)
    s0, s1 = secadd(x ^ xr, xr, y ^ yr, yr, rng)
    with np.errstate(over="ignore"):
        assert np.array_equal(s0 ^ s1, x + y)

def test_masked_shares_recombine():
    rng = np.random.default_rng(4); m = rand64(rng, 200); k0, k1 = split_key(KEY)
    (a0, a1), (b0, b1) = shares_masked(KEY, m, rng)
    with np.errstate(over="ignore"):
        assert np.array_equal(a0 ^ a1, U(k1 ^ C3) ^ m)
        assert np.array_equal(b0 ^ b1, U(k0 ^ C2) + (U(k1 ^ C3) ^ m))

def test_cpa_recovers_key_low_noise():
    rng = np.random.default_rng(5); m = rand64(rng, 600)
    T = leak_unmasked(KEY, m, 0.5, rng)
    k0, k1 = cpa_attack(T, m)
    assert (k0, k1) == split_key(KEY)

def test_cpa_hd_stage2_with_oracle_k1():
    rng = np.random.default_rng(6); m = rand64(rng, 1500); k0, k1 = split_key(KEY)
    T = leak_unmasked(KEY, m, 0.5, rng, model2="HD")
    est0, _ = cpa_attack(T, m, model2="HD", k1_oracle=k1)
    # HD of an addition hides the MSB of every byte: only those 8 bits may differ
    assert (est0 ^ k0) & ~0x8080808080808080 & MASK == 0
    mk = lambda a, b: a.to_bytes(8, "little") + b.to_bytes(8, "little")
    msg = (12345).to_bytes(8, "little")
    assert resolve_msb_ambiguity(est0, k1, mk, msg, siphash24(KEY, msg)) == k0

def test_cpa_fails_with_too_few_traces_high_noise():
    rng = np.random.default_rng(7); m = rand64(rng, 20)
    T = leak_unmasked(KEY, m, 4.0, rng)
    assert cpa_attack(T, m) != split_key(KEY)

def test_masked_defeats_first_order():
    rng = np.random.default_rng(8); m = rand64(rng, 20000); k0, k1 = split_key(KEY)
    T = leak_masked(KEY, m, 0.5, rng)
    est = cpa_firstorder_masked(T, m, stage=1)
    assert byte_hits(est, k1) <= 1        # chance level is 8/256 = 0.03 bytes
    est0 = cpa_firstorder_masked(T, m, k1_oracle=k1, stage=2)
    assert byte_hits(est0, k0) <= 1

def test_masking_off_control_is_broken():
    rng = np.random.default_rng(9); m = rand64(rng, 3000); k0, k1 = split_key(KEY)
    T = leak_masked(KEY, m, 0.5, rng, mask_on=False)
    assert cpa_firstorder_masked(T, m, stage=1) == k1

def test_second_order_breaks_first_order_masking():
    rng = np.random.default_rng(10); m = rand64(rng, 20000); k0, k1 = split_key(KEY)
    T = leak_masked(KEY, m, 0.5, rng)
    assert byte_hits(cpa_secondorder_masked(T, m), k1) >= 7

def test_tvla_unmasked_leaks_masked_does_not():
    rng = np.random.default_rng(11); n = 6000
    fixed = np.full(n, 0x0123456789abcdef, dtype=np.uint64); rnd = rand64(rng, n)
    tu = np.abs(welch_t(leak_unmasked(KEY, fixed, 1.0, rng), leak_unmasked(KEY, rnd, 1.0, rng))).max()
    Tf, Tr = leak_masked(KEY, fixed, 1.0, rng), leak_masked(KEY, rnd, 1.0, rng)
    tm = np.abs(welch_t(Tf, Tr)).max()
    assert tu > 10 and tm < 4.5
