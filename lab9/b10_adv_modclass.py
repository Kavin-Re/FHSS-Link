"""B10 Adversarial perturbations against a modulation classifier (simulation, white-box, own model).
Classifier: moment features of 64 received symbols -> small MLP (numpy, analytic gradients). Classes: BPSK, QPSK, 8PSK, 16QAM at 10 dB SNR.
Perturbation: L2-bounded, relative to signal norm (eps_rel). Compare: no perturbation, random noise of equal norm, PGD, and PGD-adversarial training."""
import numpy as np
from _common import *

NSYM, SNR_DB, H = 64, 10.0, 24
def constellation(c):
    if c == 0: return np.array([1, -1], complex)
    if c == 1: return np.exp(1j * (np.pi / 4 + np.pi / 2 * np.arange(4)))
    if c == 2: return np.exp(1j * np.pi / 4 * np.arange(8))
    q = np.array([-3, -1, 1, 3]); p = (q[:, None] + 1j * q[None, :]).ravel(); return p / np.sqrt((np.abs(p) ** 2).mean())
CONS = [constellation(c) for c in range(4)]

def make_data(rng, n):
    y = rng.integers(0, 4, n); x = np.empty((n, NSYM), complex)
    for c in range(4):
        m = y == c; x[m] = CONS[c][rng.integers(0, len(CONS[c]), (m.sum(), NSYM))]
    nv = 10 ** (-SNR_DB / 10)
    x = x + np.sqrt(nv / 2) * (rng.normal(size=x.shape) + 1j * rng.normal(size=x.shape))
    return x.real.copy(), x.imag.copy(), y          # I, Q arrays (n, NSYM)

def feats(I, Q):
    r2 = I * I + Q * Q
    F = np.stack([I * I - Q * Q, I ** 4 - 6 * I * I * Q * Q + Q ** 4, r2 ** 2, r2 ** 3], 1)   # (n,4,NSYM)
    return F.mean(2)
def feat_jac_T(I, Q, gF):
    """Backprop gF (n,4) through the feature map to dI, dQ (n,NSYM)."""
    r2 = I * I + Q * Q
    dI = [2 * I, 4 * I ** 3 - 12 * I * Q * Q, 4 * I * r2, 6 * I * r2 ** 2]
    dQ = [-2 * Q, -12 * I * I * Q + 4 * Q ** 3, 4 * Q * r2, 6 * Q * r2 ** 2]
    gI = sum(gF[:, k, None] * dI[k] for k in range(4)) / NSYM
    gQ = sum(gF[:, k, None] * dQ[k] for k in range(4)) / NSYM
    return gI, gQ

class Net:
    def __init__(self, rng, mu, sd):
        self.W1 = rng.normal(0, 0.5, (4, H)); self.b1 = np.zeros(H); self.W2 = rng.normal(0, 0.5, (H, 4)); self.b2 = np.zeros(4); self.mu, self.sd = mu, sd
    def forward(self, F):
        Z = (F - self.mu) / self.sd; A = np.tanh(Z @ self.W1 + self.b1); L = A @ self.W2 + self.b2
        L = L - L.max(1, keepdims=True); P = np.exp(L); P /= P.sum(1, keepdims=True); return Z, A, P
    def predict(self, I, Q): return self.forward(feats(I, Q))[2].argmax(1)
    def grad_input(self, I, Q, y):
        """Gradient of mean-free per-sample cross-entropy w.r.t. I and Q (per sample, not averaged)."""
        F = feats(I, Q); Z, A, P = self.forward(F); G = P.copy(); G[np.arange(len(y)), y] -= 1
        gA = G @ self.W2.T; gZ = (gA * (1 - A * A)) @ self.W1.T; gF = gZ / self.sd
        loss = -np.log(P[np.arange(len(y)), y] + 1e-12); return loss, *feat_jac_T(I, Q, gF)
    def step(self, I, Q, y, lr, F=None):
        F = feats(I, Q) if F is None else F; Z, A, P = self.forward(F); n = len(y); G = P.copy(); G[np.arange(n), y] -= 1; G /= n
        gW2 = A.T @ G; gb2 = G.sum(0); gA = G @ self.W2.T; gZp = gA * (1 - A * A); gW1 = Z.T @ gZp; gb1 = gZp.sum(0)
        for p, g in ((self.W1, gW1), (self.b1, gb1), (self.W2, gW2), (self.b2, gb2)): p -= lr * g

def pgd(net, I, Q, y, eps_rel, steps=15):
    n = len(y); nrm = np.sqrt((I * I + Q * Q).sum(1)); eps = eps_rel * nrm
    dI = np.zeros_like(I); dQ = np.zeros_like(Q)
    for _ in range(steps):
        _, gI, gQ = net.grad_input(I + dI, Q + dQ, y)
        gn = np.sqrt((gI * gI + gQ * gQ).sum(1)) + 1e-12
        a = 2.5 * eps / steps
        dI += a[:, None] * gI / gn[:, None]; dQ += a[:, None] * gQ / gn[:, None]
        pn = np.sqrt((dI * dI + dQ * dQ).sum(1)); sc = np.minimum(1, eps / (pn + 1e-12))
        dI *= sc[:, None]; dQ *= sc[:, None]
    return I + dI, Q + dQ

def rand_pert(rng, I, Q, eps_rel):
    nI, nQ = rng.normal(size=I.shape), rng.normal(size=Q.shape); nn = np.sqrt((nI ** 2 + nQ ** 2).sum(1))
    eps = eps_rel * np.sqrt((I * I + Q * Q).sum(1)); return I + nI * (eps / nn)[:, None], Q + nQ * (eps / nn)[:, None]

def train(rng, I, Q, y, adv_eps=0.0, epochs=300, lr=0.3):
    F = feats(I, Q); net = Net(rng, F.mean(0), F.std(0) + 1e-9); n = len(y)
    warm = epochs if adv_eps == 0 else 150
    for ep in range(warm): net.step(None, None, y, lr, F=F)           # clean epochs on cached features
    for ep in range(epochs - warm if adv_eps > 0 else 0):           # adversarial epochs: PGD on a minibatch, train on clean+adversarial
        idx = rng.choice(n, 400, replace=False); Ia, Qa = pgd(net, I[idx], Q[idx], y[idx], adv_eps, steps=4)
        net.step(np.vstack([I[idx], Ia]), np.vstack([Q[idx], Qa]), np.concatenate([y[idx], y[idx]]), lr)
    return net

def one_seed(seed, eps_grid, ntest=400):
    rng = np.random.default_rng(seed)
    I, Q, y = make_data(rng, 1500); It, Qt, yt = make_data(rng, ntest)
    std = train(rng, I, Q, y); adv = train(rng, I, Q, y, adv_eps=0.2)
    r = {}
    for name, net in (("std", std), ("adv", adv)):
        r[name + "_clean"] = float((net.predict(It, Qt) == yt).mean())
        r[name + "_pgd"] = [float((net.predict(*pgd(net, It, Qt, yt, e, 20)) == yt).mean()) for e in eps_grid]
        r[name + "_rand"] = [float((net.predict(*rand_pert(rng, It, Qt, e)) == yt).mean()) for e in eps_grid]
    return r

def run(fast=False):
    eps = [0.0, 0.05, 0.1, 0.2, 0.3, 0.5]; ns = NSEEDS if not fast else 20
    from multiprocessing import Pool
    with Pool(2) as p: R = p.starmap(one_seed, [(s, eps) for s in range(ns)])
    A = lambda k: np.array([r[k] for r in R])
    out = dict(eps=eps, nseeds=ns, clean_std=mean_ci(A("std_clean")), clean_adv=mean_ci(A("adv_clean")))
    for k in ("std_pgd", "std_rand", "adv_pgd", "adv_rand"):
        out[k] = [mean_ci(A(k)[:, i]) for i in range(len(eps))]
    save_json("b10_adv_modclass.json", out); return out

def plot(o):
    fig, ax = plt.subplots(figsize=(5.2, 3.5))
    for k, lab, c, ls in [("std_pgd", "standard, PGD", C["verm"], "-"), ("std_rand", "standard, random noise", C["grey"], "--"),
                          ("adv_pgd", "adv-trained, PGD", C["blue"], "-"), ("adv_rand", "adv-trained, random noise", C["sky"], "--")]:
        m = o[k]; ax.errorbar(o["eps"], [x[0] for x in m], yerr=[[max(0,x[0]-x[1]) for x in m], [max(0,x[2]-x[0]) for x in m]], color=c, ls=ls, marker="o", capsize=2, label=lab)
    ax.set_xlabel("perturbation norm / signal norm"); ax.set_ylabel("accuracy"); ax.legend(); ax.set_title("Modulation classifier under L2 perturbation")
    save_fig(fig, "b10_adv_modclass.png")

if __name__ == "__main__":
    o = run(); plot(o); i = o["eps"].index(0.2)
    key("B10", f"clean acc std {fmt(o['clean_std'])}; at eps_rel=0.2 (-14 dB): PGD {fmt(o['std_pgd'][i])} vs equal-norm random {fmt(o['std_rand'][i])}; adv-trained PGD {fmt(o['adv_pgd'][i])} (clean {o['clean_adv'][0]:.3f})")
