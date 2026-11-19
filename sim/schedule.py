"""Hop schedule generators. Both TX and RX derive the same sequence from a shared secret."""
import hashlib, hmac
import numpy as np
from link_sim import lfsr_hops


def lfsr_schedule(n, M, key=0xACE1):
    """Weak baseline: 16-bit LFSR, hop = state mod M. Cheap in hardware, but only 65535 possible states."""
    return lfsr_hops(n, M, seed=key)


def prf_schedule(n, M, key=b"demo-key"):
    """Keyed PRF: HMAC-SHA256(key, counter) -> channel. Unpredictable without the key.
    Unbiased: reject values >= largest multiple of M below 2**32 (rejection sampling)."""
    out, ctr = [], 0
    lim = (2**32 // M) * M
    while len(out) < n:
        d = hmac.new(key, ctr.to_bytes(8, "big"), hashlib.sha256).digest()
        ctr += 1
        for i in range(0, 32, 4):
            v = int.from_bytes(d[i:i + 4], "big")
            if v < lim:
                out.append(v % M)
                if len(out) == n:
                    break
    return np.array(out)
