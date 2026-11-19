"""Bit-exact Python model of rtl/corr_core.v / approx_correlator.v built on the ApproxKit Python adders (approxkit.LOA / TruncatedAdder / ETA).

Where ApproxKit is found: $APPROXKIT (directory that contains the 'approxkit' package), else ../../../../ApproxKit (laptop layout
FHSS-Link/rtl/approx_correlator/model -> Projects/ApproxKit), else /home/claude/work/approxkit (cloud mirror).
"""
import os, sys
import numpy as np
_here = os.path.dirname(os.path.abspath(__file__))
for cand in (os.environ.get("APPROXKIT"), os.path.join(_here, "..", "..", "..", "..", "ApproxKit"), "/home/claude/work/approxkit"):
    if cand and os.path.isdir(os.path.join(cand, "approxkit")):
        sys.path.insert(0, os.path.abspath(cand)); break
import approxkit as ak

ATYPES = {0: "exact", 1: "LOA", 2: "TRUNC", 3: "ETA"}
def sw_of(N, W): return W + int(np.log2(N)) + 1

def _adder(atype, n, k):
    ke = min(k, n - 1)
    return {0: lambda: ak.ExactAdder(n), 1: lambda: ak.LOA(n, ke), 2: lambda: ak.TruncatedAdder(n, ke), 3: lambda: ak.ETA(n, ke)}[atype]()

def tree_sum(t, W, atype, K, ex=False):
    """t: (B, N) unsigned W-bit leaves -> (B,) tree sum; level l pairs adjacent elements with an adder of width W+l."""
    t = np.asarray(t, dtype=np.int64); N = t.shape[1]; L = int(np.log2(N)); assert 1 << L == N
    for l in range(L):
        add = _adder(0 if (ex or atype == 0) else atype, W + l, K)
        t = add(t[:, 0::2], t[:, 1::2])
    return t[:, 0]

def leaves(code, x, W):
    """code: (B,N) 0/1 (1 = +1 chip), x: (B,N) signed W-bit samples -> unsigned leaves t_i and nneg"""
    u = (np.asarray(x, dtype=np.int64) + (1 << (W - 1))) & ((1 << W) - 1)
    t = np.where(np.asarray(code) == 1, u, (~u) & ((1 << W) - 1))
    return t, (np.asarray(code) == 0).sum(axis=1)

def wrap_signed(v, bits):
    v = np.asarray(v, dtype=np.int64) & ((1 << bits) - 1)
    return np.where(v >= (1 << (bits - 1)), v - (1 << bits), v)

def corr(code, x, W=6, atype=1, K=3, ex=False, comp=0):
    """signed correlation output exactly as the RTL (SW-bit two's complement wrap); ex=True or atype=0 -> exact tree"""
    code = np.asarray(code); x = np.asarray(x); N = code.shape[1]; SW = sw_of(N, W)
    t, nneg = leaves(code, x, W)
    T = tree_sum(t, W, atype, K, ex)
    apx = (atype != 0) and not ex
    return wrap_signed(T + nneg - (N << (W - 1)) + (comp if apx else 0), SW)

def corr_true(code, x):
    return (np.where(np.asarray(code) == 1, 1, -1) * np.asarray(x, dtype=np.int64)).sum(axis=1)

class ModeCtl:
    """cycle-level model of corr_mode_ctrl (acts only on frame ticks)"""
    APPROX, EXACT, COOL = 0, 1, 2
    def __init__(s, dwell=8): s.st = s.EXACT; s.cnt = 0; s.ex = 1; s.dwell = dwell
    def frame(s, ladder):
        used = s.ex; want = (ladder >> 1) & 1
        if s.st == s.APPROX:
            if want: s.st = s.EXACT; s.ex = 1
        elif s.st == s.EXACT:
            if not want: s.st = s.COOL; s.cnt = 1
        else:
            if want: s.st = s.EXACT
            elif s.cnt == s.dwell - 1: s.st = s.APPROX; s.ex = 0; s.cnt = 0
            else: s.cnt += 1
        return used

# ---------------- channel / ADC (same conventions as FHSS-Link lab5/approx_correlator.py) ----------------
STEP, QMAX = 0.5, 31
def make_frames(rng, B, N, W, ebn0_db, step=STEP):
    """DS-SS BPSK, fresh random +-1 code per bit, per-chip amplitude 1, per-chip noise variance sigma2 = N/(2 Eb/N0); W-bit signed ADC (step in chip-amplitude units)."""
    sigma = np.sqrt(N / (2 * 10 ** (ebn0_db / 10)))
    b = rng.choice([-1, 1], size=B)
    code = rng.integers(0, 2, size=(B, N))
    c = np.where(code == 1, 1, -1)
    r = b[:, None] * c + rng.normal(0, sigma, size=(B, N))
    lo, hi = -(1 << (W - 1)), (1 << (W - 1)) - 1
    q = np.clip(np.rint(r / step), lo, hi).astype(np.int64)
    return b, code, q
