"""Beyond #6: GPS-style carry-off spoofing vs an innovation test (simulation only; 1-D delay-lock loop model).
Receiver: DLL tracking a range (metres) with a triangular-correlator S-curve (chip = 293 m), first-order loop at 10 Hz.
Spoofer: starts aligned with the genuine signal at +power advantage, then drags its delay at `rate` m/s; once the loop is
captured the genuine peak (>1 chip away) no longer matters. Defence: clock-aided innovation test. The receiver knows its
oscillator is stable, so the tracked range of a static receiver should not drift; CUSUM on the per-step range increment
(normalised by calibrated sigma) flags a sustained drag. Clock grade = random-walk noise per step (assumed numbers).
Outputs: detection delay and the pull-off at detection vs drag rate for two clock grades; miss rate; false alarm rate."""
import numpy as np
from _common import *

CHIP = 293.0
HARM = 50.0     # position error (m) counted as 'harmful pull-off'
DT = 0.1
def scurve(d):
    """Early-late discriminator of a triangular correlation: linear inside +-0.5 chip, falling to 0 at +-1 chip."""
    a = np.abs(d) / CHIP
    s = np.where(a < 0.5, d, np.sign(d) * (1 - a) * CHIP)
    return np.where(a < 1.0, s, 0.0)

def simulate(rate, clk_sigma, trials, T=600.0, t_attack=60.0, ag=1.0, asp=1.6, K=0.1, noise=0.1, attack=True, rng=None):
    """Returns x (trials, steps) tracked range minus truth (genuine truth = 0), and truth of spoofer offset."""
    n = int(T / DT); t0 = int(t_attack / DT)
    x = np.zeros((trials, n)); xs = np.zeros(trials)
    for k in range(1, n):
        tau_s = 0.0 if not attack or k < t0 else rate * (k - t0) * DT
        e = ag * scurve(0.0 - xs) + (asp * scurve(tau_s - xs) if attack and k >= t0 else 0.0)
        xs = xs + K * e + rng.normal(0, noise, trials) + rng.normal(0, clk_sigma, trials)
        x[:, k] = xs
    return x

def block_inc(x, L=10):
    """Non-overlapping 1 s block increments of the tracked range (m per block)."""
    n = (x.shape[1] // L) * L
    xb = x[:, :n:L]
    return np.diff(xb, axis=1), L

def cusum_detect(x, sigma_i, kappa=0.5, h=8.0):
    """Two-sided CUSUM on normalised 1 s increments. Returns step index of first alarm (-1 = none)."""
    inc, L = block_inc(x)
    z = inc / sigma_i
    trials, m = z.shape
    S = np.zeros(trials); Sn = np.zeros(trials); det = np.full(trials, -1)
    for k in range(m):
        S = np.maximum(0, S + z[:, k] - kappa); Sn = np.maximum(0, Sn - z[:, k] - kappa)
        hit = ((S > h) | (Sn > h)) & (det < 0)
        det[hit] = (k + 1) * L
    return det

def calibrate(clk_sigma, rng, trials, target_fa=0.01):
    """sigma_i from attack-free runs, then the smallest h with attack-free false-alarm rate <= target over the whole run."""
    x0 = simulate(0, clk_sigma, trials, attack=False, rng=rng)
    inc, _ = block_inc(x0)
    sigma_i = float(inc.std())
    best_h = None
    for h in np.arange(2, 60, 0.5):
        fa = np.mean(cusum_detect(x0, sigma_i, h=h) >= 0)
        if fa <= target_fa: best_h = float(h); break
    return sigma_i, best_h, x0

def run(fast=False, seed=11):
    rng = np.random.default_rng(seed)
    trials = 100 if fast else 300
    rates = [0.1, 0.2, 0.5, 1.0, 2.0, 5.0] if not fast else [0.2, 1.0, 5.0]
    grades = {"TCXO-like (clk noise 0.3 m/step)": 0.3, "OCXO-like (clk noise 0.03 m/step)": 0.03}
    out = {"rates": rates, "grades": {}, "harm_m": HARM}
    t_att = int(60.0 / DT)
    for gname, cs in grades.items():
        sigma_i, h, x0 = calibrate(cs, rng, trials)
        fa = float(np.mean(cusum_detect(x0, sigma_i, h=h) >= 0))
        g = {"sigma_i": sigma_i, "h": h, "fa": fa, "det_delay_s": [], "pull_m": [], "miss": [], "safe": [], "undefended_t_to_harm_s": []}
        for r in rates:
            x = simulate(r, cs, trials, rng=rng)
            det = cusum_detect(x, sigma_i, h=h)
            harm_idx = np.array([np.argmax(np.abs(row) > HARM) if (np.abs(row) > HARM).any() else x.shape[1] for row in x])
            caught = det >= t_att
            idx = np.where(det >= 0, det, x.shape[1] - 1)
            g["miss"].append(float(np.mean(det < 0)))
            g["pull_m"].append(float(np.median(np.abs(x[np.arange(trials), idx]))))
            g["det_delay_s"].append(float(np.median((det[caught] - t_att) * DT)) if caught.any() else None)
            g["safe"].append(float(np.mean((det >= 0) & (det <= harm_idx))))   # alarm raised before position error exceeded HARM
            g["undefended_t_to_harm_s"].append(float(np.median((harm_idx - t_att) * DT)))
        out["grades"][gname] = g
    return out

def main():
    out = run()
    fig, ax = plt.subplots(1, 3, figsize=(11, 3.4))
    cols = [C["verm"], C["blue"]]
    for (gname, g), c in zip(out["grades"].items(), cols):
        lab = gname.split(" (")[0]
        print(gname, f"sigma_i={g['sigma_i']:.3f} m per 1 s block, h={g['h']}, attack-free false-alarm {g['fa']:.3f}")
        for r, d, p, m, sf, th in zip(out["rates"], g["det_delay_s"], g["pull_m"], g["miss"], g["safe"], g["undefended_t_to_harm_s"]):
            print(f"   drag {r:4.1f} m/s: detect delay {d} s, pull-off at alarm {p:.0f} m, miss {m:.2f}, alarm before {HARM:.0f} m error {sf:.2f}, (undefended: {HARM:.0f} m error after {th:.0f} s)")
        ax[0].semilogx(out["rates"], [np.nan if d is None else d for d in g["det_delay_s"]], "o-", color=c, label=lab)
        ax[1].loglog(out["rates"], g["pull_m"], "o-", color=c, label=lab)
        ax[2].semilogx(out["rates"], g["safe"], "o-", color=c, label=lab)
    ax[0].set_xlabel("drag rate (m/s)"); ax[0].set_ylabel("median alarm delay (s)"); ax[0].legend()
    ax[1].set_xlabel("drag rate (m/s)"); ax[1].set_ylabel("pull-off at alarm (m)"); ax[1].axhline(HARM, color=C["grey"], ls=":")
    ax[2].set_xlabel("drag rate (m/s)"); ax[2].set_ylabel(f"P(alarm before {HARM:.0f} m error)"); ax[2].set_ylim(-0.02, 1.02)
    save_fig(fig, "b06_carryoff.png"); save_json("b06_carryoff.json", out)
    g = out["grades"]["OCXO-like (clk noise 0.03 m/step)"]; t = out["grades"]["TCXO-like (clk noise 0.3 m/step)"]
    def slowest(gr):
        ok = [r for r, sf in zip(out["rates"], gr["safe"]) if sf >= 0.9]
        return min(ok) if ok else None
    key("B6", f"slowest drag alarmed before {HARM:.0f} m error (>=90% of runs): {slowest(g)} m/s with OCXO-like clock vs {slowest(t)} m/s with TCXO-like; slower drags evade within the 540 s window; attack-free false alarm {g['fa']:.3f}/{t['fa']:.3f}")
if __name__ == "__main__":
    main()
