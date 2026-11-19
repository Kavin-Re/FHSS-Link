#!/usr/bin/env python3
"""Stimulus + expected outputs for tb/tb_approx_correlator.v from the bit-exact Python model (corr_model.py).
One line per clock in stim_*.mem: {valid(1), ladder(2), code(N), x(N*W)} hex; exp_*.mem: one line per valid frame: {ex(1), bit(1), sum(SW)} hex.
Ladder is a random walk with runs of 1..40 frames so that the controller reaches ST_APPROX (DWELL consecutive 'approximate-allowed' frames)."""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from corr_model import *
V = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "vectors"); os.makedirs(V, exist_ok=True)
W = 6; DWELL = 8; NF = 4000
# tag: (N, ATYPE, K, COMP)
from ber_model import calib                       # COMP = -round(mean approx-exact error), the same calibration the BER model uses
_c = lambda N, a, k: calib(N, a, k)[0]
CONFIGS = {"n16_loa3": (16, 1, 3, _c(16, 1, 3)), "n32_loa3": (32, 1, 3, _c(32, 1, 3)), "n64_loa3": (64, 1, 3, _c(64, 1, 3)),
           "n32_trunc2": (32, 2, 2, _c(32, 2, 2)), "n32_eta3": (32, 3, 3, 0), "n64_loa4": (64, 1, 4, 0), "n32_exact": (32, 0, 0, 0)}
def main():
    rows = []
    for tag, (N, a, k, comp) in CONFIGS.items():
        rng = np.random.default_rng(abs(hash(tag)) % 1000 if False else sum(map(ord, tag)))
        SW = sw_of(N, W)
        # frames: mixture of extreme and random samples + noisy BPSK frames
        code = rng.integers(0, 2, size=(NF, N))
        x = rng.integers(-(1 << (W - 1)), 1 << (W - 1), size=(NF, N))
        x[NF // 4: NF // 3] = -(1 << (W - 1)); x[NF // 3: NF // 3 + 50] = (1 << (W - 1)) - 1
        _, c2, q2 = make_frames(rng, NF // 4, N, W, 3.0); code[:NF // 4] = c2; x[:NF // 4] = q2
        # ladder walk
        lad = []; 
        while len(lad) < NF: lad += [int(rng.integers(0, 4))] * int(rng.integers(1, 41))
        lad = lad[:NF]
        mc = ModeCtl(DWELL); stim = []; exp = []; nap = 0
        for i in range(NF):
            gap = int(rng.integers(0, 3))                      # idle clocks before the frame (random ladder, not sampled)
            for _ in range(gap):
                stim.append((0, int(rng.integers(0, 4)), int(rng.integers(0, 1 << min(N, 62))), 0, 0, 0))
            used = mc.frame(lad[i])
            S = int(corr(code[i:i+1], x[i:i+1], W, a, k, bool(used), comp)[0])
            nap += (not used)
            if used or a == 0: assert S == int(corr_true(code[i:i+1], x[i:i+1])[0])
            cv = sum(int(b) << j for j, b in enumerate(code[i]))
            xv = sum((int(v) & ((1 << W) - 1)) << (W * j) for j, v in enumerate(x[i]))
            stim.append((1, lad[i], cv, xv, 1, 0))
            exp.append((used, int(S >= 0), S & ((1 << SW) - 1)))
        dig = (N + N * W + 3 + 3) // 4
        with open(f"{V}/stim_{tag}.mem", "w") as f:
            for v, l, cv, xv, _, __ in stim: f.write("%0*x\n" % (dig, (v << (2 + N + N * W)) | (l << (N + N * W)) | (cv << (N * W)) | xv))
        with open(f"{V}/exp_{tag}.mem", "w") as f:
            for e, b, s in exp: f.write("%0*x\n" % ((SW + 2 + 3) // 4, (e << (SW + 1)) | (b << SW) | s))
        rows.append(f"{tag}: N={N} ATYPE={a} K={k} COMP={comp} frames={NF} clocks={len(stim)} approx_frames={nap} exact_frames={NF-nap}")
    print("\n".join(rows))
if __name__ == "__main__": main()
