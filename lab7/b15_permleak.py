"""Beyond #15: permutation-epoch hopping leaks (simulation only). Some regimes require every channel to be visited once per epoch of M slots.
An observer who sees the channels of PAST hops (not the key) can then guess the next one among the M-i channels not yet visited in this epoch.
Schemes (M=13, keyed pseudo-random choices modelled as true random):
  iid        uniform every slot (no epoch rule)
  perm       a fresh random permutation per epoch of M slots
  excl(L)    uniform over channels not used in the last L slots (no coverage guarantee)
  guard(L,W) excl(L) plus a coverage guarantee: a channel idle for W-1 slots is forced (max gap <= W)    <- "keyed overlapping epochs"
Attackers (rule-aware, i.e. they know the scheme but not the key):
  perm  -> self-synchronising: tracks the visited set, resets when it is full or a repeat occurs; guesses uniformly among unvisited
  excl  -> guesses uniformly among channels not in the last L slots
  guard -> guesses the forced channel if one is overdue, else as excl
Metric: one-shot hit probability of a reactive 1-channel jammer that aims at the predicted channel; coverage: max gap between visits of a channel."""
import numpy as np
from _common import *

M = 13
P_JAM, P_CLEAN = 0.95, 0.01

def gen(scheme, n, rng, L=0, W=0):
    """Returns channel sequence. scheme in iid, perm, excl, guard."""
    if scheme == "iid": return rng.integers(0, M, n)
    if scheme == "perm":
        out = np.empty(n, dtype=int)
        for e in range(0, n, M):
            out[e:e + M] = rng.permutation(M)[: min(M, n - e)]
        return out
    seq = []; last_used = np.full(M, -1)      # slot of last use
    for t in range(n):
        allowed = np.ones(M, bool)
        for c in seq[-L:] if L else []: allowed[c] = False
        idle = t - last_used                    # slots since last use (last_used=-1 -> t+1)
        c = None
        if scheme == "guard":
            overdue = np.flatnonzero(idle >= W)
            if len(overdue): c = int(overdue[np.argmax(idle[overdue])])
        if c is None: c = int(rng.choice(np.flatnonzero(allowed)))
        seq.append(c); last_used[c] = t
    return np.array(seq)

def attack_hit_rate(scheme, seq, L=0, W=0, rng=None):
    """Fraction of slots (after warm-up) where the rule-aware attacker's single guess equals the next channel."""
    hits = tot = 0; visited = set(); n = len(seq)
    last_used = np.full(M, -1)
    for t in range(n):
        if t > 4 * M:
            if scheme == "iid": g = int(rng.integers(M))
            elif scheme == "perm":
                cand = [c for c in range(M) if c not in visited]
                g = int(rng.choice(cand)) if cand else int(rng.integers(M))
            else:
                allowed = np.ones(M, bool)
                for c in seq[max(0, t - L):t]: allowed[c] = False
                g = None
                if scheme == "guard":
                    idle = t - last_used; od = np.flatnonzero(idle >= W)
                    if len(od): g = int(od[np.argmax(idle[od])])
                if g is None: g = int(rng.choice(np.flatnonzero(allowed)))
            hits += (g == seq[t]); tot += 1
        c = int(seq[t])
        if scheme == "perm":
            if c in visited: visited = set()
            visited.add(c)
            if len(visited) == M: visited = set()
        last_used[c] = t
    return hits / tot

def max_gap(seq):
    gaps = []
    for c in range(M):
        pos = np.flatnonzero(seq == c)
        if len(pos) > 1: gaps.append(np.diff(pos).max())
    return int(max(gaps))

def run(fast=False, seed=2):
    rng = np.random.default_rng(seed)
    n = 20000 if fast else 120000
    cfgs = [("iid", dict()), ("perm", dict()), ("excl", dict(L=3)), ("excl", dict(L=6)), ("excl", dict(L=9)), ("guard", dict(L=6, W=2 * M)), ("guard", dict(L=9, W=2 * M))]
    res = []
    for sch, kw in cfgs:
        seq = gen(sch, n, rng, **kw)
        hit = attack_hit_rate(sch, seq, rng=rng, **kw)
        freq = np.bincount(seq, minlength=M) / n
        delivery = 1 - ((hit) * P_JAM + (1 - hit) * P_CLEAN)         # 1-channel jammer aimed at the guess, jams only that channel
        res.append(dict(scheme=sch, **kw, hit=hit, delivery=delivery, max_gap=max_gap(seq), freq_dev=float(np.abs(freq - 1 / M).max())))
    front = []
    nf = 15000 if fast else 40000
    for W in (26, 32, 39, 52, 78):
        for L in (3, 6):
            seq = gen("guard", nf, rng, L=L, W=W)
            front.append(dict(L=L, W=W, hit=attack_hit_rate("guard", seq, L=L, W=W, rng=rng), max_gap=max_gap(seq)))
    harmonic = float(sum(1 / (M - i) for i in range(M)) / M)
    return dict(M=M, n=n, results=res, theory_perm=harmonic, theory_iid=1 / M, frontier=front)

def label(r):
    return r["scheme"] + (f"(L={r['L']})" if "L" in r and r["scheme"] == "excl" else "") + (f"(L={r['L']},W={r['W']})" if r["scheme"] == "guard" else "")

def main():
    out = run()
    print(f"theory: iid 1/M = {out['theory_iid']:.4f}; permutation epochs H_M/M = {out['theory_perm']:.4f}")
    for r in out["results"]:
        print(f"  {label(r):18s} attacker hit {r['hit']:.4f}  delivery vs aimed 1-channel jammer {r['delivery']:.3f}  max gap {r['max_gap']:3d}  max |freq-1/M| {r['freq_dev']:.4f}")
    byname0 = {label(r): r for r in out['results']}
    fig, ax = plt.subplots(1, 3, figsize=(14, 3.5))
    names = [label(r) for r in out["results"]]; hits = [r["hit"] for r in out["results"]]
    cols = [C["grey"], C["verm"], C["sky"], C["sky"], C["sky"], C["blue"], C["blue"]]
    ax[0].barh(names, hits, color=cols); ax[0].axvline(1 / M, color="k", ls=":"); ax[0].set_xlabel("attacker one-shot hit probability (dotted: 1/M)"); ax[0].invert_yaxis()
    i = np.arange(M)
    ax[1].plot(i + 1, 1 / (M - i), "o-", color=C["verm"], label="permutation epoch: 1/(M-i)")
    ax[1].axhline(1 / M, color=C["grey"], ls=":", label="iid: 1/M"); ax[1].set_xlabel("position i+1 inside the epoch"); ax[1].set_ylabel("attacker guess probability"); ax[1].legend()
    for L, c in ((3, C["sky"]), (6, C["blue"])):
        pts = [(f["max_gap"], f["hit"]) for f in out["frontier"] if f["L"] == L]
        ax[2].plot(*zip(*pts), "o-", color=c, label=f"guard L={L}, W=26..78")
    ax[2].plot([byname0["perm"]["max_gap"]], [byname0["perm"]["hit"]], "s", color=C["verm"], ms=9, label="permutation epochs")
    ax[2].axhline(1 / M, color=C["grey"], ls=":"); ax[2].set_xlabel("max gap between visits of a channel (slots)"); ax[2].set_ylabel("attacker hit probability"); ax[2].legend(); ax[2].set_title("leak vs coverage guarantee")
    save_fig(fig, "b15_permleak.png"); save_json("b15_permleak.json", out)
    byname = {label(r): r for r in out["results"]}
    g = byname["guard(L=6,W=26)"]
    f39 = [f for f in out["frontier"] if f["L"] == 3 and f["W"] == 39][0]
    print("frontier:", [(f["L"], f["W"], round(f["hit"], 3), f["max_gap"]) for f in out["frontier"]])
    key("B15", f"permutation epochs: attacker guesses {byname['perm']['hit']:.3f} vs {byname['iid']['hit']:.3f} for iid ({byname['perm']['hit']/byname['iid']['hit']:.2f}x; theory {out['theory_perm']:.3f}); keyed guard(L=6,W=26) holds {g['hit']:.3f} with max channel gap {g['max_gap']} slots (perm epochs: {byname['perm']['max_gap']}); guard(L=3,W=39) {f39['hit']:.3f} at gap {f39['max_gap']}")
if __name__ == "__main__":
    main()
