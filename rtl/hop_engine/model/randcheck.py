"""Randomness / predictability checks on the RTL OUTPUT streams (dumped by the testbenches), reusing the test battery of
sim/randtests.py (chi-square uniformity, lag-1 serial correlation, runs test, Shannon entropy, adaptive order-3 context predictor),
plus the existing LFSR-break attacker (sim/attack.py LfsrBreaker, re-implemented here verbatim so no repo file is imported or modified).
Usage: python3 model/randcheck.py   (reads results/rtl_stream_*.txt)"""
import os, sys, json
import numpy as np
from math import sqrt, log2, erfc
sys.path.insert(0, os.path.dirname(__file__))
from hop_model import lfsr_schedule, lfsr_step
R = os.path.join(os.path.dirname(__file__), "..", "results")
M = 13

def pnorm2(z): return erfc(abs(z) / sqrt(2))
def tests(h, M):      # same battery as sim/randtests.py tests()
    n = len(h); cnt = np.bincount(h, minlength=M); exp = n / M
    chi = ((cnt - exp) ** 2 / exp).sum(); df = M - 1
    z = ((chi / df) ** (1 / 3) - (1 - 2 / (9 * df))) / sqrt(2 / (9 * df)); p_chi = erfc(z / sqrt(2)) / 2
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
                entropy_bits=round(float(H), 3), max_entropy=round(log2(M), 3), predictor_acc=round(hit / (n - 3), 4), chance=round(1 / M, 4),
                min_count=int(cnt.min()), max_count=int(cnt.max()))

class LfsrBreaker:   # verbatim logic of sim/attack.py LfsrBreaker (candidate elimination over all 65535 nonzero states)
    def __init__(self, M): self.M = M; self.cand = np.arange(1, 65536, dtype=np.uint32); self.seen = 0
    def step(self, s): bit = ((s >> 0) ^ (s >> 2) ^ (s >> 3) ^ (s >> 5)) & 1; return (s >> 1) | (bit << 15)
    def observe(self, ch): self.cand = self.step(self.cand); self.cand = self.cand[(self.cand % self.M) == ch]; self.seen += 1
    def identified(self): return len(self.cand) == 1

def hops_to_identify(stream, M=13, limit=200):
    a = LfsrBreaker(M)
    for h in stream[:limit]:
        a.observe(int(h))
        if a.identified(): return a.seen, True
        if len(a.cand) == 0: return a.seen, False
    return limit, False

if __name__ == "__main__":
    out = {}
    rtl = np.loadtxt(f"{R}/rtl_stream_m13.txt", dtype=int)
    assert len(rtl) == 60000
    for k in range(3):
        out[f"keyed RTL key{k+1} (20000 hops)"] = tests(rtl[k * 20000:(k + 1) * 20000], M)
    out["keyed RTL all 60000"] = tests(rtl, M)
    lf = np.loadtxt(f"{R}/rtl_stream_lfsr.txt", dtype=int)
    assert (lf == lfsr_schedule(20000, M, 0xACE1)).all()
    out["LFSR16 RTL (20000 hops)"] = tests(lf, M)
    for n, r in out.items(): print(f"{n:34s}", r)
    # LFSR break: hops until the existing attacker's candidate set is a single state, on the RTL stream and over 300 random seeds (python model == RTL, verified bit-exact)
    n_rtl, ok = hops_to_identify(lf); print("\nLFSR break on RTL stream (seed ACE1): identified after", n_rtl, "hops", ok)
    rng = np.random.default_rng(7); H = []
    for s in rng.integers(1, 65536, 300):
        n, ok = hops_to_identify(lfsr_schedule(200, M, int(s)))
        if ok: H.append(n)
    H = np.array(H); print(f"LFSR break over 300 random seeds: identified {len(H)}/300; hops to identify min={H.min()} median={int(np.median(H))} mean={H.mean():.1f} p90={int(np.percentile(H, 90))} max={H.max()}")
    # the same attacker against the keyed RTL stream: its candidate set empties (model mismatch), i.e. it learns nothing usable
    n_k, ok_k = hops_to_identify(rtl[:20000]); print("same attacker vs keyed RTL stream: identified=%s, candidate set exhausted after %d hops" % (ok_k, n_k))
    out["_lfsr_break"] = dict(rtl_seed_ACE1=n_rtl, seeds300=dict(n=len(H), min=int(H.min()), median=int(np.median(H)), mean=round(float(H.mean()), 2), p90=int(np.percentile(H, 90)), max=int(H.max())))
    json.dump(out, open(f"{R}/randcheck.json", "w"), indent=1)
