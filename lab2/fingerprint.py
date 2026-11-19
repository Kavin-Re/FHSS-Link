"""Module 3 - transmitter fingerprinting by clock skew + timing jitter.

Model / assumptions
- 6 nodes send a packet every T=100 ms on the (keyed) hop schedule; the receiver records arrival time minus nominal
  slot time. Arrival deviation x_k = skew_i * (k T) + o_i + jitter_k, jitter ~ N(0, sigma_i^2), independent per packet.
  Skew in ppm (crystal), jitter sigma in microseconds. The receiver's own clock skew is common to all nodes and is
  absorbed in the enrolled skew values (so it cancels in the comparison).
- Per observation window of n packets: skew estimate = least-squares slope of x_k vs kT, jitter estimate = residual std.
- Enrollment: 5000 packets per node (8 min) -> stored (skew, jitter) model per node, including enrollment error.
- Temperature: each test window sees the node's skew shifted by N(0, 0.3 ppm) relative to enrollment.
- Decision: claimed node j is accepted if the normalised distance d2 = (s_hat-s_j)^2/var_s + (sig_hat-sig_j)^2/var_sig
  is below a threshold; var_s = 12 sig_j^2/(T^2 n (n^2-1)) + 0.3ppm^2, var_sig = sig_j^2/(2(n-2)).
  The threshold is calibrated on one set of genuine windows to the target false-alarm rate and the rates are
  then measured on an independent set. Identification = nearest node by d2.
- Impostor: holds the correct key (passes MAC and follows the schedule), but has its own crystal. Three types:
  'random' skew U(-20,20) ppm, jitter U(4,16) us, claims a random node; 'near' skew within +-1 ppm and jitter within
  +-20% of the claimed node (a skilled attacker who tuned his clock); 'clone' exactly equal clock parameters (shows
  the method's blind spot: detection = false-alarm rate).
- Caveats: Gaussian jitter (real MAC/OS jitter has heavy tails and bursts), no clock steps, no mid-session skew
  jumps, hardware timestamping assumed (software timestamps would add ms-level jitter).
"""
import os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "figures")
T = 0.1
SKEW = np.array([2.0, 3.5, -1.0, 8.0, -6.5, 11.0]) * 1e-6
SIG = np.array([6.0, 9.0, 12.0, 7.0, 10.0, 15.0]) * 1e-6
SIG_TEMP = 0.3e-6


def window_stats(skew, sig, n, rng, chunk=500):
    """skew, sig: arrays (m,). Returns (skew_hat, sig_hat) from n-packet windows with fresh jitter."""
    skew = np.asarray(skew, float); sig = np.asarray(sig, float); m = len(skew)
    k = np.arange(n) * T; kc = k - k.mean(); sk = np.sum(kc ** 2)
    sh = np.zeros(m); gh = np.zeros(m)
    for a in range(0, m, chunk):
        b = min(m, a + chunk)
        x = skew[a:b, None] * k[None, :] + sig[a:b, None] * rng.normal(size=(b - a, n))
        sl = (x @ kc) / sk
        icp = x.mean(axis=1) - sl * k.mean()
        res = x - sl[:, None] * k[None, :] - icp[:, None]
        sh[a:b] = sl
        gh[a:b] = np.sqrt(np.sum(res ** 2, axis=1) / (n - 2))
    return sh, gh


def enroll(rng, n_enr=5000):
    s, g = window_stats(SKEW, SIG, n_enr, rng)
    return s, g


def d2(sh, gh, ms, mg, n):
    vs = 12 * mg ** 2 / (T ** 2 * n * (n ** 2 - 1)) + SIG_TEMP ** 2
    vg = mg ** 2 / (2.0 * (n - 2))
    return (sh - ms) ** 2 / vs + (gh - mg) ** 2 / vg


def genuine(nodes, n, rng):
    sk = SKEW[nodes] + SIG_TEMP * rng.normal(size=len(nodes))
    return window_stats(sk, SIG[nodes], n, rng)


def impostor(kind, claimed, n, rng):
    m = len(claimed)
    if kind == "random":
        s = rng.uniform(-20e-6, 20e-6, m); g = rng.uniform(4e-6, 16e-6, m)
    elif kind == "near":
        s = SKEW[claimed] + rng.uniform(-1e-6, 1e-6, m); g = SIG[claimed] * rng.uniform(0.8, 1.2, m)
    else:
        s = SKEW[claimed].copy(); g = SIG[claimed].copy()
    s = s + SIG_TEMP * rng.normal(size=m)  # same temperature wander as anyone
    return window_stats(s, g, n, rng)


def thresholds(d_gen, fas):
    return {fa: float(np.quantile(d_gen, 1 - fa)) for fa in fas}


def main():
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from _budget import step
    ns = [20, 50, 100, 200, 500, 1000, 2000]
    FAS = [0.001, 0.01, 0.05]
    M = 3600

    def s_enr():
        rng = np.random.default_rng(10)
        ms, mg = enroll(rng)
        print("== enrollment (5000 packets/node) ==")
        for i in range(6):
            print(f"node {i}: true skew {SKEW[i]*1e6:6.2f} ppm jitter {SIG[i]*1e6:5.1f} us | enrolled {ms[i]*1e6:6.2f} ppm {mg[i]*1e6:5.2f} us")
        return ms, mg
    ms, mg = step("fp", "enr", s_enr)

    def s_id():
        print("\n== node identification accuracy (nearest model, 6 nodes, 600 windows/node) ==")
        print("n packets (time) | accuracy | worst-node accuracy | most common confusion")
        acc = {}
        for n in ns:
            rng = np.random.default_rng(20 + n)
            nodes = np.repeat(np.arange(6), 600)
            sh, gh = genuine(nodes, n, rng)
            D = np.stack([d2(sh, gh, ms[j], mg[j], n) for j in range(6)], axis=1)
            pred = D.argmin(axis=1)
            per = [float(np.mean(pred[nodes == i] == i)) for i in range(6)]
            conf = np.zeros((6, 6), int)
            for a, b in zip(nodes, pred): conf[a, b] += 1
            np.fill_diagonal(conf, 0); i, j = np.unravel_index(conf.argmax(), conf.shape)
            acc[n] = (float(np.mean(pred == nodes)), min(per))
            print(f"{n:5d} ({n*T:6.0f} s) | {acc[n][0]:.3f} | {acc[n][1]:.3f} | node {i} read as {j}: {conf[i, j]/600:.3f}")
        return acc
    acc = step("fp", "id", s_id)

    def s_det():
        print("\n== impostor detection (claimed node must match enrolled clock); FA = genuine rejected ==")
        print(f"{'n':>5s} | {'FA target':>9s} | measured FA | detect random | detect near(+-1ppm,+-20%) | detect clone")
        res = {}
        for n in ns:
            rngA = np.random.default_rng(100 + n); rngB = np.random.default_rng(200 + n)
            nodesA = rngA.integers(0, 6, M); nodesB = rngB.integers(0, 6, M)
            sh, gh = genuine(nodesA, n, rngA); dA = d2(sh, gh, ms[nodesA], mg[nodesA], n)
            th = thresholds(dA, FAS)
            sh, gh = genuine(nodesB, n, rngB); dB = d2(sh, gh, ms[nodesB], mg[nodesB], n)
            dets = {}
            for kind in ("random", "near", "clone"):
                cl = rngB.integers(0, 6, M); sh, gh = impostor(kind, cl, n, rngB)
                dets[kind] = d2(sh, gh, ms[cl], mg[cl], n)
            for fa in FAS:
                fam = float(np.mean(dB > th[fa]))
                r = [float(np.mean(dets[k] > th[fa])) for k in ("random", "near", "clone")]
                res[(n, fa)] = (fam, *r)
                print(f"{n:5d} | {fa:9.3f} | {fam:11.4f} | {r[0]:13.3f} | {r[1]:25.3f} | {r[2]:.3f}")
            res[(n, "dets")] = None
        return res
    res = step("fp", "det", s_det)

    def s_roc():
        print("\n== ROC points at n=200 and n=1000 (random impostor): FA -> detection ==")
        out = {}
        for n in (200, 1000):
            rng = np.random.default_rng(300 + n)
            nodes = rng.integers(0, 6, 6000)
            sh, gh = genuine(nodes, n, rng); dg = d2(sh, gh, ms[nodes], mg[nodes], n)
            cl = rng.integers(0, 6, 6000); sh, gh = impostor("random", cl, n, rng); di = d2(sh, gh, ms[cl], mg[cl], n)
            qs = np.quantile(dg, np.linspace(0, 1, 200))
            fa = np.array([np.mean(dg > t) for t in qs]); dt = np.array([np.mean(di > t) for t in qs])
            out[n] = (fa, dt)
            for f in (0.001, 0.01, 0.1):
                idx = np.argmin(abs(fa - f)); print(f"n={n}: FA {fa[idx]:.4f} -> detection {dt[idx]:.3f}")
        return out
    roc = step("fp", "roc", s_roc)

    def s_fig():
        fig, ax = plt.subplots(1, 3, figsize=(14, 4))
        ax[0].semilogx(ns, [acc[n][0] for n in ns], "o-", label="mean"); ax[0].semilogx(ns, [acc[n][1] for n in ns], "s--", label="worst node")
        ax[0].set_xlabel("packets observed n (100 ms apart)"); ax[0].set_ylabel("identification accuracy"); ax[0].legend(); ax[0].grid(alpha=.3)
        ax[0].set_title("who is talking? (6 nodes)")
        for kind, c, i in (("random", "#1e8449", 1), ("near", "#e67e22", 2), ("clone", "#c0392b", 3)):
            ax[1].semilogx(ns, [res[(n, 0.01)][i] for n in ns], "o-", c=c, label=kind)
        ax[1].axhline(0.01, c="gray", ls=":"); ax[1].set_xlabel("packets observed n"); ax[1].set_ylabel("detection rate at FA=1%")
        ax[1].legend(); ax[1].grid(alpha=.3); ax[1].set_title("impostor with correct key")
        for n, (fa, dt) in roc.items(): ax[2].semilogx(np.maximum(fa, 1e-4), dt, label=f"n={n}")
        ax[2].set_xlabel("false alarm rate"); ax[2].set_ylabel("detection (random impostor)"); ax[2].legend(); ax[2].grid(alpha=.3); ax[2].set_title("ROC")
        plt.tight_layout(); plt.savefig(os.path.join(FIG, "fingerprint.png"), dpi=110); print("saved figures/fingerprint.png")
    step("fp", "fig", s_fig)


if __name__ == "__main__":
    main()
