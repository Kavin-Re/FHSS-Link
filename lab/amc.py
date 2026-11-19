"""Automatic modulation classification (numpy only): OOK, BPSK, QPSK, BFSK, DS-SS BPSK.

Model / assumptions
-------------------
* Complex baseband frames of 1024 samples. Rectangular pulses, 8 samples/symbol for OOK, BPSK, QPSK;
  BFSK: tones at +-fs/16 (h = 1) with 8 samples/symbol, continuous phase;
  DS-SS BPSK: 14-sample data bit spread by the 7-chip m-sequence (1110100) at 2 samples/chip,
  so it occupies about 4x the bandwidth of plain BPSK.
* Channel: random carrier phase, random small carrier-frequency offset (+-0.003 cycles/sample),
  AWGN. SNR = mean signal power / noise variance per complex sample (wideband, so spreading
  does not "buy" SNR here). Random symbol timing offset (0..7 samples) and random data.
* Features (log10 for the ratios): amplitude coefficient of variation, kurtosis of |x|,
  2nd-power and 4th-power spectral peak-to-mean ratios (|FFT(x^2)|, |FFT(x^4)|), instantaneous
  frequency std (angle(x[n+1] conj x[n])), spectral flatness of |FFT(x)|^2, spectral peak-to-mean
  ratio, and ratio of the 2nd to 1st spectral peak (peaks >= 4 bins apart; large for BFSK).
* Classifiers written here: softmax regression (batch gradient descent, L2) and nearest centroid.
  Trained on pooled SNRs -5..20 dB (300 frames per class per SNR), tested on freshly generated
  frames with a different seed (200 per class per SNR).
"""
import numpy as np

CLASSES = ["OOK", "BPSK", "QPSK", "BFSK", "DSSS-BPSK"]
L = 1024
SPS = 8
MSEQ = np.array([1, 1, 1, -1, 1, -1, -1], float)


def gen(cls, snr_db, rng):
    if cls == "OOK":
        s = np.repeat(rng.integers(0, 2, L // SPS + 2), SPS) * np.sqrt(2.0)
        x = s.astype(complex)
    elif cls == "BPSK":
        x = np.repeat(rng.choice([-1.0, 1.0], L // SPS + 2), SPS).astype(complex)
    elif cls == "QPSK":
        x = np.repeat((rng.choice([-1, 1], L // SPS + 2) + 1j * rng.choice([-1, 1], L // SPS + 2)) / np.sqrt(2), SPS)
    elif cls == "BFSK":
        f = np.repeat(rng.choice([-1.0, 1.0], L // SPS + 2), SPS) / 16.0
        x = np.exp(2j * np.pi * np.cumsum(f))
    else:
        nb = L // 14 + 2
        x = np.repeat(np.repeat(rng.choice([-1.0, 1.0], nb), 7) * np.tile(MSEQ, nb), 2).astype(complex)
    off = rng.integers(0, 8)
    x = x[off:off + L]
    n = np.arange(L)
    x = x * np.exp(1j * (rng.uniform(0, 2 * np.pi) + 2 * np.pi * rng.uniform(-0.003, 0.003) * n))
    x = x / np.sqrt(np.mean(np.abs(x) ** 2))
    sigma = np.sqrt(10 ** (-snr_db / 10) / 2)
    return x + sigma * (rng.standard_normal(L) + 1j * rng.standard_normal(L))


def _peakratio(v):
    p = np.abs(np.fft.fft(v)) ** 2
    return p.max() / p.mean()


def features(x):
    a = np.abs(x)
    cv = a.std() / a.mean()
    kurt = np.mean((a - a.mean()) ** 4) / a.var() ** 2
    sp2 = _peakratio(x ** 2)
    sp4 = _peakratio(x ** 4)
    d = np.angle(x[1:] * np.conj(x[:-1]))
    ifstd = d.std()
    P = np.abs(np.fft.fft(x)) ** 2
    flat = np.exp(np.mean(np.log(P + 1e-12))) / P.mean()
    spk = P.max() / P.mean()
    i = int(np.argmax(P)); Pm = P.copy()
    for k in range(-4, 5): Pm[(i + k) % L] = 0
    r2 = Pm.max() / P.max()
    return np.array([cv, kurt, np.log10(sp2), np.log10(sp4), ifstd, np.log10(flat), np.log10(spk), r2])


FEAT_NAMES = ["amp CV", "kurt|x|", "log SP2", "log SP4", "IF std", "log flat", "log specpeak", "peak2/peak1"]


def dataset(snrs, per, seed):
    rng = np.random.default_rng(seed)
    X, y, s = [], [], []
    for sn in snrs:
        for c, name in enumerate(CLASSES):
            for _ in range(per):
                X.append(features(gen(name, sn, rng))); y.append(c); s.append(sn)
    return np.array(X), np.array(y), np.array(s)


class Softmax:
    def __init__(self, lr=0.5, it=3000, l2=1e-3):
        self.lr, self.it, self.l2 = lr, it, l2

    def fit(self, X, y, k):
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-9
        Z = np.hstack([(X - self.mu) / self.sd, np.ones((len(X), 1))])
        W = np.zeros((Z.shape[1], k)); Y = np.eye(k)[y]
        for _ in range(self.it):
            Pz = Z @ W; Pz -= Pz.max(1, keepdims=True); P = np.exp(Pz); P /= P.sum(1, keepdims=True)
            W -= self.lr * (Z.T @ (P - Y) / len(Z) + self.l2 * W)
        self.W = W
        return self

    def predict(self, X):
        Z = np.hstack([(X - self.mu) / self.sd, np.ones((len(X), 1))])
        return np.argmax(Z @ self.W, 1)


class Centroid:
    def fit(self, X, y, k):
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-9
        Z = (X - self.mu) / self.sd
        self.C = np.stack([Z[y == i].mean(0) for i in range(k)])
        return self

    def predict(self, X):
        Z = (X - self.mu) / self.sd
        return np.argmin(((Z[:, None, :] - self.C[None]) ** 2).sum(2), 1)


def confusion(y, p, k=5):
    M = np.zeros((k, k), int)
    for a, b in zip(y, p): M[a, b] += 1
    return M


def main():
    Xtr, ytr, _ = dataset([-5, 0, 5, 10, 15, 20], 300, seed=1)
    sm = Softmax().fit(Xtr, ytr, 5)
    nc = Centroid().fit(Xtr, ytr, 5)
    print("train accuracy (pooled): softmax %.3f, centroid %.3f" % (np.mean(sm.predict(Xtr) == ytr), np.mean(nc.predict(Xtr) == ytr)))
    sweep = [-10, -5, 0, 5, 10, 15, 20]
    Xte, yte, ste = dataset(sweep, 200, seed=999)
    acc_s, acc_c = [], []
    for sn in sweep:
        m = ste == sn
        acc_s.append(np.mean(sm.predict(Xte[m]) == yte[m])); acc_c.append(np.mean(nc.predict(Xte[m]) == yte[m]))
    print("test accuracy vs SNR (200 frames/class, fresh seed), softmax | centroid:")
    for sn, a, b in zip(sweep, acc_s, acc_c): print(f"  {sn:+3d} dB: {a:.3f} | {b:.3f}")
    cms = {}
    for sn in (-5, 0, 5, 10, 15):
        m = ste == sn
        cm = confusion(yte[m], sm.predict(Xte[m])); cms[sn] = cm
        print(f"\nconfusion matrix (softmax), SNR {sn} dB, rows = true, cols = predicted, counts of 200:")
        print("            " + " ".join(f"{c[:6]:>7s}" for c in CLASSES))
        for i, c in enumerate(CLASSES): print(f"  {c:9s} " + " ".join(f"{v:7d}" for v in cm[i]))
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(15, 8))
    ax = fig.add_subplot(2, 3, 1)
    ax.plot(sweep, acc_s, 'o-', label="softmax"); ax.plot(sweep, acc_c, 's--', label="nearest centroid")
    ax.set(title="accuracy vs SNR", xlabel="SNR (dB)", ylabel="accuracy", ylim=(0, 1.02)); ax.grid(alpha=.3); ax.legend()
    for k, sn in enumerate((0, 5, 10, 15)):
        a = fig.add_subplot(2, 3, [2, 3, 5, 6][k]); cm = cms[sn] / cms[sn].sum(1, keepdims=True)
        a.imshow(cm, vmin=0, vmax=1, cmap="Blues"); a.set_title(f"confusion, {sn} dB")
        a.set_xticks(range(5)); a.set_xticklabels(CLASSES, fontsize=7, rotation=30); a.set_yticks(range(5)); a.set_yticklabels(CLASSES, fontsize=7)
        for i in range(5):
            for j in range(5): a.text(j, i, f"{cm[i, j]:.2f}", ha="center", va="center", fontsize=7, color="w" if cm[i, j] > .5 else "k")
    fig.tight_layout(); fig.savefig("figures/amc.png", dpi=100)
    print("saved figures/amc.png")


if __name__ == "__main__":
    main()
