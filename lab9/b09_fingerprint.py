"""B9 Fingerprint forgery (simulation): an attacker emulates a victim's crystal skew in software/SDR.
Feature 1 = mean skew (ppm). Feature 2 = short-term oscillator jitter rms. The attacker can SET skew to any value
(limited by how well he measured the victim and by his synthesiser resolution) and can ADD jitter, but cannot REMOVE
his own oscillator's jitter floor J_a. Question: at what precision does feature 1 fail, and when does feature 2 restore it?"""
import math
import numpy as np
from _common import *

SIG_POP, SIG_M, NV_PKT, N_ENROL, N_J = 5.0, 0.30, 8, 100, 64   # ppm spread, per-packet skew noise, packets per decision, enrolment packets, jitter samples
D, TRIALS = 50, 40

def meas_skew(rng, s, n_pkt):                 # mean of n_pkt noisy per-packet skew estimates
    return s + rng.normal(0, SIG_M / math.sqrt(n_pkt), np.shape(s))
def meas_jit(rng, j):                          # jitter rms estimated from N_J samples
    return j * np.sqrt(rng.chisquare(N_J, np.shape(j)) / N_J)

def thresholds(rng, s, j):
    """Per-feature thresholds from legitimate trials giving ~0.5% FRR each (two-sided)."""
    S, J = np.repeat(s, 40), np.repeat(j, 40)
    d1 = np.abs(meas_skew(rng, S, NV_PKT) - meas_skew(rng, S, N_ENROL))        # includes a fresh enrolment error
    d2 = np.abs(np.log(meas_jit(rng, J) / meas_jit(rng, J)))
    return np.quantile(d1, 0.995), np.quantile(d2, 0.995)

def one_seed(seed, sig_a_grid, ratios):
    rng = np.random.default_rng(seed)
    s = rng.normal(0, SIG_POP, D); j = np.exp(rng.normal(0, 0.3, D))
    s_enr = meas_skew(rng, s, N_ENROL); j_enr = meas_jit(rng, np.repeat(j, 1))   # enrolled (noisy) templates
    t1, t2 = thresholds(rng, s, j)
    res = {"t1": float(t1)}
    # legitimate users (FRR) and zero-effort impostors (another device)
    L1 = np.abs(meas_skew(rng, np.repeat(s, TRIALS), NV_PKT) - np.repeat(s_enr, TRIALS)) <= t1
    L2 = np.abs(np.log(meas_jit(rng, np.repeat(j, TRIALS)) / np.repeat(j_enr, TRIALS))) <= t2
    res["frr_both"] = float(1 - (L1 & L2).mean())
    other = rng.permutation(D); same = other == np.arange(D); other[same] = (other[same] + 1) % D
    Z1 = np.abs(meas_skew(rng, np.repeat(s[other], TRIALS), NV_PKT) - np.repeat(s_enr, TRIALS)) <= t1
    res["zero_effort_f1"] = float(Z1.mean())
    # forgery of feature 1 at attacker precision sig_a
    acc1 = []
    for sa in sig_a_grid:
        emit = np.repeat(s, TRIALS) + rng.normal(0, sa, D * TRIALS)       # attacker sets skew = victim + his error
        a1 = np.abs(meas_skew(rng, emit, NV_PKT) - np.repeat(s_enr, TRIALS)) <= t1
        acc1.append(float(a1.mean()))
    res["acc1"] = acc1
    # feature 2: victim jitter fixed to its own value; attacker floor J_a = ratio * j_v ; attacker adds noise only if he is below
    sa0 = 0.05                                                            # near-perfect skew forgery so feature 1 does not mask feature 2
    acc2, accb = [], []
    for r in ratios:
        jf = np.repeat(j, TRIALS); Ja = r * jf
        jemit = np.sqrt(np.maximum(jf ** 2, Ja ** 2))                     # cannot go below floor; can pad up to victim
        a2 = np.abs(np.log(meas_jit(rng, jemit) / np.repeat(j_enr, TRIALS))) <= t2
        emit = np.repeat(s, TRIALS) + rng.normal(0, sa0, D * TRIALS)
        a1 = np.abs(meas_skew(rng, emit, NV_PKT) - np.repeat(s_enr, TRIALS)) <= t1
        acc2.append(float(a2.mean())); accb.append(float((a1 & a2).mean()))
    res["acc2"], res["accb"] = acc2, accb
    return res

def run(fast=False):
    sig_a = [0.01, 0.03, 0.1, 0.2, 0.3, 0.5, 1.0, 2.0, 5.0]; ratios = [0.5, 0.8, 1.0, 1.25, 1.5, 2.0, 3.0]
    R = [one_seed(s, sig_a, ratios) for s in range(NSEEDS)]
    A = lambda key_: np.array([r[key_] for r in R])
    out = dict(sig_a=sig_a, ratios=ratios, nseeds=NSEEDS,
               acc1=[mean_ci(A("acc1")[:, i]) for i in range(len(sig_a))],
               acc2=[mean_ci(A("acc2")[:, i]) for i in range(len(ratios))],
               accb=[mean_ci(A("accb")[:, i]) for i in range(len(ratios))],
               frr=mean_ci(A("frr_both")), zero_effort=mean_ci(A("zero_effort_f1")), t1=mean_ci(A("t1")))
    # natural attacker: m=10 observed packets (error 0.3/sqrt(10)), synthesiser step 0.1 ppm, residual drift 0.05
    out["sig_a_natural"] = float(math.sqrt(SIG_M ** 2 / 10 + 0.1 ** 2 / 12 + 0.05 ** 2))
    # independent analytic prediction of feature-1 acceptance: P(|N(0, sa^2 + 2*sv^2 + se^2)| <= t1)
    sv = SIG_M / math.sqrt(NV_PKT); se = SIG_M / math.sqrt(N_ENROL)
    out["acc1_theory"] = [math.erf(out["t1"][0] / math.sqrt(2 * (sa ** 2 + sv ** 2 + se ** 2))) for sa in sig_a]
    save_json("b09_fingerprint.json", out); return out

def plot(o):
    fig, ax = plt.subplots(1, 2, figsize=(9, 3.4))
    m = o["acc1"]; ax[0].errorbar(o["sig_a"], [x[0] for x in m], yerr=[[x[0]-x[1] for x in m], [x[2]-x[0] for x in m]], color=C["verm"], marker="o", capsize=2, label="simulated forgery acceptance")
    ax[0].plot(o["sig_a"], o["acc1_theory"], "--", color=C["black"], label="analytic Gaussian prediction")
    ax[0].axhline(o["zero_effort"][0], color=C["grey"], ls=":", label="zero-effort impostor"); ax[0].set_xscale("log")
    ax[0].set_xlabel("attacker skew error sigma_a (ppm)"); ax[0].set_ylabel("P(forged skew accepted)"); ax[0].legend(); ax[0].set_title("Feature 1 only")
    r = o["ratios"]
    for lab, key_, c in [("jitter only", "acc2", C["sky"]), ("skew + jitter", "accb", C["blue"])]:
        m = o[key_]; ax[1].errorbar(r, [x[0] for x in m], yerr=[[x[0]-x[1] for x in m], [x[2]-x[0] for x in m]], color=c, marker="o", capsize=2, label=lab)
    ax[1].set_xlabel("attacker jitter floor / victim jitter"); ax[1].set_ylabel("P(forgery accepted)"); ax[1].legend(); ax[1].set_title("Adding the jitter feature (skew forged at 0.05 ppm)")
    save_fig(fig, "b09_fingerprint.png")

if __name__ == "__main__":
    o = run(); plot(o); i = o["sig_a"].index(0.1); j = o["ratios"].index(2.0); j1 = o["ratios"].index(1.0)
    key("B9", f"natural attacker precision {o['sig_a_natural']:.2f} ppm; skew-only forgery accepted {fmt(o['acc1'][o['sig_a'].index(0.1)])} at 0.1 ppm "
              f"(zero-effort {o['zero_effort'][0]:.3f}, FRR {o['frr'][0]:.3f}); adding jitter: floor=2x victim -> {fmt(o['accb'][j])}, floor=1x -> {fmt(o['accb'][j1])}")
