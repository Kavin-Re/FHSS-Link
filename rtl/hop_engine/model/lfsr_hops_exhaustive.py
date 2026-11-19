"""Exhaustive LFSR-break measurement: hops until the repo's LfsrBreaker (candidate elimination) leaves exactly one state,
over ALL 65,535 nonzero 16-bit seeds, M=13. Replaces the sampled figures (300 seeds, 39 keys, 100 keys) with the exact distribution.
Also cross-checks the randcheck.py re-implementation against sim/attack.py attack_run on the first 500 seeds.
Usage: python3 model/lfsr_hops_exhaustive.py   (about 75 s, numpy only; writes results/lfsr_hops_exhaustive.txt)"""
import os, sys
import numpy as np
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "sim"))
from randcheck import hops_to_identify
from hop_model import lfsr_schedule
M = 13
if __name__ == "__main__":
    out = []
    try:
        import attack as A
        for s in range(1, 501):
            _, ident = A.attack_run(lfsr_schedule(60, M, s), M, A.LfsrBreaker(M), slots=60)
            n, ok = hops_to_identify(lfsr_schedule(60, M, s), limit=60)
            assert ok and ident == n, (s, ident, n)
        out.append("cross-check: sim/attack.py attack_run identification slot == randcheck.hops_to_identify for seeds 1..500: OK")
    except ImportError:
        out.append("cross-check skipped: sim/attack.py not importable")
    H = np.array([hops_to_identify(lfsr_schedule(40, M, s), limit=40)[0] for s in range(1, 65536)])
    c = np.bincount(H)
    out.append(f"exhaustive over all {len(H)} nonzero seeds, M={M}: min={H.min()} max={H.max()} mean={H.mean():.3f} median={int(np.median(H))}")
    for k in range(H.min(), H.max() + 1): out.append(f"  identified after {k} hops: {c[k]} seeds ({100 * c[k] / len(H):.1f} %)")
    out.append("information floor log13(65535) = %.2f hops" % (np.log(65535) / np.log(M)))
    txt = "\n".join(out); print(txt)
    open(os.path.join(HERE, "..", "results", "lfsr_hops_exhaustive.txt"), "w").write(txt + "\n")
