"""R7 (RED_TEAM idea 11) Partial-knowledge (myopic) jammer: knowledge-vs-damage curve. Own-link simulation.
Per hop dwell (normalised length 1) the jammer (a) correctly identifies the active channel with probability a, but only after a latency d (in dwell
units), and then jams the REST of the dwell; or (b) otherwise (not identified, or identified too late to matter) it jams a random channel for the whole dwell. The packet is lost with prob
P_JAM if the overlap with jamming exceeds the FEC erasure tolerance theta, else with P_CLEAN. Hopping is uniform i.i.d., so history gives no
prediction: a jammer predicting the NEXT channel from past ones is a coin flip (checked). Closed form is compared against Monte Carlo."""
import numpy as np
from _common import *

def delivery_mc(a, d, theta=0.25, M=M_DEF, N=200000, seed=0):
    rng = np.random.default_rng(seed); known = rng.random(N) < a
    guess_hit = rng.random(N) < 1.0 / M
    useful = max(0.0, 1.0 - d) > theta                      # a late detection is worthless: the jammer then falls back to a blind guess
    known = known & useful
    overlap = np.where(known, 1.0 - d, np.where(guess_hit, 1.0, 0.0))
    jam = overlap > theta
    loss = np.where(jam, rng.random(N) < P_JAM, rng.random(N) < P_CLEAN)
    return 1.0 - float(loss.mean())

def delivery_cf(a, d, theta=0.25, M=M_DEF):
    ua = a if 1.0 - d > theta else 0.0
    pj = ua + (1 - ua) * (1.0 / M)
    return 1.0 - (pj * P_JAM + (1 - pj) * P_CLEAN)

def history_predictor(M=M_DEF, N=100000, seed=0):
    rng = np.random.default_rng(seed); seq = rng.integers(M, size=N)
    # best guess for next channel from the previous 3 channels: majority of a context table (learned online)
    tab = {}; hit = 0
    for i in range(3, N):
        ctx = tuple(seq[i - 3:i]); g = max(range(M), key=lambda c: tab.get((ctx, c), 0)); hit += (g == seq[i]); tab[(ctx, seq[i])] = tab.get((ctx, seq[i]), 0) + 1
    return hit / (N - 3)

def main():
    ds = np.linspace(0, 1.4, 15); A = (0.25, 0.5, 1.0); res = {"d": ds.tolist()}
    for a in A: res[f"a={a}"] = [delivery_mc(a, d) for d in ds]
    thetas = np.linspace(0, 0.9, 10); res["theta"] = thetas.tolist(); res["theta_curve_d0.5_a1"] = [delivery_mc(1.0, 0.5, th) for th in thetas]
    hp = history_predictor(); res["history_predictor_acc"] = hp
    blind = 1 - (P_JAM / M_DEF + P_CLEAN * (1 - 1 / M_DEF)); print(f"blind 1-channel jammer delivery {blind:.3f}; perfect zero-latency follower {delivery_cf(1, 0):.3f}; history predictor accuracy {hp:.4f} (chance {1/M_DEF:.4f})")
    for a in A: print(f"a={a}: delivery at d=0, 0.5, 0.75, 1.0: " + " ".join(f"{delivery_cf(a, d):.3f}" for d in (0, 0.5, 0.75, 1.0)))
    fig, ax = plt.subplots(1, 2, figsize=(7.4, 3.3))
    for a, col in zip(A, (C["sky"], C["blue"], C["verm"])): ax[0].plot(ds, res[f"a={a}"], "o-", ms=3, color=col, label=f"detect accuracy a={a}")
    ax[0].axhline(blind, color=C["grey"], ls="--", label="blind (a=0)"); ax[0].set_xlabel("jammer latency d / dwell"); ax[0].set_ylabel("delivery"); ax[0].legend(fontsize=6.5)
    ax[1].plot(thetas, res["theta_curve_d0.5_a1"], "o-", color=C["green"]); ax[1].set_xlabel("FEC erasure tolerance theta"); ax[1].set_title("a=1, d=0.5 dwell", fontsize=8)
    fig.suptitle("R7 myopic jammer: knowledge vs damage", fontsize=9); save_fig(fig, "r7_myopic_jammer.png"); save_json("r7_myopic_jammer.json", res)
    key("delivery vs perfect-detection follower with latency 0 / 0.5 / 0.75 dwell (theta=0.25)", f"{delivery_cf(1,0):.3f} / {delivery_cf(1,0.5):.3f} / {delivery_cf(1,0.75):.3f}")
    return res
if __name__ == "__main__": main()
