"""Beyond #16: traffic analysis of an encrypted, hopping link (simulation only, synthetic traffic).
Payload and channel are hidden, but an observer who can see THAT a burst happened and how long it was (energy-on-air per slot) learns the mission state.
Hidden state Y in {idle, patrol, alert, command} (equiprobable). Per 20-slot window the observer sees: number of bursts n and total airtime (slots) a.
Each class has its own burst rate and burst-length distribution (assumed numbers, below). We estimate I(Y; (n,a)) in bits (max 2) with a plug-in
estimator + Miller-Madow correction on 40,000 windows per class.
Defences: (1) pad every burst to a fixed length; (2) constant-rate cover traffic with budget T: the observer sees max(real, T) airtime in the window
(deterministic once T exceeds the busiest class); (3) both. Cost = extra airtime / real airtime."""
import numpy as np
from _common import *

W = 20  # slots per observation window
CLASSES = {  # name: (burst rate per window, mean burst length in slots)
    "idle": (0.4, 1.0), "patrol": (2.0, 1.5), "alert": (4.0, 2.5), "command": (1.0, 4.0)}
LMAX = 6

def sample_window(cls, rng, nwin):
    lam, ml = CLASSES[cls]
    n = rng.poisson(lam, nwin)
    lens = []                      # airtime per window = sum of burst lengths (geometric-ish, mean ml, truncated to [1, LMAX])
    p = 1.0 / ml
    a = np.zeros(nwin, dtype=int)
    for i in range(nwin):
        if n[i]: a[i] = int(np.minimum(rng.geometric(p, n[i]), LMAX).sum())
    return n, a

def mi_plugin(xs, ys, correct=True):
    """I(Y;X) in bits for discrete X (pairs encoded) and Y; Miller-Madow bias correction optional."""
    N = len(ys); ycls = np.unique(ys)
    xk = {}; xi = np.array([xk.setdefault(x, len(xk)) for x in xs])
    joint = np.zeros((len(xk), len(ycls)))
    for x, y in zip(xi, np.searchsorted(ycls, ys)): joint[x, y] += 1
    pj = joint / N; px = pj.sum(1, keepdims=True); py = pj.sum(0, keepdims=True)
    nz = pj > 0
    mi = float((pj[nz] * np.log2(pj[nz] / (px @ py)[nz])).sum())
    if correct:
        mi -= (np.count_nonzero(joint) - np.count_nonzero(px) - np.count_nonzero(py) + 1) / (2 * N * np.log(2))
    return max(mi, 0.0)

def observe(n, a, pad, T):
    """Observer features (n_bursts_visible, airtime) after the defences. pad: pad each burst to LMAX. T: constant-rate budget in slots of airtime per window (0 = off)."""
    n = n.copy(); a = a.copy()
    if pad: a = n * LMAX
    real = a.copy()
    if T > 0:
        a_obs = np.maximum(a, T); n_obs = np.where(a > T, n, np.ceil(T / (LMAX if pad else 1)).astype(int))
        # deterministic filler once the budget exceeds real traffic: observer cannot tell filler from payload
        if not pad: n_obs = np.where(a > T, n, 0)
        return n_obs, a_obs, real
    return n, a, real

def run(fast=False, seed=4):
    rng = np.random.default_rng(seed)
    nwin = 8000 if fast else 40000
    data = {c: sample_window(c, rng, nwin) for c in CLASSES}
    ys = np.concatenate([[i] * nwin for i, c in enumerate(CLASSES)])
    n_all = np.concatenate([data[c][0] for c in CLASSES]); a_all = np.concatenate([data[c][1] for c in CLASSES])
    out = {"classes": list(CLASSES), "points": []}
    def point(name, pad, T):
        n_o, a_o, real = observe(n_all, a_all, pad, T)
        mi = mi_plugin(list(zip(n_o.tolist(), a_o.tolist())), ys)
        cost = float((a_o.sum() - real.sum()) / real.sum()) if T > 0 else float((a_o.sum() - a_all.sum()) / a_all.sum())
        out["points"].append(dict(name=name, pad=pad, T=T, mi=mi, cost=cost))
    point("none", False, 0)
    point("pad bursts", True, 0)
    for T in (4, 8, 12, 16, 20, 28, 40):
        point(f"cover T={T}", False, T)
    for T in (24, 36, 48, 72):
        point(f"pad+cover T={T}", True, T)
    # only-count view and only-airtime view of the undefended link
    out["mi_count_only"] = mi_plugin(n_all.tolist(), ys); out["mi_air_only"] = mi_plugin(a_all.tolist(), ys)
    # permutation-test floor (bias check): shuffle labels
    out["mi_shuffled"] = mi_plugin(list(zip(n_all.tolist(), a_all.tolist())), rng.permutation(ys))
    return out

def main():
    out = run()
    print(f"undefended: I(Y; n, airtime) = {out['points'][0]['mi']:.3f} bits of 2.000 (count only {out['mi_count_only']:.3f}, airtime only {out['mi_air_only']:.3f}); shuffled-label floor {out['mi_shuffled']:.4f}")
    for p in out["points"]: print(f"  {p['name']:18s} MI {p['mi']:.3f} bits  extra airtime {p['cost']*100:7.1f} %")
    fig, ax = plt.subplots(figsize=(6.2, 3.8))
    for kind, col, mk in (("cover", C["blue"], "o"), ("pad+cover", C["green"], "s")):
        pts = [p for p in out["points"] if p["name"].startswith(kind + " ")]
        ax.plot([p["cost"] * 100 for p in pts], [p["mi"] for p in pts], mk + "-", color=col, label=kind)
    for p in out["points"][:2]: ax.plot(p["cost"] * 100, p["mi"], "D", color=C["verm"], ms=8); ax.annotate(p["name"], (p["cost"] * 100, p["mi"]), textcoords="offset points", xytext=(6, 4))
    ax.set_xscale("symlog", linthresh=10); ax.set_xlabel("extra airtime vs real traffic (%)"); ax.set_ylabel("leak I(state; observed) (bits, max 2)"); ax.legend()
    save_fig(fig, "b16_traffic.png"); save_json("b16_traffic.json", out)
    base = out["points"][0]; pad = out["points"][1]
    best = min((p for p in out["points"] if p["mi"] < 0.05), key=lambda p: p["cost"], default=None)
    key("B16", f"undefended leak {base['mi']:.2f} of 2 bits; padding alone {pad['mi']:.2f} bits (cost {pad['cost']*100:.0f}%); first config under 0.05 bit: {best['name'] if best else 'none'} at {best['cost']*100 if best else float('nan'):.0f}% extra airtime")
if __name__ == "__main__":
    main()
