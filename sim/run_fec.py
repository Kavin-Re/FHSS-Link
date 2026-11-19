import numpy as np, matplotlib, json; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from math import comb
from fec import *
rng = np.random.default_rng(11)
def qf(x): from math import erfc, sqrt; return 0.5 * erfc(x / sqrt(2))
def chan(bits, ebn0_db, rate):
    es = rate * 10 ** (ebn0_db / 10); p = qf(np.sqrt(2 * es))
    return bits ^ (rng.random(len(bits)) < p).astype(np.uint8)
eb = np.arange(2, 9.5, 1.0); N = 40000; res = {"ebn0": eb.tolist()}
unc, ham, ham_i, cv = [], [], [], []
for e in eb:
    b = rng.integers(0, 2, N).astype(np.uint8)
    unc.append(((chan(b, e, 1.0)) != b).mean())
    c = ham_encode(b); ham.append((ham_decode(chan(c, e, 4 / 7))[:N] != b).mean())
    bb = b[:4000]; c = conv_encode(bb); cv.append((viterbi_decode(chan(c, e, 0.5)) != bb).mean())
plt.figure(); 
for y, l in ((unc, "uncoded BPSK"), (ham, "Hamming(7,4)"), (cv, "conv K=3 r=1/2 + Viterbi")): plt.semilogy(eb, np.maximum(y, 2e-6), "o-", label=l)
plt.xlabel("Eb/N0 (dB)"); plt.ylabel("BER after decoding"); plt.grid(True, which="both", alpha=.3); plt.legend(); plt.title("Coding gain on AWGN (hard decision)")
plt.savefig("figures/10_coding_gain.png", dpi=130); plt.close()
res.update(unc=unc, ham=ham, conv=cv)
# packet level: block (n,k) sent over n hops, loss prob per packet p (hopping vs jammed set), goodput = k/n * P(>=k arrive)
def pdecode(n, k, p): return sum(comb(n, i) * (1 - p) ** i * p ** (n - i) for i in range(k, n + 1))
M = 13; pl = lambda kj: (kj / M) * 0.95 + (1 - kj / M) * 0.01
rows = []
plt.figure()
for kj, st in ((1, "o-"), (3, "s-"), (6, "^-")):
    p = pl(kj); pts = []
    for n, k in [(1, 1), (5, 4), (6, 4), (7, 4), (8, 4), (10, 4), (12, 4), (8, 6), (10, 8)]:
        pts.append((k / n, pdecode(n, k, p), k / n * pdecode(n, k, p), n, k))
        rows.append(dict(jammed_channels=kj, n=n, k=k, rate=k / n, block_success=pts[-1][1], goodput=pts[-1][2]))
    plt.scatter([q[0] for q in pts], [q[1] for q in pts], label=f"{kj} of 13 channels jammed")
    for q in pts: plt.annotate(f"({q[3]},{q[4]})", (q[0], q[1]), fontsize=6)
plt.xlabel("code rate k/n (overhead = 1/rate - 1)"); plt.ylabel("probability the block is decoded"); plt.grid(alpha=.3); plt.legend(fontsize=8)
plt.title("Erasure code across hops: protection vs overhead"); plt.savefig("figures/11_erasure_tradeoff.png", dpi=130); plt.close()
# Monte Carlo cross-check of one point
n, k, p = 7, 4, pl(3); mc = np.mean([(rng.random(n) > p).sum() >= k for _ in range(100000)])
res["mc_check"] = dict(analytic=pdecode(n, k, p), mc=float(mc)); res["erasure"] = rows
print("mc check (7,4), 3 jammed:", pdecode(n, k, p), mc)
for r in rows:
    if r["jammed_channels"] == 3: print(r["n"], r["k"], round(r["rate"], 2), round(r["block_success"], 4), round(r["goodput"], 3))
json.dump(res, open("figures/fec_results.json", "w"), indent=1)
print({k: [round(x, 5) for x in res[k]] for k in ("unc", "ham", "conv")})
