"""Idea 15: locate an interferer on our own test link from RSSI at K boards (fox hunting).
Model: RSSI_i = P0 - 10 n log10(d_i / 1 m) + shadowing N(0, sigma). Unknown: (x, y) and P0 (profiled out analytically). Path-loss exponent n known (2.5 indoor-ish)
or mismatched (true n differs from assumed). Grid search over a 20 m x 20 m area."""
import numpy as np

def locate(anchors, rssi, n_assumed=2.5, size=20.0, step=0.25):
    xs = np.arange(0, size + step, step); X, Y = np.meshgrid(xs, xs)
    D = np.sqrt((X[..., None] - anchors[:, 0]) ** 2 + (Y[..., None] - anchors[:, 1]) ** 2).clip(0.3)
    model = -10 * n_assumed * np.log10(D)                  # P0 removed below
    resid = rssi - model; P0 = resid.mean(-1, keepdims=True); cost = ((resid - P0) ** 2).sum(-1)
    i = np.unravel_index(cost.argmin(), cost.shape); return np.array([X[i], Y[i]])

def mc(K=3, sigma=3.0, n_true=2.5, n_assumed=2.5, trials=300, seed=0, size=20.0):
    rng = np.random.default_rng(seed)
    base = np.array([[2, 2], [18, 3], [10, 18], [3, 16], [17, 16], [10, 1]], float)[:K]
    err = []
    for _ in range(trials):
        p = rng.uniform(1, size - 1, 2); d = np.linalg.norm(base - p, axis=1).clip(0.3)
        r = -20 - 10 * n_true * np.log10(d) + rng.normal(0, sigma, K)
        err.append(np.linalg.norm(locate(base, r, n_assumed, size) - p))
    err = np.array(err); return float(np.median(err)), float(np.percentile(err, 90))

if __name__ == "__main__":
    import json; res = {}
    print("median / 90th-percentile position error in metres (20 m x 20 m room, 300 trials)")
    for K in (3, 4, 6):
        for sg in (0, 2, 4, 6):
            m, p = mc(K=K, sigma=sg, trials=200); res[f"K{K}_sigma{sg}"] = dict(median=m, p90=p); print(f"K={K} shadowing {sg} dB: {m:.2f} / {p:.2f} m")
    for na in (2.0, 3.0, 3.5):
        m, p = mc(K=4, sigma=3, n_true=2.5, n_assumed=na, trials=200); res[f"K4_nmismatch{na}"] = dict(median=m, p90=p); print(f"K=4, sigma 3 dB, assumed n={na} (true 2.5): {m:.2f} / {p:.2f} m")
    json.dump(res, open("figures/locate.json", "w"), indent=1)
