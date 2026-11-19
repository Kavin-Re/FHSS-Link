"""Ideas 18 + 29: graceful-degradation ladder with an explainable decision log.
Modes: NORMAL (blind keyed hop, 1 attempt) < ADAPT (Thompson channel learning, critical gets 3 attempts)
       < CODED (blind hop, bulk uses (7,4) erasure blocks, critical gets 5 attempts) < SURVIVAL (no bulk, critical gets up to 10 attempts).
Traffic: a CRITICAL message (heartbeat / stop command) every 10 slots with a 10-slot deadline; every other slot is BULK data.
Controller: observed loss rate over the last 50 attempts; upgrade at once, downgrade only after 100 calm slots (hysteresis).
Scenario (10,000 slots): 0-2000 clean | 2000-4000 static 2 channels | 4000-6000 wideband 8 of 13 channels | 6000-8000 random 4 channels per slot | 8000-10000 clean."""
import numpy as np
from adaptive import Blind, Thompson

MODES = ["NORMAL", "ADAPT", "CODED", "SURVIVAL"]; CRIT_TRIES = {"NORMAL": 1, "ADAPT": 3, "CODED": 5, "SURVIVAL": 10}
PHASES = [(0, 2000, "clean"), (2000, 4000, "static-2"), (4000, 6000, "wide-8of13"), (6000, 8000, "random-4"), (8000, 10000, "clean")]

def jam_set(t, rng, M=13):
    for a, b, name in PHASES:
        if a <= t < b:
            if name == "static-2": return {0, 1}
            if name == "wide-8of13": return set(range(8))
            if name == "random-4": return set(rng.choice(M, 4, replace=False).tolist())
    return set()

def phase_name(t):
    for a, b, n in PHASES:
        if a <= t < b: return n

def run(policy, seed=1, M=13, T=10000, p_jam=0.95, p_clean=0.01, log=None):
    rng = np.random.default_rng(seed); blind = Blind(M, np.random.default_rng(seed + 1)); ts = Thompson(M, np.random.default_rng(seed + 2))
    mode = "NORMAL" if policy == "LADDER" else policy; hist = []; calm = 0; switches = 0
    crit_pending = None; crit_tries = 0
    crit_sent = {n: 0 for _, _, n in PHASES}; crit_ok = dict(crit_sent); bulk_ok = dict(crit_sent); bulk_slots = dict(crit_sent)
    blk = []; per_phase_slots = dict(crit_sent)
    lostch = []
    for t in range(T):
        ph = phase_name(t); per_phase_slots[ph] += 1
        J = jam_set(t, rng, M)
        if t % 10 == 0:
            if crit_pending is not None: pass     # missed deadline (already counted as sent, not ok)
            crit_pending = t; crit_tries = 0; crit_sent[ph] += 1
        c = ts.pick() if mode in ("ADAPT",) else blind.pick()
        ok = rng.random() > (p_jam if c in J else p_clean)
        ts.update(c, float(ok)); blind.update(c, float(ok)); hist.append(0 if ok else 1)
        if not ok: lostch.append(c)
        if crit_pending is not None and crit_tries < CRIT_TRIES[mode] and t - crit_pending < 10:
            crit_tries += 1
            if ok: crit_ok[crit_pending and phase_name(crit_pending) or ph] += 1; crit_pending = None
        elif mode != "SURVIVAL":
            bulk_slots[ph] += 1
            if mode == "CODED":
                blk.append(ok)
                if len(blk) == 7:
                    if sum(blk) >= 4: bulk_ok[ph] += 4
                    blk = []
            else: bulk_ok[ph] += int(ok)
        if policy == "LADDER":
            loss = np.mean(hist[-50:]) if len(hist) >= 20 else 0.0
            want = 0 if loss < 0.08 else 1 if loss < 0.25 else 2 if loss < 0.55 else 3
            cur = MODES.index(mode)
            if want > cur:
                if log is not None:
                    top = np.bincount(lostch[-50:], minlength=M); tops = np.argsort(-top)[:2].tolist()
                    log.append(f"slot {t} [{ph}]: {mode} -> {MODES[want]} because loss {loss:.0%} over the last 50 attempts; most-hit channels {tops}")
                mode = MODES[want]; calm = 0; switches += 1
            elif want < cur:
                # ADAPT hides losses by avoiding bad channels, so low loss alone does not mean the jammer left: stay while the learner still avoids channels
                still_avoiding = mode == "ADAPT" and (ts.a / (ts.a + ts.b)).min() < 0.6
                calm = 0 if still_avoiding else calm + 1
                if calm >= 100:
                    if log is not None: log.append(f"slot {t} [{ph}]: {mode} -> {MODES[want]} because loss fell to {loss:.0%} and stayed low for 100 slots")
                    mode = MODES[want]; calm = 0; switches += 1
            else: calm = 0
    out = {n: dict(critical=crit_ok[n] / max(1, crit_sent[n]), bulk=bulk_ok[n] / max(1, per_phase_slots[n])) for n in crit_sent}
    out["switches"] = switches
    return out

if __name__ == "__main__":
    import json
    names = [n for _, _, n in PHASES]; agg = {}
    print("critical-message delivery / bulk goodput (packets per slot), mean over 3 seeds; phases:", ", ".join(dict.fromkeys(names)))
    for pol in ("NORMAL", "ADAPT", "CODED", "SURVIVAL", "LADDER"):
        rs = [run(pol, seed=s) for s in (1, 2, 3)]
        agg[pol] = {n: dict(critical=float(np.mean([r[n]["critical"] for r in rs])), bulk=float(np.mean([r[n]["bulk"] for r in rs]))) for n in dict.fromkeys(names)}; agg[pol]['switches'] = float(np.mean([r['switches'] for r in rs]))
        # phase 'clean' appears twice: dict merges keys, so average both clean stretches properly below
        print(f"{pol:9s}", " | ".join(f"{n}: {agg[pol][n]['critical']:.2f}/{agg[pol][n]['bulk']:.2f}" for n in agg[pol] if n != 'switches') + f" | mode switches {agg[pol]['switches']:.0f}")
    log = []; run("LADDER", seed=1, log=log)
    open("../logs/ladder_decisions.txt", "w").write("\n".join(log) + "\n"); print("\n".join(log[:12]))
    json.dump(agg, open("figures/ladder.json", "w"), indent=1)
