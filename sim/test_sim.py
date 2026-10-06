"""Sanity tests: Monte Carlo must agree with theory within statistical error. Run: python3 test_sim.py"""
from math import sqrt
from fhss_sim import *


def close(mc, th, n, label, nsig=5):
    sd = sqrt(max(th * (1 - th), 1e-12) / n)
    ok = abs(mc - th) <= nsig * sd + 1e-4
    print(f"{'PASS' if ok else 'FAIL'}  {label}: MC={mc:.5f} theory={th:.5f} (5 sigma={nsig*sd:.5f})")
    return ok


n = 400_000
res = []
res.append(close(simulate_ber("fixed", 4, None, n), ber_awgn_theory(4), n, "AWGN only, Eb/N0=4 dB"))
res.append(close(simulate_ber("fixed", 10, 0.0, n), ber_tone_theory(10, 1.0), n, "fixed + tone JSR=0 dB, Eb/N0=10 dB"))
res.append(close(simulate_ber("fixed", 10, 10.0, n), ber_tone_theory(10, 10.0), n, "fixed + tone JSR=10 dB, Eb/N0=10 dB"))
res.append(close(simulate_ber("fh", 10, 10.0, n, M=8, k=1), ber_fh_theory(10, 10.0, 8, 1), n, "FH M=8, k=1, JSR=10 dB"))
res.append(close(simulate_ber("fh", 10, 10.0, n, M=13, k=2), ber_fh_theory(10, 10.0, 13, 2), n, "FH M=13, k=2, JSR=10 dB"))
res.append(close(simulate_ber("ds", 10, None, 100_000, Gp=16), ber_awgn_theory(10), 100_000, "DS no jammer = AWGN"))
res.append(close(simulate_ber("ds", 6, 10.0, 100_000, Gp=32), ber_ds_theory(6, 10 ** 1.0, 32), 100_000, "DS Gp=32, JSR=10 dB, Eb/N0=6 dB"))
assert simulate_ber("fixed", 10, 10.0, 100_000) > 5 * simulate_ber("ds", 10, 10.0, 100_000, Gp=64) , "DS should beat fixed under strong interference"
print("ALL PASSED" if all(res) else "SOME FAILED")
raise SystemExit(0 if all(res) else 1)
