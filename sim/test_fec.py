import numpy as np, itertools
from fec import *
rng = np.random.default_rng(5)
def check(n, c): print(("PASS " if c else "FAIL ") + n); assert c
b = rng.integers(0, 2, 400).astype(np.uint8)
c = ham_encode(b); ok = True
for t in range(0, len(c), 7):   # one error per block
    d = c.copy(); d[t + rng.integers(7)] ^= 1; ok &= (ham_decode(d)[:400] == b).all() if t == 0 else True
d = c.copy()
for t in range(0, len(c), 7): d[t + rng.integers(7)] ^= 1
check("Hamming corrects 1 error in every block", (ham_decode(d)[:400] == b).all())
x = interleave(c, 7); x[10:17] ^= 1   # burst of 7 consecutive channel bits
check("interleaver turns a 7-bit burst into correctable single errors", (ham_decode(deinterleave(x, 7, len(c)))[:400] == b).all())
e = conv_encode(b); check("conv encode length 2(n+2)", len(e) == 2 * (len(b) + 2))
check("Viterbi decodes clean stream", (viterbi_decode(e) == b).all())
e2 = e.copy(); e2[[20, 90, 200, 333, 500]] ^= 1
check("Viterbi corrects 5 well-separated errors", (viterbi_decode(e2) == b).all())
data = [rng.integers(0, 256, 16).astype(np.uint8) for _ in range(4)]; n = 7
pk = erasure_encode(data, n)
good = 0
for lost in itertools.combinations(range(n), 3):   # any 3 lost of 7: still k=4 left
    rec = {i: pk[i] for i in range(n) if i not in lost}
    out = erasure_decode(rec, n, 4); good += all((o == d).all() for o, d in zip(out, data))
check(f"erasure (7,4): all {good}/35 loss patterns of 3 packets recovered", good == 35)
check("4 lost of 7 cannot be decoded", erasure_decode({i: pk[i] for i in range(3)}, n, 4) is None)
print("ALL PASSED")
