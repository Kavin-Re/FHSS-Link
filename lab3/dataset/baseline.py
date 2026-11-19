"""Baselines for the simulated jammer-classification dataset (numpy only, no sim/ imports needed).
Reads windows.csv, trains on split=train, reports accuracy on split=test for: majority class, nearest centroid, softmax regression.
Run: python3 baseline.py [path/to/windows.csv]"""
import os, sys, csv
import numpy as np
FEATS = ["rate", "top2_loss_share", "step_plus1", "loss_entropy", "rssi_excess", "repeat_rate", "phase_peak"]
CLASSES = ["none", "static", "sweep", "random", "reactive"]


def load(path):
    rows = list(csv.DictReader(open(path))); X = np.array([[float(r[f]) for f in FEATS] for r in rows]); y = np.array([CLASSES.index(r["label"]) for r in rows])
    sp = np.array([r["split"] for r in rows]); M = np.array([int(r["M"]) for r in rows]); return X, y, sp, M


def softmax_fit(X, y, k, iters=3000, lr=0.5):
    mu, sd = X.mean(0), X.std(0) + 1e-9; Xb = np.c_[(X - mu) / sd, np.ones(len(X))]; W = np.zeros((Xb.shape[1], k)); Y = np.eye(k)[y]
    for _ in range(iters):
        Z = Xb @ W; Z -= Z.max(1, keepdims=True); P = np.exp(Z); P /= P.sum(1, keepdims=True); W -= lr * Xb.T @ (P - Y) / len(Xb) + 1e-4 * W
    return mu, sd, W


def softmax_predict(m, X): mu, sd, W = m; return (np.c_[(X - mu) / sd, np.ones(len(X))] @ W).argmax(1)


def centroid_fit(X, y, k):
    mu, sd = X.mean(0), X.std(0) + 1e-9; Xs = (X - mu) / sd; return mu, sd, np.array([Xs[y == c].mean(0) for c in range(k)])


def centroid_predict(m, X): mu, sd, C = m; Xs = (X - mu) / sd; return ((Xs[:, None, :] - C[None]) ** 2).sum(2).argmin(1)


def main(path=None):
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "windows.csv"); X, y, sp, M = load(path); tr, te = sp == "train", sp == "test"
    print(f"train {tr.sum()} windows, test {te.sum()} windows, {len(FEATS)} features, {len(CLASSES)} classes"); res = {}
    maj = np.bincount(y[tr]).argmax(); res["majority"] = float((y[te] == maj).mean())
    mc = centroid_fit(X[tr], y[tr], 5); pc = centroid_predict(mc, X[te]); res["nearest centroid"] = float((pc == y[te]).mean())
    ms = softmax_fit(X[tr], y[tr], 5); ps = softmax_predict(ms, X[te]); res["softmax"] = float((ps == y[te]).mean())
    for k, v in res.items(): print(f"test accuracy {k:17s} {v:.3f}")
    cm = np.zeros((5, 5), int)
    for a, b in zip(y[te], ps): cm[a, b] += 1
    print("softmax confusion (rows true, cols predicted)", CLASSES); print(cm)
    print("softmax per-class recall:", {c: round(float(cm[i, i] / max(cm[i].sum(), 1)), 3) for i, c in enumerate(CLASSES)})
    print("softmax accuracy by M:", {int(m): round(float((ps[M[te] == m] == y[te][M[te] == m]).mean()), 3) for m in sorted(set(M))})
    return res


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
