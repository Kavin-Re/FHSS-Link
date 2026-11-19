"""Experiment 1b: first-order CPA on the 2-share masked engine with MORE TRIALS, including the 32,000-trace stage 2 that exp1_cpa.py never ran.
Same model and attack functions as exp1_cpa.py section B (sidechannel.py unchanged); only the number of trials differs and different seeds are used.
Work is split into batches so that each call stays short (the 32,000-trace cell costs about 4 s per trial):
    python3 exp1b_masked_firstorder_trials.py run N TRIALS BATCH_ID     # adds one batch to results/exp1b_masked_firstorder_trials.json
    python3 exp1b_masked_firstorder_trials.py report                    # pooled table: hits, Wilson 95 % interval, exact binomial tail
sigma = 1, chance per byte 1/256 (the tail is also given for 2/256, the chance level if the HD/MSB ambiguity halved the search space).
Numpy only."""
import sys, json, os, time
import numpy as np
from math import comb, sqrt
from sidechannel import *
from siphash import split_key

OUT = "results/exp1b_masked_firstorder_trials.json"
SIGMA = 1.0

def tail(n, x, p): return float(sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(x, n + 1)))
def wilson(x, n, z=1.96):
    ph = x / n; d = 1 + z * z / n; c = ph + z * z / (2 * n); h = z * sqrt(ph * (1 - ph) / n + z * z / (4 * n * n))
    return [max(0.0, (c - h) / d), (c + h) / d]
def load(): return json.load(open(OUT)) if os.path.exists(OUT) else {"sigma": SIGMA, "batches": {}}

def run(n, trials, batch):
    rng = np.random.default_rng([20261008, n, batch]); h1 = h2 = 0
    for t in range(trials):
        key = rng.bytes(16); k0, k1 = split_key(key); m = rand64(rng, n)
        T = leak_masked(key, m, SIGMA, rng)
        h1 += byte_hits(cpa_firstorder_masked(T, m, stage=1), k1)
        h2 += byte_hits(cpa_firstorder_masked(T, m, k1_oracle=k1, stage=2), k0)
    R = load(); R["batches"][f"{n}/{batch}"] = dict(N=n, batch=batch, trials=trials, stage1_hits=int(h1), stage2_hits=int(h2))
    json.dump(R, open(OUT, "w"), indent=1); print(f"N={n} batch {batch}: {trials} trials, stage1 {h1}/{8 * trials}, stage2 {h2}/{8 * trials}")

def report():
    R = load(); print(f"first-order CPA on the masked engine, sigma={SIGMA}; pooled over batches; chance 1/256 per byte")
    for n in sorted({b["N"] for b in R["batches"].values()}):
        bs = [b for b in R["batches"].values() if b["N"] == n]; tr = sum(b["trials"] for b in bs); nb = 8 * tr
        for name, f in (("stage 1", "stage1_hits"), ("stage 2 (oracle k1)", "stage2_hits")):
            h = sum(b[f] for b in bs); w = wilson(h, nb)
            print(f"  N={n:6d} {name:20s}: {h:3d}/{nb} bytes ({tr} trials) = {h / nb:.4f}  Wilson95 [{w[0]:.4f}, {w[1]:.4f}]  P(X>=hits|1/256)={tail(nb, h, 1 / 256):.3g}  P(X>=hits|2/256)={tail(nb, h, 2 / 256):.3g}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "run": run(int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]))
    else: report()
