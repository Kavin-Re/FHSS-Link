"""Idea 22: randomness and predictability tests for hop schedules (M=13, 20,000 hops).
Schedules: LFSR16, keyed PRF (HMAC-SHA256), chaotic logistic map (r=3.99), Python random (Mersenne Twister, for reference).
Tests: chi-square uniformity, lag-1 serial correlation, runs test (above/below median), Shannon entropy,
and an adaptive order-3 context predictor (accuracy vs the 1/M chance level)."""
import numpy as np, json
from math import sqrt, log2, erfc
from schedule import lfsr_schedule, prf_schedule
import random

def chaotic(n, M, x=0.3141, r=3.99):
    out = []
    for _ in range(n):
        x = r * x * (1 - x); out.append(int(x * M) % M)
    return np.array(out)

def mt(n, M, seed=5):
    r = random.Random(seed); return np.array([r.randrange(M) for _ in range(n)])

def pnorm2(z): return erfc(abs(z) / sqrt(2))   # two-sided

def tests(h, M):
    n = len(h); cnt = np.bincount(h, minlength=M); exp = n / M
    chi = ((cnt - exp) ** 2 / exp).sum(); df = M - 1
    z = ((chi / df) ** (1 / 3) - (1 - 2 / (9 * df))) / sqrt(2 / (9 * df)); p_chi = erfc(z / sqrt(2)) / 2   # Wilson-Hilferty, upper tail
    x = h - h.mean(); r1 = (x[:-1] * x[1:]).sum() / (x * x).sum(); p_r1 = pnorm2(r1 * sqrt(n))
    b = h > np.median(h); runs = 1 + (b[1:] != b[:-1]).sum(); n1 = b.sum(); n0 = n - n1
    mu = 2 * n1 * n0 / n + 1; var = (mu - 1) * (mu - 2) / (n - 1); p_run = pnorm2((runs - mu) / sqrt(var))
    p = cnt / n; H = -(p[p > 0] * np.log2(p[p > 0])).sum()
    ctx = {}; hit = 0
    for i in range(3, n):
        key = tuple(h[i - 3:i]); c = ctx.setdefault(key, np.zeros(M))
        if c.max() > 0 and c.argmax() == h[i]: hit += 1
        c[h[i]] += 1
    return dict(chi_p=round(float(p_chi), 3), serial_corr_p=round(float(p_r1), 3), runs_p=round(float(p_run), 3),
                entropy_bits=round(float(H), 3), max_entropy=round(log2(M), 3), predictor_acc=round(hit / (n - 3), 4), chance=round(1 / M, 4))

if __name__ == "__main__":
    M, n = 13, 20000; res = {}
    for name, h in (("LFSR16", lfsr_schedule(n, M)), ("keyed PRF", prf_schedule(n, M)), ("logistic map", chaotic(n, M)), ("Mersenne Twister", mt(n, M))):
        res[name] = tests(h, M); print(f"{name:17s}", res[name])
    json.dump(res, open("figures/randtests.json", "w"), indent=1)
