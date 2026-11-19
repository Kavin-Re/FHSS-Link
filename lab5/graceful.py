"""Experiment 6 - graceful-degradation curve of the existing ladder (sim/ladder.py) vs a cliff-style baseline (simulation only).

Sweep: jammer strength = number k of the 13 channels jammed (0..12), stationary for the whole run, two jammer shapes:
  static  : channels {0..k-1} every slot (learnable);  random : k random channels each slot (not learnable).
Systems (same traffic as sim/ladder.py: a critical message every 10 slots with a 10-slot deadline; every other slot is bulk data):
  LADDER  : sim/ladder.py run('LADDER') executed unmodified; only its scenario hooks (PHASES, jam_set) are re-pointed at runtime to a stationary k-jammer.
  NORMAL  : sim/ladder.py run('NORMAL'): blind keyed hopping, one attempt, no mode changes (linear, un-protected baseline).
  CLIFF   : LINK-WATCHDOG baseline defined HERE (a strawman, stated as such): blind hopping, 1 attempt, and when the loss rate over the last 50 attempts
            exceeds 30 % the link declares sync loss and is down for 300 slots (re-scan), then restarts with empty history. Typical of a link that
            treats heavy loss as loss-of-lock. Whether real links behave so is not measured here.
Metrics: critical-message delivery and bulk goodput (delivered packets per slot).
"""
import contextlib
import numpy as np
import _common as cm
from _common import C, plt
import adaptive, ladder


@contextlib.contextmanager
def stationary_jammer(k, shape, T):
    saved = (ladder.PHASES, ladder.jam_set)
    ladder.PHASES = [(0, T, "stat")]
    ladder.jam_set = (lambda t, rng, M=13: set(range(k))) if shape == "static" else (lambda t, rng, M=13: set(rng.choice(M, k, replace=False).tolist()) if k else set())
    try: yield
    finally: ladder.PHASES, ladder.jam_set = saved


def ladder_point(policy, k, shape, T=3000, seeds=(1, 2, 3)):
    out = []
    with stationary_jammer(k, shape, T):
        for s in seeds:
            r = ladder.run(policy, seed=s, T=T); out.append((r["stat"]["critical"], r["stat"]["bulk"]))
    return tuple(float(x) for x in np.mean(out, axis=0))


def cliff_run(k, shape, seed=1, T=3000, M=13, thr=0.30, down=300):
    rng = np.random.default_rng(seed); blind = adaptive.Blind(M, np.random.default_rng(seed + 1))
    hist = []; down_left = 0; crit_sent = crit_ok = bulk_ok = 0; pending = None
    for t in range(T):
        if t % 10 == 0: crit_sent += 1; pending = t
        if down_left > 0:
            down_left -= 1; continue
        J = set(range(k)) if shape == "static" else (set(rng.choice(M, k, replace=False).tolist()) if k else set())
        c = blind.pick(); ok = rng.random() > (cm.P_JAM if c in J else cm.P_CLEAN); hist.append(0 if ok else 1)
        if pending is not None and t - pending < 10:
            if ok: crit_ok += 1; pending = None
            else: pending = None      # 1 attempt only (NORMAL mode)
        else: bulk_ok += int(ok)
        if len(hist) >= 50 and np.mean(hist[-50:]) > thr: down_left = down; hist = []
    return crit_ok / max(1, crit_sent), bulk_ok / T


def main(T=3000, seeds=(1, 2, 3)):
    ks = list(range(0, 13)); res = {}; lines = []
    for shape in ("static", "random"):
        res[shape] = {"LADDER": [ladder_point("LADDER", k, shape, T, seeds) for k in ks], "NORMAL": [ladder_point("NORMAL", k, shape, T, seeds) for k in ks],
                      "CLIFF": [tuple(np.mean([cliff_run(k, shape, s, T) for s in seeds], axis=0)) for k in ks]}
        for sysn, v in res[shape].items():
            lines.append(f"{shape:6s} {sysn:7s} critical: " + " ".join(f"{a:.2f}" for a, _ in v)); lines.append(f"{shape:6s} {sysn:7s} bulk    : " + " ".join(f"{b:.2f}" for _, b in v))
    # steepness metrics
    met = {}
    for shape in res:
        for sysn, v in res[shape].items():
            crit = np.array([a for a, _ in v]); drops = -np.diff(crit)
            half = next((k for k, c in zip(ks, crit) if c < 0.5), None)
            met[f"{shape}|{sysn}"] = dict(max_step_drop=float(drops.max()), step_at_k=int(ks[int(drops.argmax())]), k_below_50pct=half, area=float(np.trapezoid(crit, ks) / ks[-1]))
            lines.append(f"{shape:6s} {sysn:7s} max one-step drop {drops.max():.2f} (k={ks[int(drops.argmax())]}->{ks[int(drops.argmax())]+1}), first k with critical<0.5: {half}, mean critical over k: {met[f'{shape}|{sysn}']['area']:.2f}")
    print("\n".join(lines))
    fig, ax = plt.subplots(2, 2, figsize=(11, 7), sharex=True)
    col = dict(LADDER=C["blue"], NORMAL=C["black"], CLIFF=C["verm"])
    for j, shape in enumerate(("static", "random")):
        for sysn in ("LADDER", "NORMAL", "CLIFF"):
            ax[0, j].plot(ks, [a for a, _ in res[shape][sysn]], "-o", ms=3, color=col[sysn], label=sysn); ax[1, j].plot(ks, [b for _, b in res[shape][sysn]], "-o", ms=3, color=col[sysn], label=sysn)
        ax[0, j].set_title(f"{shape} jammer: critical-message delivery"); ax[1, j].set_title(f"{shape} jammer: bulk goodput (packets/slot)"); ax[1, j].set_xlabel("jammed channels k (of 13)")
    ax[0, 0].legend(); ax[0, 0].set_ylabel("delivery"); ax[1, 0].set_ylabel("goodput")
    fig.suptitle("Degradation ladder vs cliff-style link watchdog (watchdog baseline is a defined strawman; 3 seeds x 3000 slots)", fontsize=9)
    cm.save_fig(fig, "fig6_graceful.png"); cm.save_json("exp6_graceful.json", dict(ks=ks, res=res, metrics=met))
    open(cm.os.path.join(cm.OUT, "exp6_graceful.txt"), "w").write("\n".join(lines) + "\n")
    return res, met


if __name__ == "__main__":
    main()
