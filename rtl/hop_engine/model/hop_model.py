"""Bit-exact Python reference for the FHSS-Link keyed hop engine (rtl/hop_keyed.v) and the 16-bit LFSR baseline (rtl/hop_lfsr.v).

Keyed engine
  digest = SipHash-2-4(key128, msg64 LE)           msg64 = {retry[7:0], slot[55:0]}
  chunks : RW-bit pieces of the digest, least-significant chunk first, NCH of them (default RW=32, NCH=2)
  Lemire unbiased reduction per chunk: p = x*M; accept if (p mod 2^RW) >= (2^RW mod M); channel = p >> RW
  if every chunk is rejected, retry += 1 (new message, new digest).
Key layout: key128 integer; k0 = key[63:0], k1 = key[127:64]  (== the 16 key bytes read little-endian, as in the SipHash reference).
"""
import numpy as np
MASK = (1 << 64) - 1
SLOTW = 56
def rotl(x, b): return ((x << b) | (x >> (64 - b))) & MASK

def sipround(v):
    v0, v1, v2, v3 = v
    v0 = (v0 + v1) & MASK; v1 = rotl(v1, 13); v1 ^= v0; v0 = rotl(v0, 32)
    v2 = (v2 + v3) & MASK; v3 = rotl(v3, 16); v3 ^= v2
    v0 = (v0 + v3) & MASK; v3 = rotl(v3, 21); v3 ^= v0
    v2 = (v2 + v1) & MASK; v1 = rotl(v1, 17); v1 ^= v2; v2 = rotl(v2, 32)
    return [v0, v1, v2, v3]

def siphash24_bytes(key16: bytes, data: bytes) -> int:
    """Generic SipHash-2-4 (any length) - used only to validate against the published test vectors."""
    k0 = int.from_bytes(key16[:8], "little"); k1 = int.from_bytes(key16[8:], "little")
    v = [k0 ^ 0x736f6d6570736575, k1 ^ 0x646f72616e646f6d, k0 ^ 0x6c7967656e657261, k1 ^ 0x7465646279746573]
    n = len(data); end = n - (n % 8)
    for i in range(0, end, 8):
        m = int.from_bytes(data[i:i + 8], "little"); v[3] ^= m
        v = sipround(v); v = sipround(v); v[0] ^= m
    b = (n & 0xff) << 56 | int.from_bytes(data[end:], "little")
    v[3] ^= b; v = sipround(v); v = sipround(v); v[0] ^= b; v[2] ^= 0xff
    for _ in range(4): v = sipround(v)
    return v[0] ^ v[1] ^ v[2] ^ v[3]

def siphash24_word(key128: int, m: int) -> int:
    """SipHash-2-4 of one 64-bit message word (8-byte input) - exactly what the RTL computes (8 rounds)."""
    return siphash24_bytes(key128.to_bytes(16, "little"), (m & MASK).to_bytes(8, "little"))

def lemire(x, M, RW):
    p = x * M; lo = p & ((1 << RW) - 1)
    return (p >> RW) if lo >= ((1 << RW) % M) else None

def hop(key128, slot, M=13, RW=32, NCH=2):
    """returns (channel, retries, first_digest)"""
    slot &= (1 << SLOTW) - 1; retry = 0; first = None
    while True:
        d = siphash24_word(key128, (retry << SLOTW) | slot)
        if first is None: first = d
        for c in range(NCH):
            r = lemire((d >> (RW * c)) & ((1 << RW) - 1), M, RW)
            if r is not None: return r, retry, first
        retry = (retry + 1) & 0xff

def keyed_schedule(key128, start, n, M=13, RW=32, NCH=2):
    return np.array([hop(key128, (start + i) & ((1 << SLOTW) - 1), M, RW, NCH)[0] for i in range(n)])

def lfsr_step(s):
    bit = ((s >> 0) ^ (s >> 2) ^ (s >> 3) ^ (s >> 5)) & 1
    return (s >> 1) | (bit << 15)

def lfsr_schedule(n, M=13, seed=0xACE1):
    """identical to sim/link_sim.py lfsr_hops (seed 0 is mapped to 1 in RTL to avoid the lock-up state)"""
    s = seed or 1; out = []
    for _ in range(n):
        s = lfsr_step(s); out.append(s % M)
    return np.array(out)

# ---- self validation against published SipHash-2-4 vectors ----
def selftest():
    key = bytes(range(16))
    # SipHash paper appendix A: 15-byte input 00..0e
    assert siphash24_bytes(key, bytes(range(15))) == 0xa129ca6149be45e5, "paper vector"
    # reference vectors.h (vectors_sip64): len 0 and len 8
    assert siphash24_bytes(key, b"") == int.from_bytes(bytes([0x31,0x0e,0x0e,0xdd,0x47,0xdb,0x6f,0x72]), "little")
    assert siphash24_bytes(key, bytes(range(8))) == int.from_bytes(bytes([0x62,0x24,0x93,0x9a,0x79,0xf5,0xf5,0x93]), "little")
    # exhaustive unbiasedness of the reduction for small widths
    for RW in (4, 6, 8, 10):
        for M in range(2, 1 << RW if RW < 6 else 40):
            if M > (1 << RW): continue
            cnt = np.zeros(M, int)
            for x in range(1 << RW):
                r = lemire(x, M, RW)
                if r is not None: cnt[r] += 1
            assert len(set(cnt)) == 1 and cnt[0] == (1 << RW) // M, (RW, M)
    return True

if __name__ == "__main__":
    print("selftest:", selftest())
