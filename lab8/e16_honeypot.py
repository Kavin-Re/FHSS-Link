"""E16 (RED_TEAM idea 16): honeypot channels. Simulation only, own link. 13 channels, slot-level.
Defender: real traffic every slot on one channel drawn from a NON-uniform preference (an AFH-style link that favours its best channels):
  REAL_W over 9 good channels, 4 channels (BAIT) are never used for real traffic. Honeypot: on each bait channel a decoy frame is sent with prob RHO per slot.
Jammers (each jams K_J channels per slot, success prob P_JAM=0.95 on a real frame, 0.01 clean leak is ignored; energy 1 unit per jam):
  * FREQ  frequency-counting jammer: exponentially decayed activity histogram (decay 0.99), jams the K_J highest (eps-greedy 5%).
  * EXP3  EXP3 bandit (gamma 0.1) over channels; reward 1 if it saw activity on the channel it jammed (real or decoy).
  Both observe 'activity' on a channel; a decoy is indistinguishable from a real frame with prob 1 - Q_D. A DISCERNING jammer (Q_D) recognises a
  decoy and gets no reward / no count from it (Q_D=1: perfect discrimination). Q_D is the honest negative-result knob.
Metrics over the last 3/4 of 4000 slots: real delivery (1 - P_JAM * fraction of real frames jammed), jammer wasted jams (jams on channels with no real frame),
decoy energy (frames sent per slot) vs jammer energy. Defensive lesson: decoys only buy protection while they are indistinguishable from real traffic."""
import sys
import numpy as np
from _common import *

K = 13
REAL_W = np.array([.25, .20, .15, .10, .10, .05, .05, .05, .05]); BAIT = np.arange(9, 13)
REAL_P = np.concatenate([REAL_W, np.zeros(4)])
K_J, P_JAM, T = 2, 0.95, 4000

def run(seed, kind, rho, qd, T=T, kj=K_J):
    rng = np.random.default_rng(seed)
    cnt = np.zeros(K); w = np.ones(K); gamma = 0.1
    real = rng.choice(K, T, p=REAL_P); decoy = (rng.random((T, 4)) < rho)
    lost = 0; wasted = 0; jams = 0; n_real = 0; start = T // 4
    for t in range(T):
        if kind == "freq":
            if rng.random() < 0.05: ch = rng.choice(K, kj, replace=False)
            else: ch = np.argsort(-(cnt + 1e-9 * rng.random(K)))[:kj]
        else:
            p = (1 - gamma) * w / w.sum() + gamma / K
            ch = rng.choice(K, kj, replace=False, p=p)
        act = np.zeros(K); act[real[t]] = 1.0
        dec = np.zeros(K); dec[BAIT[decoy[t]]] = 1.0
        seen_dec = dec * (rng.random(K) > qd)                         # decoys the jammer fails to recognise
        obs = np.maximum(act, seen_dec)
        if kind == "freq":
            cnt *= 0.99; cnt += obs
        else:
            for c in ch:
                x = obs[c] / p[c]; w[c] *= np.exp(gamma * x / K)
            w /= w.max()
        if t >= start:
            hit = real[t] in ch; jams += kj; n_real += 1
            lost += hit * P_JAM
            wasted += int((act[ch] == 0).sum())
    return dict(deliv=1 - lost / n_real, wasted_frac=wasted / jams, decoy_per_slot=float(rho * 4))

def main(nseeds=20):
    cfgs = [("none", 0.0, 0.0), ("rho=.1", .1, 0.0), ("rho=.3", .3, 0.0), ("rho=.6", .6, 0.0), ("rho=1", 1.0, 0.0), ("rho=.6, Q_D=.5", .6, .5), ("rho=.6, Q_D=1", .6, 1.0)]
    res = {}
    print(f"E16 {nseeds} seeds x {T} slots, jammer jams {K_J} of 13 channels/slot, success {P_JAM}. real preference top-2 mass {REAL_W[:2].sum():.2f}")
    print("  config | " + " | ".join(f"{k} delivery / wasted jams" for k in ("freq", "exp3")) + " | decoy frames per slot")
    for name, rho, qd in cfgs:
        line = f"  {name:16s}"
        for kind in ("freq", "exp3"):
            rs = [run(s, kind, rho, qd) for s in range(nseeds)]; res[(name, kind)] = rs
            line += f" | {fmt([r['deliv'] for r in rs],3)} / {fmt([r['wasted_frac'] for r in rs],2)}"
        print(line + f" | {rho*4:.1f}", flush=True)
    uni = 1 - P_JAM * K_J / K
    print(f"  reference: jamming {K_J} random channels hurts a uniform hopper by {P_JAM*K_J/K:.3f}; ideal oracle on this preference loses {P_JAM*REAL_W[:2].sum():.3f}")
    d = {k: [r["deliv"] for r in v] for k, v in res.items()}
    for kind in ("freq", "exp3"):
        m, h = paired_ci(d[("rho=.6", kind)], d[("none", kind)]); print(f"  paired gain rho=.6 vs none ({kind}): {m:+.3f} +/- {h:.3f}")
        m, h = paired_ci(d[("rho=.6, Q_D=1", kind)], d[("none", kind)]); print(f"  paired gain rho=.6 against a discerning jammer ({kind}): {m:+.3f} +/- {h:.3f}")
    key("real delivery, none -> honeypot rho=.6 (freq jammer)", f"{fmt(d[('none','freq')])} -> {fmt(d[('rho=.6','freq')])}")
    key("real delivery, none -> honeypot rho=.6 (EXP3 jammer)", f"{fmt(d[('none','exp3')])} -> {fmt(d[('rho=.6','exp3')])}")
    key("honeypot vs discerning jammer (Q_D=1), freq", fmt(d[("rho=.6, Q_D=1", "freq")]))
    save_json("e16_honeypot.json", {f"{a}|{b}": v for (a, b), v in res.items()})
    fig, ax = plt.subplots(figsize=(8.5, 3.8)); x = np.arange(len(cfgs)); wd = .38
    for j, (kind, c) in enumerate((("freq", C["verm"]), ("exp3", C["blue"]))):
        ms = [ci95(d[(n, kind)]) for n, _, _ in cfgs]; ax.bar(x + (j - .5) * wd, [m[0] for m in ms], wd, yerr=[m[1] for m in ms], color=c, label=kind, capsize=2)
    ax.set_xticks(x); ax.set_xticklabels([c[0] for c in cfgs], rotation=20); ax.set_ylabel("real-frame delivery"); ax.set_ylim(0.4, 1.0); ax.legend()
    save_fig(fig, "e16_honeypot.png")

if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
