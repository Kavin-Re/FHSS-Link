"""R8 (RED_TEAM idea 19) Red-team scorecard generator. Runs a compact version of each red-team experiment (R1-R7 plus the timing-leak idea 5, copied
from sim/redteam_ladder.py) against two defender configurations (BASELINE = naive choices, HARDENED = the lesson of each experiment) and writes a
scorecard: damage in [0,1] per attack x configuration, verdict (HOLDS < 0.25 <= DEGRADED < 0.6 <= BROKEN), attacker cost tier, heatmap, markdown.
Damage definitions are per row (see ROWS) and are NOT comparable as absolute risk across rows; they say 'how much of the defender's goal was lost'."""
import numpy as np
from _common import *
import exp1_bandit_poison as e1, exp2_learning_rate as e2, exp3_control_plane as e3, exp4_time_push as e4
import exp5_prng_graveyard as e5, exp6_keyfromair_drain as e6, exp7_myopic_jammer as e7

def verdict(d): return "HOLDS" if d < 0.25 else ("DEGRADED" if d < 0.6 else "BROKEN")
def clip01(x): return float(min(1.0, max(0.0, x)))

def timing_leak(tries, w, randomised, seed=1, T=20000):      # copied from sim/redteam_ladder.py (idea 5), unchanged logic
    rng = np.random.default_rng(seed); ok = n = 0
    for k in range(T // 10):
        base = k * 10; off = int(rng.integers(0, 10)) if randomised else 0; n += 1
        for a in range(tries):
            t = base + off + a; jammed = (t % 10) < w
            if rng.random() > (P_JAM if jammed else P_CLEAN): ok += 1; break
    return ok / n

def row_r1(hard):
    kw = dict(eps=0.1, gamma=0.98) if hard else {}
    c = np.mean([e1.run("ts", poison=False, seed=s, **kw)["p2_first300"] for s in range(5)]); p = np.mean([e1.run("ts", poison=True, seed=s, **kw)["p2_first300"] for s in range(5)])
    return clip01((c - p) / c), f"first-300-slot delivery {p:.2f} vs {c:.2f} unpoisoned"

def row_r2(hard):
    kw = dict(gamma=1.0, detect=True) if hard else dict(gamma=1.0)
    L = (10, 20, 6000); v = [np.mean([e2.run(l, T=4000, seed=s, **kw) for s in range(3)]) for l in L]; u = np.mean([e2.run(10, T=4000, seed=s, gamma=1.0, uniform=True) for s in range(3)])
    adv = (v[2] - min(v[:2])) / (v[2] - u)
    return clip01((v[2] - min(v[:2])) / v[2]), f"worst {min(v[:2]):.2f} vs static-jammer {v[2]:.2f} (uniform floor {u:.2f}; {100*adv:.0f}% of learning advantage stripped)"

def row_r3(hard):
    R, D = (5, 100) if hard else (1, 60); n = e3.avg(R, D, "none", T=30000)["avail"]; c = e3.avg(R, D, "control", T=30000)["avail"]
    return clip01(1 - c / n), f"availability {c:.2f} vs {n:.2f}"

def row_r4(hard, r=1.0):
    bad = []
    for s in range(12):
        x = e4.run(r, seed=s); v = x["t_viol"]; d = x["t_det"] if hard else None
        bad.append(v is not None and (d is None or d > v))
    return float(np.mean(bad)), f"{100*np.mean(bad):.0f}% of runs misaligned before any alarm (push {r} ppm)"

def row_r5(hard):
    rng = np.random.default_rng(0)
    if hard:
        key_ = b"k" * 16; seq = [e5.hmac_hop(key_, i) for i in range(600)]; guess = max(range(13), key=lambda c: seq[:300].count(c)); acc = np.mean([g == guess for g in seq[300:]]); lab = "HMAC"
    else:
        x0 = int(rng.integers(e5.M24)); st = e5.lcg_stream(x0, 60); cand, used = e5.lcg_attack(st[:20]); x = int(cand[0]); pred = []
        for i in range(used, 60): x = (e5.A24 * x + e5.C24) % e5.M24; pred.append((x >> 8) % 13)
        acc = float(np.mean([p == q for p, q in zip(pred, st[used:60])])); lab = "LCG24"
    return clip01((acc - 1 / 13) / (1 - 1 / 13)), f"{lab}: future-hop prediction accuracy {acc:.2f} after <=20 hops seen"

def row_r6(hard):
    m = e6.measure(0.1, 0.3); clean = e6.measure(1.0, 0.0)
    accepted = (not hard) or e6.monitor(0.1, 0.3)
    dmg = clip01(1 - m["hmin"]) if accepted else 0.0
    return dmg, ("weak key accepted: min-entropy %.2f bit/bit" % m["hmin"]) if accepted else "monitor aborts key (availability lost, key not weakened)"

def row_r7(hard):
    d = 1.0 if hard else 0.1                                   # latency in dwell units: fast hopping (4x lab5-style) vs slow dwell
    dm = 1 - e7.delivery_cf(1.0, d); return clip01(dm / P_JAM), f"follower delivery {1 - dm:.2f} (latency {d} dwell)"

def row_r8(hard):
    v = timing_leak(3 if hard else 1, 1, hard); return clip01(1 - v), f"critical delivery {v:.2f} ({'randomised, 3 tries' if hard else 'periodic, 1 try'})"

ROWS = [("R1 bandit poisoning", "idea 1", "medium (jams 10 ch at 50% for 1500 slots)", row_r1), ("R2 learning-rate attack", "idea 4", "medium (needs learner memory length)", row_r2),
        ("R3 control-plane jamming", "idea 6", "cheap (5% duty, 1 channel)", row_r3), ("R4 time-pushing", "idea 7", "medium (needs a growing-delay relay)", row_r4),
        ("R5 weak-PRNG schedule", "idea 9", "cheap (8 observed hops, LCG24)", row_r5), ("R6 key-from-air drain", "idea 10", "medium (control environment)", row_r6),
        ("R7 myopic follower jammer", "idea 11", "medium (fast detector)", row_r7), ("R8 timing leak", "idea 5", "cheap (10% airtime)", row_r8)]
BASE_DESC = "Thompson no forgetting; 1 rendezvous ch, D=60; no clock check; LCG24 schedule; fixed-threshold key, no monitor; slow dwell; periodic critical msgs, 1 try"
HARD_DESC = "floor 0.1 + discount 0.98 / switch-detect; 5 rendezvous ch, D=100; skew-rate check; HMAC schedule; entropy monitor; fast hop (latency = 1 dwell); randomised critical msgs, 3 tries"

def build():
    out = []
    for name, idea, cost, f in ROWS:
        b, bn = f(False); h, hn = f(True); out.append(dict(attack=name, idea=idea, cost=cost, baseline=b, hardened=h, base_note=bn, hard_note=hn, base_verdict=verdict(b), hard_verdict=verdict(h)))
    return out

def main():
    sc = build()
    print(f"{'attack':28s} {'cost tier':42s} {'BASELINE':>16s} {'HARDENED':>16s}")
    for r in sc: print(f"{r['attack']:28s} {r['cost']:42s} {r['baseline']:6.2f} {r['base_verdict']:>9s} {r['hardened']:6.2f} {r['hard_verdict']:>9s}")
    fig, ax = plt.subplots(figsize=(6.6, 3.9)); Z = np.array([[r["baseline"], r["hardened"]] for r in sc]); im = ax.imshow(Z, cmap="Reds", vmin=0, vmax=1, aspect="auto"); ax.grid(False)
    ax.set_xticks([0, 1]); ax.set_xticklabels(["BASELINE", "HARDENED"]); ax.set_yticks(range(len(sc))); ax.set_yticklabels([r["attack"] for r in sc], fontsize=7.5)
    for i, r in enumerate(sc):
        for j, k in enumerate(("baseline", "hardened")): ax.text(j, i, f"{r[k]:.2f}\n{verdict(r[k])}", ha="center", va="center", fontsize=6.5, color="white" if r[k] > 0.6 else "black")
    fig.colorbar(im, label="damage (0 = defender goal intact, 1 = lost)"); ax.set_title("R8 red-team scorecard"); save_fig(fig, "r8_scorecard.png")
    md = ["# Red-team scorecard (simulation, own-link model)", "", f"Baseline: {BASE_DESC}.", "", f"Hardened: {HARD_DESC}.", "", "| Attack | Idea | Attacker cost | Baseline damage | Verdict | Hardened damage | Verdict | Evidence (baseline / hardened) |", "|---|---|---|---|---|---|---|---|"]
    for r in sc: md.append(f"| {r['attack']} | {r['idea']} | {r['cost']} | {r['baseline']:.2f} | {r['base_verdict']} | {r['hardened']:.2f} | {r['hard_verdict']} | {r['base_note']} / {r['hard_note']} |")
    open(os.path.join(OUT, "scorecard.md"), "w").write("\n".join(md) + "\n"); save_json("r8_scorecard.json", sc)
    nb = sum(r["base_verdict"] == "BROKEN" for r in sc); nh = sum(r["hard_verdict"] == "BROKEN" for r in sc)
    key("attacks rated BROKEN: baseline vs hardened (of 8)", f"{nb} vs {nh}")
    return sc
if __name__ == "__main__": main()
