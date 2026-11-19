"""Module 6 - compressed-sensing spectrum sensing with orthogonal matching pursuit (numpy only).

Model / assumptions
- Complex-baseband wideband spectrum with N=256 bins, s occupied bins (jammer tones plus our own hopping signal),
  coefficients x_k = a_k exp(j phi_k), |a_k| ~ U[1,2], phi uniform, positions uniform without replacement.
- Measurements y = Phi x + n, n ~ CN(0, sigma^2), m << N of them:
    'sample' : random sub-sampling of the unitary time-domain signal (Phi = rows of the inverse DFT, 1/sqrt(N) entries),
               i.e. a sub-Nyquist ADC at random instants;
    'gauss'  : i.i.d. complex Gaussian projections (variance 1/N per entry, same column energy on average).
- SNR is per-bin in the unitary basis: SNR = 1/sigma^2 refers to the WEAKEST possible tone (|a|=1); stronger tones have more.
- Recovery = exact support recovery. OMP with known sparsity s (s iterations); a second variant 'blind' does not know s
  and stops when the residual energy falls below 1.5 m sigma^2 (noise-based rule) with a cap of 3 s atoms.
- Columns are normalised inside OMP. Trials are independent draws of support, amplitudes, phases, Phi and noise.
- Caveats: on-grid tones only (no off-bin leakage), no occupied-bin clutter from wide emitters, noise white and known
  in level for the blind rule, 100-200 trials per point so probabilities have ~+-0.05 sampling error near 0.5.
"""
import os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "figures")
N = 256


def make_phi(kind, m, rng, N=N):
    if kind == "sample":
        t = np.sort(rng.choice(N, m, replace=False))
        F = np.exp(2j * np.pi * np.outer(t, np.arange(N)) / N) / np.sqrt(N)
        return F
    return (rng.normal(size=(m, N)) + 1j * rng.normal(size=(m, N))) / np.sqrt(2 * N)


def omp(Phi, y, s=None, sigma2=0.0, cap=None):
    m, n = Phi.shape
    nrm = np.linalg.norm(Phi, axis=0); Pn = Phi / nrm
    r = y.copy(); sel = []; coef = np.zeros(0, complex)
    steps = s if s is not None else (cap or 24)
    for _ in range(steps):
        if s is None and np.linalg.norm(r) ** 2 <= 1.5 * m * sigma2: break
        c = np.abs(Pn.conj().T @ r); c[sel] = -1
        sel.append(int(np.argmax(c)))
        coef, *_ = np.linalg.lstsq(Phi[:, sel], y, rcond=None)
        r = y - Phi[:, sel] @ coef
    return sorted(sel), coef


def trial(kind, m, s, sigma2, rng, blind=False):
    supp = rng.choice(N, s, replace=False)
    x = np.zeros(N, complex); x[supp] = rng.uniform(1, 2, s) * np.exp(2j * np.pi * rng.random(s))
    Phi = make_phi(kind, m, rng)
    y = Phi @ x + np.sqrt(sigma2 / 2) * (rng.normal(size=m) + 1j * rng.normal(size=m))
    if blind: est, _ = omp(Phi, y, None, sigma2, cap=3 * s)
    else: est, _ = omp(Phi, y, s)
    ok = set(est) == set(supp.tolist())
    fa = len(set(est) - set(supp.tolist()))
    return ok, fa


def prob(kind, m, s, sigma2, trials, seed, blind=False):
    rng = np.random.default_rng(seed); ok = 0; fa = 0
    for _ in range(trials):
        o, f = trial(kind, m, s, sigma2, rng, blind); ok += o; fa += f
    return ok / trials, fa / trials


def main():
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from _budget import step
    fr = [0.03, 0.05, 0.075, 0.1, 0.125, 0.15, 0.2, 0.3, 0.4]
    S = [3, 4, 5, 6, 8, 12, 16, 24]
    sig_hi = 1e-4  # 40 dB

    def s_pt(kind):
        def f():
            print(f"== phase transition, {kind}, SNR(weakest tone)=40 dB: P(exact support) vs m/N (rows s), N=256, 100 trials ==")
            print("s \\ m/N " + " ".join(f"{v:6.3f}" for v in fr))
            P = np.zeros((len(S), len(fr)))
            for i, s in enumerate(S):
                for j, v in enumerate(fr):
                    P[i, j] = prob(kind, max(int(round(v * N)), s + 1), s, sig_hi, 100, 1000 * i + j)[0]
                print(f"{s:3d}     " + " ".join(f"{p:6.2f}" for p in P[i]))
            return P
        return f
    Ps = step("cs", "pt_sample", s_pt("sample"))
    Pg = step("cs", "pt_gauss", s_pt("gauss"))

    def s_m90():
        print("\n== smallest m/N on the grid with P >= 0.9 (and the classical scale s*ln(N/s)/N) ==")
        print("s | sample m/N | gauss m/N | m_sample | m_gauss | m_sample/(s ln(N/s))")
        for i, s in enumerate(S):
            def first(P):
                idx = np.flatnonzero(P[i] >= 0.9); return fr[idx[0]] if len(idx) else None
            a, b = first(Ps), first(Pg)
            ma = None if a is None else int(round(a * N)); mb = None if b is None else int(round(b * N))
            print(f"{s} | {a} | {b} | {ma} | {mb} | {('%.2f' % (ma/(s*np.log(N/s)))) if ma else '-'}")
    step("cs", "m90", s_m90)

    snrs = [-5, 0, 5, 10, 15, 20, 30]
    ms = [26, 38, 51, 77]

    def s_noise():
        print("\n== noise sensitivity, s=5, random sub-sampling: P(exact support) vs SNR of the weakest tone ==")
        print("m (m/N) \\ SNR[dB] " + " ".join(f"{v:6d}" for v in snrs))
        P = np.zeros((len(ms), len(snrs)))
        for i, m in enumerate(ms):
            for j, sn in enumerate(snrs):
                P[i, j] = prob("sample", m, 5, 10 ** (-sn / 10), 150, 5000 + 10 * i + j)[0]
            print(f"{m:3d} ({m/N:.2f})       " + " ".join(f"{p:6.2f}" for p in P[i]))
        return P
    Pn = step("cs", "noise", s_noise)

    def s_blind():
        print("\n== blind OMP (sparsity unknown, noise-level stopping), s=5, m=77 (m/N=0.30) ==")
        print("SNR[dB] | P(exact support) | mean false bins per trial")
        out = {}
        for sn in (0, 5, 10, 20, 30):
            p, fa = prob("sample", 77, 5, 10 ** (-sn / 10), 150, 9000 + sn, blind=True); out[sn] = (p, fa)
            print(f"{sn:6d} | {p:.2f} | {fa:.2f}")
        return out
    step("cs", "blind", s_blind)

    def s_fig():
        fig, ax = plt.subplots(1, 3, figsize=(15, 4.2))
        for a, P, t in ((ax[0], Ps, "random sub-sampling"), (ax[1], Pg, "Gaussian projections")):
            im = a.imshow(P, origin="lower", aspect="auto", vmin=0, vmax=1, cmap="viridis")
            a.set_xticks(range(len(fr))); a.set_xticklabels([f"{v:g}" for v in fr], rotation=60, fontsize=7)
            a.set_yticks(range(len(S))); a.set_yticklabels(S); a.set_xlabel("m/N"); a.set_ylabel("occupied bins s"); a.set_title(f"P(exact support), {t}, 40 dB")
        plt.colorbar(im, ax=ax[1], fraction=0.046)
        for i, m in enumerate(ms): ax[2].plot(snrs, Pn[i], "o-", label=f"m/N={m/N:.2f}")
        ax[2].set_xlabel("SNR of weakest tone [dB]"); ax[2].set_ylabel("P(exact support), s=5"); ax[2].legend(fontsize=7); ax[2].grid(alpha=.3)
        ax[2].set_title("noise robustness")
        plt.tight_layout(); plt.savefig(os.path.join(FIG, "cs_sensing.png"), dpi=110); print("saved figures/cs_sensing.png")
    step("cs", "fig", s_fig)


if __name__ == "__main__":
    main()
