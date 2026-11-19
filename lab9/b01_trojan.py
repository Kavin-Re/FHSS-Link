"""B1 Hardware-trojan hunt in a toy gate-level model of a hop-channel mapper (simulation only).
Golden netlist: 16 state/key input bits -> 6 channel bits through ~120 random 2-input gates.
Trojan: AND of k internal-net literals (rare trigger) XORed into output bit 0.
Three hunters: random-vector test (golden vs trojan outputs), toggle-rate statistics, exhaustive equivalence."""
import numpy as np
from _common import *

NIN, NG = 16, 120
OPS = ["AND", "OR", "XOR", "NAND", "NOR"]
def gate(op, a, b):
    return {"AND": a & b, "OR": a | b, "XOR": a ^ b, "NAND": ~(a & b), "NOR": ~(a | b)}[op]

def make_netlist(rng):
    gates = []
    for g in range(NG):
        n = NIN + g
        lo = max(0, n - 40)
        a, b = rng.integers(lo, n, 2)
        while b == a: b = rng.integers(lo, n)
        gates.append((OPS[rng.integers(len(OPS))], int(a), int(b)))
    return gates

def simulate(gates, X):
    """X: (nv, NIN) bool -> (nets, nv) bool, bit-parallel over vectors."""
    nets = [X[:, i] for i in range(NIN)]
    for op, a, b in gates: nets.append(gate(op, nets[a], nets[b]))
    return np.array(nets)

def add_trojan(gates, lits):
    """lits: list of (net, polarity). Returns trojaned gate list, trigger net, payload net, output nets."""
    g = list(gates); base = NIN + len(g)
    lit_nets = []
    for net, pol in lits:
        if pol: lit_nets.append(net)
        else: g.append(("NAND", net, net)); lit_nets.append(NIN + len(g) - 1)   # NOT via NAND(x,x)
    cur = lit_nets[0]
    for nx in lit_nets[1:]:
        g.append(("AND", cur, nx)); cur = NIN + len(g) - 1
    trig = cur
    return g, trig

ALLX = ((np.arange(1 << NIN)[:, None] >> np.arange(NIN)) & 1).astype(bool)

def outputs(gates, X, out_nets, payload_trig=None):
    nets = simulate(gates, X)
    o = nets[out_nets].copy()
    if payload_trig is not None: o[0] = o[0] ^ nets[payload_trig]
    return o, nets

def one_seed(seed, k, ns, trials=20, M=4096):
    rng = np.random.default_rng(1000 * seed + k)
    gold = make_netlist(rng); out_nets = list(range(NIN + NG - 6, NIN + NG))
    og, netsg = outputs(gold, ALLX, out_nets)
    prob = netsg.mean(1)
    cand = [i for i in range(NIN, NIN + NG) if 0.2 <= prob[i] <= 0.8 and i not in out_nets]
    sel = rng.choice(cand, k, replace=False)
    xstar = int(rng.integers(0, 1 << NIN))           # polarities chosen so that the trigger is satisfiable by at least one input
    lits = [(int(n), bool(netsg[n, xstar])) for n in sel]
    tg, trig = add_trojan(gold, lits)
    ot, nets_t = outputs(tg, ALLX, out_nets, payload_trig=trig)
    differs = (og != ot).any(0)                    # per input vector: does trojan change output?
    p = float(differs.mean())
    res = dict(seed=seed, k=k, p=p, exhaustive_detects=bool(differs.any()))
    # random-vector detection (sampling with replacement from the input space)
    det = {}
    for N in ns:
        hits = [differs[rng.integers(0, 1 << NIN, N)].any() for _ in range(trials)]
        det[N] = float(np.mean(hits))
    res["det"] = det
    # theory-calibrated point: N = ln2/p -> expect 0.5
    if p > 0:
        N50 = max(1, int(round(np.log(2) / p)))
        res["det50"] = float(np.mean([differs[rng.integers(0, 1 << NIN, N50)].any() for _ in range(trials * 5)]))
        res["N90_theory"] = float(np.log(10) / p)
    # toggle statistics on a random vector stream
    Xs = rng.integers(0, 2, (M, NIN)).astype(bool)
    _, ng_ = outputs(gold, Xs, out_nets); _, nt_ = outputs(tg, Xs, out_nets, payload_trig=trig)
    tog_g = (ng_[:, 1:] != ng_[:, :-1]).sum(1); tog_t = (nt_[:, 1:] != nt_[:, :-1]).sum(1)
    thr = 0.01 * M
    fp = int((tog_g[NIN:] <= thr).sum())            # natural rare/constant nets in the golden design
    trojan_nets = list(range(NIN + NG, len(tog_t)))
    res["toggle_fp_golden"] = fp
    res["toggle_flag"] = bool(tog_t[trig] <= thr)
    return res

def run(fast=False):
    ks = [4, 8, 12, 16, 20]; ns = [100, 1000, 10000]
    seeds = range(NSEEDS if not fast else 20)
    rows = {k: [one_seed(s, k, ns) for s in seeds] for k in ks}
    summ = {}
    for k in ks:
        r = rows[k]; pz = [x["p"] for x in r]
        live = [x for x in r if x["p"] > 0]
        summ[k] = dict(
            p_median=float(np.median(pz)), n_unactivatable=int(sum(1 for x in r if x["p"] == 0)),
            det={N: mean_ci([x["det"][N] for x in r]) for N in ns},
            det50=mean_ci([x["det50"] for x in live]) if live else None,
            toggle=wilson(sum(x["toggle_flag"] for x in live), len(live)) if live else None,
            toggle_fp=mean_ci([x["toggle_fp_golden"] for x in r]),
            exhaustive=wilson(sum(x["exhaustive_detects"] for x in live), len(live)) if live else None,
            N90_median=float(np.median([x["N90_theory"] for x in live])) if live else None)
    out = dict(ks=ks, ns=ns, summ={str(k): v for k, v in summ.items()}, nseeds=len(list(seeds)))
    save_json("b01_trojan.json", out); return out, summ

def plot(summ, ks, ns):
    fig, ax = plt.subplots(1, 2, figsize=(9, 3.4))
    for N, c in zip(ns, [C["sky"], C["blue"], C["verm"]]):
        m = [summ[k]["det"][N] for k in ks]
        ax[0].errorbar(ks, [x[0] for x in m], yerr=[[x[0]-x[1] for x in m], [x[2]-x[0] for x in m]], color=c, marker="o", capsize=2, label=f"N={N} random vectors")
    ax[0].set_xlabel("trigger width k (literals ANDed)"); ax[0].set_ylabel("P(random test exposes trojan)"); ax[0].legend()
    ax[0].set_title("Random-vector escape grows with trigger width")
    tg = [summ[k]["toggle"][0] if summ[k]["toggle"] else 0 for k in ks]
    ax[1].plot(ks, tg, "s-", color=C["green"], label="toggle-rate flag (netlist access)")
    ax[1].plot(ks, [summ[k]["det"][1000][0] for k in ks], "o-", color=C["blue"], label="random test, N=1000")
    ax[1].set_xlabel("trigger width k"); ax[1].set_ylabel("detection rate"); ax[1].legend(); ax[1].set_title("Complementary hunters")
    save_fig(fig, "b01_trojan.png")

if __name__ == "__main__":
    out, summ = run(); ks, ns = out["ks"], out["ns"]; plot(summ, ks, ns)
    k = 20
    key("B1", f"k={k}: median trigger prob {summ[k]['p_median']:.2e} (naive 2^-k = {2.0**-k:.1e}; net correlation makes it ~{summ[k]['p_median']*2**k:.0f}x commoner) -> N90 ~ {summ[k]['N90_median']:.0f} vectors; "
              f"random test N=1000 detects {fmt(summ[k]['det'][1000])}; toggle flag {fmt(summ[k]['toggle'])}; "
              f"golden natural rare nets {summ[k]['toggle_fp'][0]:.1f}/net-set")
