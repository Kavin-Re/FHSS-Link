"""Adaptive interference cancellation (LMS / NLMS / RLS adaptive line enhancers) vs the spreading-gain approach.

MODEL / ASSUMPTIONS (all synthetic, real-valued baseband, sample rate fs = 2000 Hz)
- Signal of interest s[n]: random +-1 chips (power 1, white = what a spread-spectrum chip stream looks like). Each data bit is
  Gp chips (bit * a fresh random +-1 code per bit, like the DS model in sim/fhss_sim.py), used only in the spreading-gain comparison.
- Narrowband interferer: one sinusoid at ~400 Hz, power J = 30 dB above the signal (power 1000), with a drifting frequency:
  default f(t) = 400 + 5 Hz*sin(2*pi*0.5*t); the drift experiment uses linear chirps and the hop experiment uses jumps.
- Mains-like hum: 50 Hz + 150 Hz + 250 Hz (relative amplitudes 1, .5, .3) with total power 20 dB above the signal (100).
- White Gaussian noise at -10 dB (SNR 10 dB relative to the signal, power 0.1).
- Canceller = adaptive line enhancer (ALE): predict d[n] from the delayed samples d[n-delta..n-delta-L+1]; the white signal is not
  predictable after delta=1 sample, the sinusoids are, so e[n] = d[n]-y[n] is the cleaned signal. L = 64 taps. No separate
  reference antenna is assumed (this is the 'single input' version; it can only remove what is predictable).
- Metrics: SINR_in = P_s / (P_J + P_hum + P_noise) on the raw input; SINR_out = P_s / mean((e - s)^2) over the last 4000 samples (the
  signal s is known in the simulation, residual includes leftover interference, noise and the filter's own self-noise).
  Convergence time = first sample at which the 200-sample-block residual power is within 2x (3 dB) of its final value.
- LMS step is given normalised, mu_n = mu*L*P_in (stability needs mu_n < 2); NLMS uses mu_n directly; RLS uses forgetting factor lambda.
- Spreading-gain comparison: correlate Gp chips with the known code; measured bit-level SINR = Gp^2 / Var(sum c_k * interference_k).
  No canceller assumed in that branch; the combination (canceller then despread) is also measured.
- Results are averages over 3 noise/code seeds; a different geometry (e.g. interferer inside the signal band, or a coloured signal) changes them.
Run: python3 lms_cancel.py
"""
import os, math, time
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

FS = 2000.0; L = 64; DELTA = 1
J_DB, HUM_DB, NOISE_DB = 30.0, 20.0, -10.0


def make_input(N, seed, tone="sin", chirp_hz_s=0.0, hop_dwell=None, hum=True, wideband=False, Gp=None):
    """Returns d, s, interference(t) (j+hum+noise), and bits/code info if Gp is given."""
    rng = np.random.default_rng(seed); t = np.arange(N) / FS
    if Gp:
        nb = N // Gp; bits = rng.choice([-1.0, 1.0], nb); code = rng.choice([-1.0, 1.0], (nb, Gp)); s = (bits[:, None] * code).ravel()      # fresh random code per bit (as in sim/fhss_sim.py DS model)
        s = np.concatenate([s, rng.choice([-1.0, 1.0], N - len(s))])
    else: s = rng.choice([-1.0, 1.0], N); bits = code = None
    if hop_dwell:
        nh = N // hop_dwell + 1; f = np.repeat(rng.uniform(150, 900, nh), hop_dwell)[:N]; ph = 2 * np.pi * np.cumsum(f) / FS
    elif chirp_hz_s:
        f = 400 + chirp_hz_s * t; ph = 2 * np.pi * np.cumsum(f) / FS
    else:
        f = 400 + 5 * np.sin(2 * np.pi * 0.5 * t); ph = 2 * np.pi * np.cumsum(f) / FS
    A = math.sqrt(2 * 10 ** (J_DB / 10)); jam = A * np.cos(ph + rng.uniform(0, 6.28))
    if wideband: jam = rng.normal(0, math.sqrt(10 ** (J_DB / 10)), N)
    h = np.zeros(N)
    if hum:
        amps = np.array([1, .5, .3]); amps = amps / math.sqrt((amps ** 2).sum() / 2) * math.sqrt(10 ** (HUM_DB / 10))   # total power = 10^(HUM_DB/10)
        for a, fh in zip(amps, (50, 150, 250)): h += a * np.cos(2 * np.pi * fh * t + rng.uniform(0, 6.28))
    n = rng.normal(0, math.sqrt(10 ** (NOISE_DB / 10)), N)
    return s + jam + h + n, s, jam + h + n, bits, code


def ale(d, algo, par, L=L, delta=DELTA):
    """Adaptive line enhancer. Returns e (error = cleaned signal). par: mu_n for lms/nlms, lambda for rls."""
    N = len(d); dp = np.concatenate([np.zeros(L + delta - 1), d]); U = sliding_window_view(dp, L)[:N]      # row n = d[n-delta], ..., d[n-delta-L+1]... (oldest first)
    U = np.ascontiguousarray(U[:, ::-1]); w = np.zeros(L); e = np.zeros(N); Pin = float(np.mean(d ** 2))
    if algo == "lms":
        mu = par / (L * Pin)
        for n in range(N):
            u = U[n]; e[n] = d[n] - w @ u; w += mu * e[n] * u
    elif algo == "nlms":
        for n in range(N):
            u = U[n]; e[n] = d[n] - w @ u; w += par * e[n] * u / (1e-6 + u @ u)
    elif algo == "rls":
        lam = par; P = np.eye(L) / (0.01 * Pin)
        for n in range(N):
            u = U[n]; Pu = P @ u; k = Pu / (lam + u @ Pu); e[n] = d[n] - w @ u; w += k * e[n]; P = (P - np.outer(k, Pu)) / lam
            if n % 64 == 0: P = (P + P.T) / 2
    else: raise ValueError(algo)
    return e


def sinr_db(s, resid): return 10 * math.log10(np.mean(s ** 2) / max(np.mean(resid ** 2), 1e-12))


def metrics(d, s, e, intf, tail=4000, blk=200):
    sin_in = sinr_db(s, intf[-tail:]); sin_out = sinr_db(s[-tail:], (e - s)[-tail:])
    r = (e - s) ** 2; nb = len(r) // blk; bp = r[:nb * blk].reshape(nb, blk).mean(1); final = r[-tail:].mean()
    idx = np.flatnonzero(bp <= 2 * final); conv = int((idx[0] + 1) * blk) if len(idx) else None
    # require that it stays within 3 dB afterwards
    for i in range(nb):
        if np.all(bp[i:] <= 2.5 * final): conv = (i + 1) * blk; break
    else: conv = None
    return dict(sin_in=sin_in, sin_out=sin_out, gain=sin_out - sin_in, conv=conv)


def avg(f, seeds=(1, 2, 3)):
    rs = [f(s) for s in seeds]; keys = rs[0].keys(); out = {}
    for k in keys:
        v = [r[k] for r in rs if r[k] is not None]; out[k] = float(np.mean(v)) if v else None
    out["n_conv_none"] = sum(r["conv"] is None for r in rs)
    return out


def run_case(algo, par, seed, N=16000, **kw):
    d, s, intf, _, _ = make_input(N, seed, **kw); e = ale(d, algo, par); return metrics(d, s, e, intf)


def psd(x, nfft=512):
    w = np.hanning(nfft); segs = sliding_window_view(x, nfft)[::nfft // 2]; P = (np.abs(np.fft.rfft(segs * w, axis=1)) ** 2).mean(0) / (w ** 2).sum() / FS
    return np.fft.rfftfreq(nfft, 1 / FS), 10 * np.log10(P + 1e-12)


def despread_sinr(resid, code, Gp):
    """bit-level SINR from the interference residual (known code): Gp^2 / Var(sum c_k r_k) over all bits."""
    nb = len(resid) // Gp; z = (resid[:nb * Gp].reshape(nb, Gp) * code).sum(1)
    return 10 * math.log10(Gp ** 2 / np.mean(z ** 2))


def main():
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    here = os.path.dirname(os.path.abspath(__file__)); t0 = time.time()
    d, s, intf, _, _ = make_input(16000, 1)
    print(f"input powers: signal {np.mean(s**2):.2f}, interference total {np.mean(intf**2):.1f} -> SINR_in = {sinr_db(s, intf):.1f} dB (tone 30 dB, hum 20 dB, noise -10 dB re signal); L={L} taps, fs={FS:.0f} Hz")
    print("\n== SINR improvement vs step size (3 seeds, slow sinusoidal drift +-5 Hz, N=16000) ==")
    mus = [0.001, 0.003, 0.01, 0.03, 0.1, 0.3, 1.0]; lams = [0.99, 0.995, 0.998, 0.999, 0.9995]; sweep = {}
    print(f"{'algo':5s} {'param':>8s} {'gain dB':>8s} {'SINRout':>8s} {'conv samples':>13s} {'conv ms':>8s}")
    for algo in ("lms", "nlms"):
        for mu in mus:
            r = avg(lambda sd: run_case(algo, mu, sd)); sweep[(algo, mu)] = r
            print(f"{algo:5s} {mu:8.3f} {r['gain']:8.1f} {r['sin_out']:8.1f} {str(round(r['conv']) if r['conv'] else 'no'):>13s} {1000*r['conv']/FS if r['conv'] else float('nan'):8.0f}")
    for lam in lams:
        r = avg(lambda sd: run_case("rls", lam, sd)); sweep[("rls", lam)] = r
        print(f"{'rls':5s} {lam:8.4f} {r['gain']:8.1f} {r['sin_out']:8.1f} {str(round(r['conv']) if r['conv'] else 'no'):>13s} {1000*r['conv']/FS if r['conv'] else float('nan'):8.0f}")
    best = {a: max((k for k in sweep if k[0] == a), key=lambda k: sweep[k]["gain"]) for a in ("lms", "nlms", "rls")}
    print("best setting per algorithm:", {a: (k[1], round(sweep[k]['gain'], 1)) for a, k in best.items()}, " (tuned on the same scenario -> optimistic)")
    print(f"[{time.time()-t0:.0f}s elapsed]")

    # --- spreading gain comparison
    print("\n== spreading gain vs canceller (bit-level SINR, same interference; canceller=best setting above) ==")
    print(f"{'Gp':>4s} {'Gp dB':>6s} {'SINR in(chip)':>13s} {'despread only':>14s} {'canceller only(chip)':>21s} {'canceller+despread':>19s}")
    spread = {}
    for Gp in (16, 64, 256):
        rows = []
        for sd in (1, 2, 3):
            d, s, intf, bits, code = make_input(25600, sd, Gp=Gp); e = ale(d, "rls", best["rls"][1]); h = 12800 // Gp * Gp
            rows.append((sinr_db(s, intf), despread_sinr(intf, code, Gp), sinr_db(s[-8000:], (e - s)[-8000:]), despread_sinr((e - s)[h:], code[h // Gp:], Gp)))
        r = np.mean(rows, 0); spread[Gp] = r
        print(f"{Gp:4d} {10*math.log10(Gp):6.1f} {r[0]:13.1f} {r[1]:14.1f} {r[2]:21.1f} {r[3]:19.1f}")
    # BER at Gp=64 with the measured streams
    Gp = 64; errs = {"despread only": 0, "canceller+despread": 0, "canceller only (1 chip=1 bit)": 0}; nbits = {k: 0 for k in errs}
    for sd in range(1, 9):
        d, s, intf, bits, code = make_input(25600, 100 + sd, Gp=Gp); e = ale(d, "rls", best["rls"][1]); nb = 25600 // Gp
        for name, x in (("despread only", d), ("canceller+despread", e)):
            z = (x[:nb * Gp].reshape(nb, Gp) * code).sum(1)
            sl = slice(len(z) // 2, None) if name != "despread only" else slice(None)
            errs[name] += int(np.sum(np.sign(z[sl]) != bits[:nb][sl])); nbits[name] += len(z[sl])
        errs["canceller only (1 chip=1 bit)"] += int(np.sum(np.sign(e[12800:]) != s[12800:])); nbits["canceller only (1 chip=1 bit)"] += len(e[12800:])
    print(f"BER at Gp={Gp} (8 seeds; canceller branches counted after 1st half for convergence): " + "; ".join(f"{k}: {errs[k]}/{nbits[k]} = {errs[k]/nbits[k]:.4f}" for k in errs))

    # --- drift
    print("\n== linear frequency drift (chirp rate) : SINR improvement dB at the best-grid step (picked per rate), N=12000 ==")
    rates = [0, 100, 500, 2000, 8000]; drift = {}
    grid = {"lms": [0.03, 0.1, 0.3, 1.0], "nlms": [0.03, 0.1, 0.3, 1.0], "rls": [0.99, 0.995, 0.999]}
    print(f"{'rate Hz/s':>10s} " + " ".join(f"{a:>8s}" for a in grid))
    for rt in rates:
        row = {}
        for a, g in grid.items(): row[a] = max(avg(lambda sd: run_case(a, p, sd, N=12000, chirp_hz_s=rt), seeds=(1, 2))["gain"] for p in g)
        drift[rt] = row; print(f"{rt:10d} " + " ".join(f"{row[a]:8.1f}" for a in grid))
    print(f"[{time.time()-t0:.0f}s elapsed]")

    # --- hop
    print("\n== interferer HOPS to a random frequency (150-900 Hz) every `dwell` samples: SINR improvement dB (best grid step per dwell), N=12000 ==")
    dw = [4000, 1000, 400, 200, 100, 50]; hop = {}
    print(f"{'dwell smp':>9s} {'ms':>6s} " + " ".join(f"{a:>8s}" for a in grid) + f"   spreading gain Gp=16/64/256: {10*math.log10(16):.1f}/{10*math.log10(64):.1f}/{10*math.log10(256):.1f} dB")
    for D in dw:
        row = {}
        for a, g in grid.items(): row[a] = max(avg(lambda sd: run_case(a, p, sd, N=12000, hop_dwell=D), seeds=(1, 2))["gain"] for p in g)
        hop[D] = row; print(f"{D:9d} {1000*D/FS:6.0f} " + " ".join(f"{row[a]:8.1f}" for a in grid))
    # wideband
    ww = avg(lambda sd: run_case("rls", 0.999, sd, N=12000, wideband=True), seeds=(1, 2))
    print(f"\nwideband (Gaussian) interferer of the same power instead of a tone: RLS gain {ww['gain']:.1f} dB (a predictor cannot cancel what is not predictable)")
    print(f"[{time.time()-t0:.0f}s total]")

    # --- figures
    fig, ax = plt.subplots(2, 2, figsize=(11, 8))
    ax[0, 0].semilogx(mus, [sweep[("lms", m)]["gain"] for m in mus], "o-", label="LMS"); ax[0, 0].semilogx(mus, [sweep[("nlms", m)]["gain"] for m in mus], "s-", label="NLMS")
    ax[0, 0].axhline(10 * math.log10(64), color="gray", ls="--", label="spreading gain Gp=64 (18 dB)"); ax[0, 0].set_xlabel("normalised step size mu_n"); ax[0, 0].set_ylabel("SINR improvement (dB)"); ax[0, 0].legend(fontsize=8); ax[0, 0].grid(alpha=.3, which="both")
    ax[0, 0].set_title("LMS / NLMS vs step size")
    ax[0, 1].semilogx([1 - l for l in lams], [sweep[("rls", l)]["gain"] for l in lams], "o-", color="C2", label="RLS"); ax[0, 1].axhline(10 * math.log10(64), color="gray", ls="--")
    ax[0, 1].set_xlabel("1 - forgetting factor"); ax[0, 1].set_ylabel("SINR improvement (dB)"); ax[0, 1].grid(alpha=.3, which="both"); ax[0, 1].set_title("RLS vs forgetting"); ax[0, 1].legend()
    for a, p, c in (("lms", best["lms"][1], "C0"), ("nlms", best["nlms"][1], "C1"), ("rls", best["rls"][1], "C2")):
        d, s, intf, _, _ = make_input(16000, 1); e = ale(d, a, p); r = (e - s) ** 2; b = r[:16000].reshape(-1, 200).mean(1)
        ax[1, 0].semilogy(np.arange(len(b)) * 200 / FS, b, c, label=f"{a} ({p})")
    ax[1, 0].set_xlabel("time (s)"); ax[1, 0].set_ylabel("residual power (200-sample blocks)"); ax[1, 0].legend(fontsize=8); ax[1, 0].grid(alpha=.3, which="both"); ax[1, 0].set_title("Convergence")
    d, s, intf, _, _ = make_input(16000, 1); e = ale(d, "rls", best["rls"][1]); f, P1 = psd(d[8000:]); _, P2 = psd(e[8000:]); _, P0 = psd(s[8000:])
    ax[1, 1].plot(f, P1, label="input"); ax[1, 1].plot(f, P2, label="after RLS ALE"); ax[1, 1].plot(f, P0, "k:", label="signal alone"); ax[1, 1].set_xlabel("Hz"); ax[1, 1].set_ylabel("PSD (dB/Hz)"); ax[1, 1].legend(fontsize=8); ax[1, 1].grid(alpha=.3); ax[1, 1].set_title("Spectrum: tone and hum lines removed")
    fig.tight_layout(); fig.savefig(os.path.join(here, "figures", "lms_overview.png"), dpi=120); plt.close(fig)
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    for a, c in (("lms", "C0"), ("nlms", "C1"), ("rls", "C2")):
        ax[0].semilogx([r for r in rates[1:]], [drift[r][a] for r in rates[1:]], "o-", color=c, label=a)
        ax[1].semilogx(dw, [hop[D][a] for D in dw], "o-", color=c, label=a)
    for gp, ls in ((16, ":"), (64, "--"), (256, "-.")):
        for x in ax: x.axhline(10 * math.log10(gp), color="gray", ls=ls, lw=1)
        ax[1].text(dw[-1], 10 * math.log10(gp) + .3, f"Gp={gp}", fontsize=7)
    ax[0].set_xlabel("linear drift rate (Hz/s)"); ax[1].set_xlabel("hop dwell (samples, 2000/s)"); ax[1].invert_xaxis()
    for x, t in zip(ax, ("Drifting tone", "Hopping tone")): x.set_ylabel("SINR improvement (dB)"); x.set_title(t); x.grid(alpha=.3, which="both"); x.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(os.path.join(here, "figures", "lms_drift_hop.png"), dpi=120); plt.close(fig)


if __name__ == "__main__":
    main()
