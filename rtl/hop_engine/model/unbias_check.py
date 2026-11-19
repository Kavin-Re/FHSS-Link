"""Exact (integer, no sampling) check that the Lemire reduction used in rtl/hop_keyed.v is unbiased:
for a uniform RW-bit chunk, every channel c in 0..M-1 is hit by exactly (2^RW - (2^RW mod M)) / M accepted values.
Also prints the reject probability per attempt and the probability that all NCH attempts of one digest are rejected."""
def counts(M, RW):
    T = (1 << RW) % M; out = []
    for c in range(M):
        lo = c * (1 << RW) + T; hi = (c + 1) * (1 << RW) - 1
        xmin = -(-lo // M); xmax = hi // M          # x with x*M in [lo, hi]
        out.append(max(0, xmax - xmin + 1))
    return T, out
ok = True
for RW in (8, 16, 32):
    for M in range(2, 257 if RW > 8 else 200):
        if M > (1 << RW): continue
        T, c = counts(M, RW)
        if len(set(c)) != 1 or c[0] * M != (1 << RW) - T: ok = False; print("FAIL", RW, M)
T, c = counts(13, 32)
print("all (RW,M) combos exact-uniform:", ok)
print(f"M=13 RW=32: 2^32 mod 13 = {T}; accepted values per channel = {c[0]} (all {len(set(c))} distinct count value(s)); reject prob/attempt = {T/2**32:.3e}; P(both 32-bit halves rejected) = {(T/2**32)**2:.3e}")
base = (2**32) // 13
print(f"for comparison, plain '(x mod 13)' on 32 bits: counts differ by 1 out of ~{base} -> relative bias {1/base:.2e}; 16-bit LFSR state mod 13: 65535 = 13*5041 + 2 -> 2 channels hit 5042x, 11 hit 5041x (relative bias {1/5041:.2e}); LFSR bias is irrelevant next to its predictability")
