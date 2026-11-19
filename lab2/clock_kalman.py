"""Module 2 - clock tamer: 2-state Kalman filter (offset, skew) vs 'reset to last beacon' resync.

Model / assumptions
- Receiver clock offset theta (s) relative to the transmitter's hop grid: theta' = skew s + white phase noise
  (sig_theta = 0.3 us / sqrt(s)). Skew s starts uniform in +-20 ppm (crystal tolerance), then random-walks
  (sig_s = 0.02 ppm / sqrt(s)) and carries an UNMODELLED slow thermal sinusoid (0.5 ppm amplitude, 300 s period,
  random phase). The Kalman filter models only the random walk.
- A beacon every T_b seconds carries the transmitter timestamp; the receiver measures theta + v, v ~ N(0, (3 us)^2)
  (detection jitter + timestamp quantisation). Optionally each beacon is lost with probability p_bl.
- Estimators: naive = reset offset to the last beacon measurement and free-run (skew ignored). Kalman = state
  [theta, s], predict with the constant-skew model, update at each received beacon (filter knows the true noise
  densities unless a mismatch experiment says otherwise).
- Timing error at a data packet = theta_true - theta_hat_predicted. The RX window must be opened +-g around the
  predicted hop boundary, so the guard needed for a 99.9 % reception rate is the 99.9th percentile of |error| over all
  packets (packets are uniform over the beacon cycle). Calibrated on one set of runs, then checked on an independent set.
- Airtime model: slot = T_pkt + 2 g, T_pkt = 2 ms; a beacon costs 1 ms every T_b. Useful fraction
  eta = T_pkt/(T_pkt+2g) * (1 - T_beacon/T_b). 'Saved' = eta_kalman - eta_naive (absolute percentage points).
- Limits: Gaussian noise, no packet-reception-dependent timing information, single link, no clock steps/outages.
"""
import os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "figures")
PPM = 1e-6
PAR = dict(s0=20 * PPM, sig_s=0.02 * PPM, sig_th=0.3e-6, sig_v=3e-6, temp_amp=0.5 * PPM, temp_per=300.0)
T_PKT, T_BCN = 2e-3, 1e-3


def kalman_Q(tau, q_th, q_s):
    return np.array([[q_th * tau + q_s * tau ** 3 / 3, q_s * tau ** 2 / 2], [q_s * tau ** 2 / 2, q_s * tau]])


def run(Tb, cycles=150, R=300, nsub=50, seed=0, p_bl=0.0, qs_mult=1.0, par=PAR, burn=15):
    """Returns (err_naive, err_kalman) arrays of timing errors at packet instants (burn-in removed)."""
    rng = np.random.default_rng(seed)
    tau = Tb / nsub
    s = rng.uniform(-par["s0"], par["s0"], R)
    th = rng.normal(0, 50e-6, R)
    ph = rng.uniform(0, 2 * np.pi, R)
    x = np.zeros((R, 2)); P = np.tile(np.diag([(1e-3) ** 2, (par["s0"]) ** 2]), (R, 1, 1))
    F = np.array([[1, tau], [0, 1]]); Q = kalman_Q(tau, par["sig_th"] ** 2, (par["sig_s"] ** 2) * qs_mult)
    y_last = np.zeros(R); have = np.zeros(R, dtype=bool)
    en, ek = [], []
    t = 0.0
    for c in range(cycles):
        for j in range(1, nsub + 1):
            t += tau
            s_eff = s + par["temp_amp"] * np.sin(2 * np.pi * t / par["temp_per"] + ph)
            th = th + s_eff * tau + par["sig_th"] * np.sqrt(tau) * rng.normal(size=R)
            s = s + par["sig_s"] * np.sqrt(tau) * rng.normal(size=R)
            x = x @ F.T
            P = F @ P @ F.T + Q
            if c >= burn:
                en.append(th - y_last); ek.append(th - x[:, 0])
        # beacon at end of cycle
        got = rng.random(R) >= p_bl
        y = th + par["sig_v"] * rng.normal(size=R)
        y_last = np.where(got, y, y_last)
        S = P[:, 0, 0] + par["sig_v"] ** 2
        Kg = P[:, :, 0] / S[:, None]
        innov = y - x[:, 0]
        xn = x + Kg * innov[:, None]
        IKH = np.tile(np.eye(2), (R, 1, 1)); IKH[:, :, 0] -= Kg
        Pn = IKH @ P @ np.transpose(IKH, (0, 2, 1)) + (Kg[:, :, None] * (par["sig_v"] ** 2) * Kg[:, None, :])
        x = np.where(got[:, None], xn, x); P = np.where(got[:, None, None], Pn, P)
    return np.concatenate(en), np.concatenate(ek)


def guard_for(err, q=0.999):
    return float(np.quantile(np.abs(err), q))


def eta(g, Tb):
    return T_PKT / (T_PKT + 2 * g) * (1 - T_BCN / Tb)


def main():
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from _budget import step
    Tbs = [0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 120]

    def s_table():
        print("== guard time for 99.9% reception vs beacon period (calibrate seed 0, hold-out seed 1) ==")
        print(" T_b[s] | rms err naive/kalman [us] | guard g naive / kalman [us] | hold-out reception naive / kalman | eta naive / kalman | saved [pp]")
        rows = []
        for Tb in Tbs:
            en, ek = run(Tb, seed=0); hn, hk = run(Tb, seed=1)
            gn, gk = guard_for(en), guard_for(ek)
            rn, rk = float(np.mean(np.abs(hn) <= gn)), float(np.mean(np.abs(hk) <= gk))
            e_n, e_k = eta(gn, Tb), eta(gk, Tb)
            rows.append((Tb, np.sqrt(np.mean(en ** 2)), np.sqrt(np.mean(ek ** 2)), gn, gk, rn, rk, e_n, e_k))
            print(f"{Tb:7.2f} | {rows[-1][1]*1e6:9.1f} {rows[-1][2]*1e6:9.1f} | {gn*1e6:10.1f} {gk*1e6:10.1f} | {rn:.4f} {rk:.4f} | {e_n:.3f} {e_k:.3f} | {100*(e_k-e_n):6.1f}")
        return rows
    rows = step("ck", "table", s_table)

    def s_best():
        print("\n== best operating point (max eta over the T_b grid) ==")
        for name, idx in (("naive", 7), ("kalman", 8)):
            b = max(rows, key=lambda r: r[idx]); print(f"{name:7s} best T_b={b[0]} s  eta={b[idx]:.3f}  guard={b[3 if name=='naive' else 4]*1e6:.1f} us")
        bn = max(rows, key=lambda r: r[7]); bk = max(rows, key=lambda r: r[8])
        print(f"at each method's own best T_b: kalman - naive = {100*(bk[8]-bn[7]):.1f} pp useful airtime")
        # beacon rate needed to hold guard <= 100 us
        for name, idx in (("naive", 3), ("kalman", 4)):
            ok = [r[0] for r in rows if r[idx] <= 100e-6]
            print(f"{name:7s} longest T_b on the grid keeping guard <= 100 us: {max(ok) if ok else 'none'} s")
    step("ck", "best", s_best)

    def s_loss():
        print("\n== beacon loss p_bl=0.2, T_b=5 s ==")
        for pb in (0.0, 0.2):
            en, ek = run(5, seed=0, p_bl=pb)
            print(f"p_bl={pb}: guard naive {guard_for(en)*1e6:.1f} us, kalman {guard_for(ek)*1e6:.1f} us")
        print("\n== filter mismatch at T_b=30 s: skew-walk density used by the filter x true ==")
        for m in (0.01, 0.1, 1.0, 10.0, 100.0):
            _, ek = run(30, seed=0, qs_mult=m)
            print(f"q_s multiplier {m:6.2f}: guard {guard_for(ek)*1e6:.1f} us, rms {np.sqrt(np.mean(ek**2))*1e6:.1f} us")
        print("\n== without thermal sinusoid and without skew walk (pure constant skew), T_b=30 s ==")
        par2 = dict(PAR, temp_amp=0.0, sig_s=1e-12)
        en, ek = run(30, seed=0, par=par2)
        print(f"guard naive {guard_for(en)*1e6:.1f} us, kalman {guard_for(ek)*1e6:.1f} us")
    step("ck", "loss", s_loss)

    def s_fig():
        T = np.array([r[0] for r in rows])
        fig, ax = plt.subplots(1, 2, figsize=(10.5, 4))
        ax[0].loglog(T, [r[3] * 1e6 for r in rows], "o-", c="#c0392b", label="naive reset")
        ax[0].loglog(T, [r[4] * 1e6 for r in rows], "o-", c="#1e8449", label="Kalman")
        ax[0].set_xlabel("beacon period T_b [s]"); ax[0].set_ylabel("guard g for 99.9% [us]"); ax[0].legend(); ax[0].grid(alpha=.3, which="both")
        ax[0].set_title("guard time needed")
        ax[1].semilogx(T, [r[7] for r in rows], "o-", c="#c0392b", label="naive reset")
        ax[1].semilogx(T, [r[8] for r in rows], "o-", c="#1e8449", label="Kalman")
        ax[1].set_xlabel("beacon period T_b [s]"); ax[1].set_ylabel("useful airtime fraction eta"); ax[1].legend(); ax[1].grid(alpha=.3)
        ax[1].set_title("airtime efficiency (T_pkt=2 ms, beacon 1 ms)")
        plt.tight_layout(); plt.savefig(os.path.join(FIG, "clock_kalman.png"), dpi=110)
        print("saved figures/clock_kalman.png")
    step("ck", "fig", s_fig)


if __name__ == "__main__":
    main()
