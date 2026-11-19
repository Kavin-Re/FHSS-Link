"""R2 (RED_TEAM idea 4) Learning-rate attack. A jammer relocates its 3-channel jam set to fresh channels every L slots. A discounted Thompson learner
(memory N = 1/(1-gamma) slots) is always partly stale. Sweep L for several gamma; then test a 'switch-detect' learner that shrinks its counts
when its own surprise (observed loss minus predicted loss on the chosen channel) stays high. Own-link simulation; the jammer is oblivious
to the learner's choices (it only knows the learner's memory length, the attacker's best-case assumption for this test)."""
import numpy as np
from _common import *

def run(L, gamma, detect=False, T=6000, seed=0, M=M_DEF, k=3, uniform=False):
    rng = np.random.default_rng(seed); a = np.ones(M); b = np.ones(M); S = rng.permutation(M)[:k]; oks = []; sur = 0.0; cool = 0
    for t in range(T):
        if t and t % L == 0: S = rng.permutation(M)[:k]
        c = int(rng.integers(M)) if uniform else int(np.argmax(rng.beta(a, b)))
        ok = rng.random() > (P_JAM if c in S else P_CLEAN); oks.append(ok)
        if uniform: continue
        if gamma < 1: a = 1 + gamma * (a - 1); b = 1 + gamma * (b - 1)
        pred_fail = b[c] / (a[c] + b[c]); sur = 0.9 * sur + 0.1 * ((not ok) - pred_fail)
        if ok: a[c] += 1
        else: b[c] += 1
        cool -= 1
        if detect and sur > 0.25 and cool <= 0:        # surprise: many unexpected losses -> the world changed, forget fast
            a = 1 + (a - 1) / 8; b = 1 + (b - 1) / 8; sur = 0.0; cool = 15
    return float(np.mean(oks))

LS = [10, 20, 50, 100, 200, 500, 1000, 6000]
CFG = {"uniform (no memory)": dict(gamma=1.0, uniform=True), "gamma=0.90 (N=10)": dict(gamma=0.90), "gamma=0.98 (N=50)": dict(gamma=0.98),
       "gamma=0.995 (N=200)": dict(gamma=0.995), "gamma=1.0 (no forgetting)": dict(gamma=1.0), "gamma=1.0 + switch-detect": dict(gamma=1.0, detect=True),
       "gamma=0.98 + switch-detect": dict(gamma=0.98, detect=True)}

def sweep(seeds=range(4), Ls=LS, T=6000):
    return {n: [float(np.mean([run(L, T=T, seed=s, **c) for s in seeds])) for L in Ls] for n, c in CFG.items()}

def main():
    res = sweep()
    print(f"{'L (slots)':28s}" + "".join(f"{L:>7d}" for L in LS))
    for n, v in res.items(): print(f"{n:28s}" + "".join(f"{x:7.3f}" for x in v))
    fig, ax = plt.subplots(figsize=(6.6, 3.6)); cols = [C["grey"], C["sky"], C["blue"], C["green"], C["verm"], C["orange"], C["pink"]]
    for (n, v), col in zip(res.items(), cols): ax.plot(LS, v, "o-" if "detect" not in n else "s--", color=col, label=n, ms=3.5)
    ax.set_xscale("log"); ax.set_xlabel("jammer relocation period L (slots)"); ax.set_ylabel("delivery"); ax.legend(fontsize=6.5, ncol=2)
    ax.set_title("R2 learning-rate attack: delivery vs relocation period"); save_fig(fig, "r2_learning_rate.png"); save_json("r2_learning_rate.json", dict(L=LS, delivery=res))
    worst = {n: (LS[int(np.argmin(v))], min(v)) for n, v in res.items()}
    key("worst delivery of 'gamma=0.98' over L (L*, value) vs uniform", f"{worst['gamma=0.98 (N=50)']} vs {np.mean(res['uniform (no memory)']):.3f}")
    return res
if __name__ == "__main__": main()
