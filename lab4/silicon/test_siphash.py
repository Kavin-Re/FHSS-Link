import numpy as np
from siphash import *

KEY = bytes(range(16))
# Public reference vectors (SipHash paper appendix / vectors.h): key 00..0f, message 00..(n-1), 64-bit output as LE bytes.
REF_BYTES = {
    0: "310e0edd47db6f72", 1: "fd67dc93c539f874", 2: "5a4fa9d909806c0d", 3: "2d7efbd796666785",
    4: "b78771 27e09427cf".replace(" ", ""), 5: "8da699cd64557618", 6: "cee3fe586e46c9cb", 7: "37d1018bf50002ab",
    8: "6224939a79f5f593",
}

def test_paper_vector_15():
    assert siphash24(KEY, bytes(range(15))) == 0xa129ca6149be45e5   # value printed in the SipHash paper

def test_reference_vectors():
    for n, hx in REF_BYTES.items():
        want = int.from_bytes(bytes.fromhex(hx), "little")
        assert siphash24(KEY, bytes(range(n))) == want, n

def test_vectorised_matches_scalar():
    rng = np.random.default_rng(1)
    key = rng.bytes(16); k0, k1 = split_key(key)
    ms = rng.integers(0, 2**63, 50, dtype=np.uint64) * np.uint64(2) + np.uint64(1)
    got = siphash24_u64(k0, k1, ms)
    for m, g in zip(ms, got):
        assert siphash24(key, int(m).to_bytes(8, "little")) == int(g)

def test_vectorised_fault_matches_scalar():
    key = bytes(range(16)); k0, k1 = split_key(key); m = 0x0123456789abcdef
    for r in range(8):
        for w in range(4):
            a = siphash24(key, m.to_bytes(8, "little"), fault=(r, w, 1 << 17))
            b = int(siphash24_u64(k0, k1, np.array([m], dtype=np.uint64), fault=(r, w, 1 << 17))[0])
            assert a == b

def test_probe_points():
    key = bytes(range(16)); k0, k1 = split_key(key); m = 0xdeadbeef01234567
    p = {}
    siphash24(key, m.to_bytes(8, "little"), probe=p)
    assert p["v3_after_xor"] == (k1 ^ C3 ^ m)
    assert p["v2_after_add"] == (((k0 ^ C2) + (k1 ^ C3 ^ m)) & MASK)

def test_hop_range_and_uniformity():
    h = hop_channels(KEY, np.arange(26000), 13)
    assert h.min() >= 0 and h.max() <= 12
    cnt = np.bincount(h, minlength=13); assert cnt.min() > 1700 and cnt.max() < 2300
