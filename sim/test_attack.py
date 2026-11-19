import numpy as np
from schedule import lfsr_schedule, prf_schedule
from attack import LfsrBreaker, FreqGuesser, attack_run

def check(n, c):
    print(("PASS " if c else "FAIL ") + n); assert c

M = 13
ids = []
for key in range(1, 40):
    s = lfsr_schedule(200, M, key=key * 1553 % 65535 + 1)
    pdr, ident = attack_run(s, M, LfsrBreaker(M), slots=200)
    ids.append(ident)
check(f"LFSR state recovered in every trial (max {max(ids)} hops, mean {np.mean(ids):.1f})", all(i is not None for i in ids) and max(ids) < 40)
s = prf_schedule(5000, M)
cnt = np.bincount(s, minlength=M) / len(s)
check("PRF schedule uniform", cnt.max() - cnt.min() < 0.02)
pdr_l, _ = attack_run(lfsr_schedule(3000, M), M, LfsrBreaker(M))
pdr_p, _ = attack_run(prf_schedule(3000, M), M, LfsrBreaker(M))
check(f"adaptive jammer kills LFSR link (PDR {pdr_l:.3f})", pdr_l < 0.15)
check(f"same attacker vs keyed PRF stays near chance (PDR {pdr_p:.3f})", pdr_p > 0.85)
print("ALL PASSED")
