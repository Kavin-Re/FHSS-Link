"""R4 (RED_TEAM idea 7) Time-pushing attack on the clock filter. Own-link simulation.
Receiver runs a 2-state Kalman filter (offset, skew) on beacon timestamps (1 per second, jitter 3 us). The attacker adds a slowly growing bias to the
timestamps (equivalently a relay whose delay grows slowly; no key is broken) (r ppm = r microseconds per second), starting at t0=150 s. The filter happily tracks the bias, so the receiver's hop grid slides away from the
true grid; reception fails once the error exceeds the guard (30 us here). Detectors: (a) the usual innovation (NIS) gate at 3 sigma; (b) a skew-rate check: alarm if the filter's skew estimate
moves by more than thr ppm within W=60 s (physics: a crystal's skew cannot change that fast thermally; stands in for a hardware oscillator reference). True skew: +-20 ppm start, random walk
0.02 ppm/sqrt(s), plus an unmodelled 0.2 ppm / 300 s thermal sinusoid (same flavour as lab2/clock_kalman.py; model copied, not imported)."""
import numpy as np
from _common import *
QS = 0.02; PPM = 1e-6;  TB = 1.0; SIGV = 3e-6; GUARD = 30e-6; T0 = 150

def run(r_ppm, T=900, seed=0, with_attack=True, thr=0.8, W=60, trace=False):
    rng = np.random.default_rng(seed)
    s = rng.uniform(-20, 20) * PPM; th = 0.0; ph = rng.uniform(0, 6.28)
    x = np.array([0.0, 0.0]); P = np.diag([(1e-3) ** 2, (20 * PPM) ** 2]); F = np.array([[1, TB], [0, 1]])
    qs = (QS * PPM) ** 2; Q = np.array([[0.3e-6 ** 2 * TB + qs * TB ** 3 / 3, qs * TB ** 2 / 2], [qs * TB ** 2 / 2, qs * TB]])
    nis_hits = 0; shat = []; err = []; t_viol = None; t_det = None; 
    for t in range(T):
        s_eff = s + 0.2 * PPM * np.sin(2 * np.pi * t / 300 + ph)
        th += s_eff * TB + 0.3e-6 * rng.normal(); s += 0.02 * PPM * rng.normal()
        x = F @ x; P = F @ P @ F.T + Q
        bias = r_ppm * PPM * (t - T0) if (with_attack and t >= T0) else 0.0
        y = th + bias + SIGV * rng.normal()
        S = P[0, 0] + SIGV ** 2; nu = y - x[0]
        if t > 30 and nu * nu / S > 9: nis_hits += (t >= T0)
        K = P[:, 0] / S; x = x + K * nu; P = (np.eye(2) - np.outer(K, [1, 0])) @ P
        shat.append(x[1]); err.append(th - x[0])                                     # timing error at a packet = true offset - estimate
        if t >= 100 and t_det is None and abs(x[1] - shat[t - W]) > thr * PPM:   # skew moved faster than any crystal can (see docstring)
            t_det = t
        if t_viol is None and t >= T0 and abs(err[-1]) > GUARD: t_viol = t
    if trace: return np.array(shat)
    return dict(t_viol=None if t_viol is None else t_viol - T0, t_det=None if t_det is None else t_det - T0, nis_hits_after=nis_hits)

def evaluate(rs=(0.1, 0.2, 0.5, 1.0, 2.0, 5.0), seeds=range(12)):
    out = {}
    for r in rs:
        R = [run(r, seed=s) for s in seeds]
        tv = [x["t_viol"] for x in R]; td = [x["t_det"] for x in R]
        out[r] = dict(viol_frac=float(np.mean([v is not None for v in tv])), t_viol=float(np.median([v for v in tv if v is not None])) if any(v is not None for v in tv) else None,
                      det_frac=float(np.mean([d is not None for d in td])), t_det=float(np.median([d for d in td if d is not None])) if any(d is not None for d in td) else None,
                      nis=float(np.mean([x["nis_hits_after"] for x in R])))
    fa = float(np.mean([run(0, seed=s, with_attack=False)["t_det"] is not None for s in seeds]))
    nis0 = float(np.mean([run(0, seed=s, with_attack=False)["nis_hits_after"] for s in seeds]))
    return out, fa, nis0

def main():
    out, fa, nis0 = evaluate(); print(f"false-alarm rate of skew-rate check without attack (900 s): {fa:.2f}; NIS-gate hits per run with NO attack (t>=150): {nis0:.1f}")
    print(f"{'push ppm':>8s} {'viol. frac':>10s} {'t_viol s':>9s} {'det frac':>9s} {'t_det s':>8s} {'NIS gate hits/run':>18s}")
    for r, v in out.items(): print(f"{r:8.1f} {v['viol_frac']:10.2f} {str(v['t_viol']):>9s} {v['det_frac']:9.2f} {str(v['t_det']):>8s} {v['nis']:18.1f}")
    rs = list(out); fig, ax = plt.subplots(figsize=(6.2, 3.5))
    ax.plot(rs, [out[r]["t_viol"] if out[r]["t_viol"] else np.nan for r in rs], "o-", color=C["verm"], label="time until guard violated (no defence)")
    ax.plot(rs, [out[r]["t_det"] if out[r]["t_det"] else np.nan for r in rs], "s-", color=C["blue"], label="time until skew-rate alarm")
    ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlabel("push rate (ppm = us per s)"); ax.set_ylabel("seconds after attack start"); ax.legend()
    ax.set_title("R4 time-pushing: slow ramp vs detection"); save_fig(fig, "r4_time_push.png"); save_json("r4_time_push.json", dict(results={str(k): v for k, v in out.items()}, false_alarm=fa, nis_noattack=nis0))
    key("push 1 ppm: median seconds to guard violation vs to skew-rate alarm", f"{out[1.0]['t_viol']} vs {out[1.0]['t_det']}")
    return out, fa, nis0
if __name__ == "__main__": main()
