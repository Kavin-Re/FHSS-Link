"""B14 Crypto denial of service (simulation): a flood of invalid packets burns a small MCU's CPU on MAC checks.
Single-core FIFO queue (capacity QCAP), Poisson arrivals. Legit rate LAM_L; attacker rate R of forged packets.
Cost model (ASSUMED, labelled; cycles on a Cortex-M4-class core at F_CPU): full HMAC-SHA256 check C_MAC, cheap structural check
(length, epoch/seq window) C_STRUCT, 16-bit keyed truncated pre-tag (SipHash-like) C_PRE.
Defences: none | struct filter (kills random junk with prob P_STRUCT, not replays/well-formed forgeries) | struct+pre-tag (a forgery passes with 2^-16) | + token-bucket rate limit.
Attacker types: 'junk' (random bytes), 'wellformed' (valid header/seq, random tag)."""
import numpy as np
from _common import *

F_CPU, C_MAC, C_STRUCT, C_PRE = 48e6, 20000, 150, 1800     # assumed: MAC ~0.42 ms
LAM_L, QCAP, TSIM = 20.0, 8, 20.0
P_STRUCT_JUNK = 0.97        # fraction of random junk rejected by length/sync/seq-window check

def sim(seed, R, defence, attacker, rate_limit=None):
    rng = np.random.default_rng(seed)
    nl, na = rng.poisson(LAM_L * TSIM), rng.poisson(R * TSIM)
    t = np.concatenate([np.sort(rng.random(nl) * TSIM), np.sort(rng.random(na) * TSIM)]); legit = np.r_[np.ones(nl, bool), np.zeros(na, bool)]
    o = np.argsort(t); t, legit = t[o], legit[o]
    u = rng.random(len(t)); busy_until = 0.0; queue_ends = []   # completion times of queued jobs
    served = 0; tokens = rate_limit[1] if rate_limit else 0; last = 0.0; cpu = 0.0
    for ti, li, ui in zip(t, legit, u):
        if rate_limit and not li:    # per-claimed-source token bucket on attacker traffic only if identifiable (spoof-able in reality: see caveat)
            tokens = min(rate_limit[1], tokens + (ti - last) * rate_limit[0]); last = ti
            if tokens < 1: continue
            tokens -= 1
        # admission: structural check is done in the ISR-level fast path (cost counted, queue not used)
        if defence == "none": cost = C_MAC
        else:
            cost = C_STRUCT
            passes_struct = True if li else (attacker == "wellformed" or ui > P_STRUCT_JUNK)
            if passes_struct:
                if defence == "struct": cost += C_MAC
                else:
                    cost += C_PRE
                    if li or rng.random() < 2.0 ** -16: cost += C_MAC
        s = cost / F_CPU
        queue_ends = [e for e in queue_ends if e > ti]
        if len(queue_ends) >= QCAP: continue          # dropped (legit or not)
        start = max(ti, queue_ends[-1] if queue_ends else ti); queue_ends.append(start + s); cpu += s
        if li and start + s <= TSIM: served += 1
    return served / max(nl, 1), cpu / TSIM

def curve(defence, attacker, rates, rl=None):
    out = []
    for R in rates:
        x = [sim(s, R, defence, attacker, rl) for s in range(NSEEDS)]
        out.append(dict(R=R, good=mean_ci([a for a, _ in x]), util=mean_ci([b for _, b in x])))
    return out

def run():
    rates = [0, 50, 100, 200, 400, 800, 1600, 3200, 6400]
    cfg = {"none/junk": ("none", "junk", None), "struct/junk": ("struct", "junk", None), "struct/wellformed": ("struct", "wellformed", None),
           "struct+pretag/wellformed": ("pretag", "wellformed", None)}
    res = {k: curve(*v[:2], rates, v[2]) for k, v in cfg.items()}
    cap = F_CPU / C_MAC            # packets/s the MAC engine can verify
    out = dict(rates=rates, res=res, cap_mac_per_s=cap, assumptions=dict(F_CPU=F_CPU, C_MAC=C_MAC, C_STRUCT=C_STRUCT, C_PRE=C_PRE, QCAP=QCAP, LAM_L=LAM_L, TSIM=TSIM, P_STRUCT_JUNK=P_STRUCT_JUNK), nseeds=NSEEDS)
    save_json("b14_dos.json", out); return out

def plot(o):
    fig, ax = plt.subplots(1, 2, figsize=(9, 3.4)); cs = [C["verm"], C["orange"], C["blue"], C["green"]]
    for (k, v), c in zip(o["res"].items(), cs):
        R = [max(x["R"], 10) for x in v]
        for a, key_ in zip(ax, ("good", "util")):
            m = [x[key_] for x in v]; a.errorbar(R, [x[0] for x in m], yerr=[[max(0, x[0]-x[1]) for x in m], [max(0, x[2]-x[0]) for x in m]], color=c, marker="o", capsize=2, label=k)
    for a, yl in zip(ax, ("legit packets served", "CPU utilisation")): a.set_xscale("log"); a.set_xlabel("attacker packets/s"); a.set_ylabel(yl)
    ax[0].axvline(o["cap_mac_per_s"] - LAM_L, color=C["grey"], ls=":"); ax[0].legend(); ax[0].set_title("Legit goodput under flood (dotted: MAC capacity)")
    save_fig(fig, "b14_dos.png")

if __name__ == "__main__":
    o = run(); plot(o); r = o["res"]; i = o["rates"].index(3200)
    key("B14", f"MAC capacity {o['cap_mac_per_s']:.0f} pkt/s; at 3200 forged pkt/s legit served: no filter {fmt(r['none/junk'][i]['good'])}, struct filter vs junk {fmt(r['struct/junk'][i]['good'])}, vs well-formed forgeries {fmt(r['struct/wellformed'][i]['good'])}, +16-bit pre-tag {fmt(r['struct+pretag/wellformed'][i]['good'])}")
