"""Interference classifier from what the link can actually observe: per-slot (our channel, ok, rssi). No jammer knowledge.
Classes: none, static, sweep, random, reactive (a jammer that has learned our hop schedule).
Features (window of W slots): loss rate, share of losses on the top-2 channels, fraction of loss-to-loss channel steps equal to +1,
channel entropy of losses, mean RSSI excess on losses, lag-1 repeat rate of lost channels."""
import numpy as np
from schedule import lfsr_schedule
from attack import LfsrBreaker
from adaptive import Jammer
CLASSES = ["none", "static", "sweep", "random", "reactive"]


def features(chs, oks, rssi, M, slots=None):
    chs, oks, rssi = map(np.asarray, (chs, oks, rssi)); lost = ~oks.astype(bool)
    slots = np.arange(len(chs)) if slots is None else np.asarray(slots)
    n = lost.sum(); rate = n / len(oks)
    if n < 3: return np.array([rate, 0, 0, 0, 0, 0.0, 0.0])
    lc = chs[lost]; cnt = np.bincount(lc, minlength=M)
    top2 = np.sort(cnt)[-2:].sum() / n
    steps = ((lc[1:] - lc[:-1]) % M == 1).mean()
    p = cnt[cnt > 0] / n; ent = -(p * np.log2(p)).sum() / np.log2(M)
    exc = (rssi[lost].mean() - rssi[~lost].mean()) / 10 if (~lost).any() else 0
    rep = (lc[1:] == lc[:-1]).mean()
    ph = np.bincount((lc - slots[lost]) % M, minlength=M).max() / n   # sweep: channel minus time is constant
    return np.array([rate, top2, steps, ent, exc, rep, ph])


def sim_window(cls, M=13, W=150, seed=0, p_jam=0.95, p_clean=0.01, duty=1.0):
    rng = np.random.default_rng(seed)
    if cls == "reactive":
        sched = lfsr_schedule(W + 40, M, key=int(rng.integers(1, 65535))); att = LfsrBreaker(M)
        for t in range(40): att.observe(int(sched[t]))   # jammer already locked in; we observe a steady-state window
        sched = sched[40:]
        jamf = lambda t, c: att.predict(rng) == c
    else:
        sched = rng.integers(0, M, W)
        jam = Jammer({"none": "none", "static": "static", "sweep": "sweep", "random": "random"}[cls], M, rng, k=int(rng.integers(1, 4)))
        jamf = lambda t, c: c in jam.jammed()
    chs, oks, rs = [], [], []
    for t in range(W):
        c = int(sched[t]); j = (cls != "none") and jamf(t, c) and rng.random() < duty   # duty < 1: evasive on/off jamming
        ok = rng.random() > (p_jam if j else p_clean)
        chs.append(c); oks.append(ok); rs.append(-62 + rng.normal(0, 2) + (14 if j else 0))
        if cls == "reactive": att.observe(c)
        elif cls != "none": jam.observe(c)
    return features(chs, oks, rs, M)


def rule(f):
    rate, top2, steps, ent, exc, rep, ph = f
    if rate < 0.04: return "none"
    if ph > 0.8: return "sweep"
    if top2 > 0.7: return "static"
    if rate > 0.5: return "reactive"
    return "random"


def softmax_train(X, y, k, iters=3000, lr=0.5):
    mu, sd = X.mean(0), X.std(0) + 1e-9; Xs = (X - mu) / sd
    Xb = np.c_[Xs, np.ones(len(Xs))]; W = np.zeros((Xb.shape[1], k)); Y = np.eye(k)[y]
    for _ in range(iters):
        Z = Xb @ W; Z -= Z.max(1, keepdims=True); P = np.exp(Z); P /= P.sum(1, keepdims=True)
        W -= lr * Xb.T @ (P - Y) / len(Xb) + 1e-4 * W
    return mu, sd, W


def softmax_predict(model, X):
    mu, sd, W = model; return ((np.c_[(X - mu) / sd, np.ones(len(X))]) @ W).argmax(1)


if __name__ == "__main__":
    import json
    def make(n, off):
        X, y = [], []
        for i in range(n):
            for ci, c in enumerate(CLASSES): X.append(sim_window(c, seed=off + i * 7 + ci)); y.append(ci)
        return np.array(X), np.array(y)
    Xtr, ytr = make(150, 0); Xte, yte = make(100, 10**6)
    model = softmax_train(Xtr, ytr, len(CLASSES))
    out = {}
    for name, pred in (("rule-based", np.array([CLASSES.index(rule(f)) for f in Xte])), ("softmax", softmax_predict(model, Xte))):
        cm = np.zeros((5, 5), int)
        for a, b in zip(yte, pred): cm[a, b] += 1
        acc = float((pred == yte).mean()); out[name] = dict(accuracy=acc, confusion=cm.tolist())
        print(name, "accuracy", round(acc, 3)); print("rows=true, cols=pred", CLASSES); print(cm)
    json.dump(out, open("figures/classifier_results.json", "w"), indent=1)
