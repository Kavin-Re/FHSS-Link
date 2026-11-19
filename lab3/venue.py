"""Congested-venue model: N co-located hopping links + background Wi-Fi, analytic (slotted-ALOHA-like) and Monte Carlo.

MODEL / ASSUMPTIONS
- Time is slotted and ALL links share slot boundaries (the pessimistic aligned case; unaligned transmissions would roughly double the
  vulnerable window). Each link (a pair of nodes) hops independently and uniformly over the same M channels with its own schedule
  (a keyed PRF schedule per pair behaves like this); no coordination between links.
- In every slot a link sends a CRITICAL packet with probability tau_c (default 0.1: one per 10 slots, as in sim/ladder.py), a BULK packet with
  probability tau_b (default 0.5), else it is idle. A packet is lost if any other link sends on the same channel in that slot (no capture effect),
  if background Wi-Fi occupies that channel in that slot (independent per channel and slot with probability b, default 0.2: an average, uniform
  assumption), or by residual noise with probability p_clean = 0.01 (same as the other sims).
- Retransmissions: a critical MESSAGE gets R attempts (default 3) treated as independent attempts: delivery = 1-(1-p)^R. The extra load that
  retries create is NOT added back into tau (optimistic at high load).
- PRIORITY ('first pick'): critical senders choose their channel first (in a short mini-slot ahead of bulk). Bulk senders sense that mini-slot:
  with probability rho (default 0.9) a bulk sender avoids all channels already taken by critical senders (chooses uniformly among the rest);
  with probability 1-rho sensing fails and it picks uniformly over all M channels. Critical senders still collide with each other.
  Analytic critical result is exact for this model; the bulk result under priority is an approximation (bulk senders avoid the critical-occupied
  channels, which concentrates them on the remaining ones) and is checked against Monte Carlo.
- Analytic per-attempt success: plain  p = (1 - P_coll) (1-b) (1-p_clean), P_coll = 1 - (1 - tau/M)^(N-1), tau = tau_c + tau_b.
  priority, critical: P_coll = 1 - (1 - tau_c/M)^(N-1) (1 - (1-rho) tau_b/M)^(N-1).
- Jain fairness index J = (sum x)^2 / (n sum x^2) over links; 1 = perfectly fair. With identical links and uniform hopping the system is symmetric
  so J is near 1 by construction; the figure uses links with unequal bulk loads (tau_b drawn uniformly in [0.1,0.9]) to see how service ratio vs throughput behave.
Run: python3 venue.py
"""
import os, math
import numpy as np

P_CLEAN = 0.01
DEF = dict(M=13, tau_c=0.1, tau_b=0.5, b=0.2, rho=0.9, R=3)


# ----------------------------------------------------------------- analytic
def p_coll_plain(N, M, tau): return 1 - (1 - tau / M) ** (N - 1)
def attempt_success(pcoll, b): return (1 - pcoll) * (1 - b) * (1 - P_CLEAN)


def analytic(N, M=13, tau_c=0.1, tau_b=0.5, b=0.2, rho=0.9, R=3, priority=False):
    """returns dict(crit_attempt, bulk_attempt, crit_msg, bulk_pcoll, crit_pcoll)."""
    tau = tau_c + tau_b
    if not priority:
        pc = pb = p_coll_plain(N, M, tau)
    else:
        pc = 1 - ((1 - tau_c / M) * (1 - (1 - rho) * tau_b / M)) ** (N - 1)
        # bulk: sees M - K free channels, K = critical-occupied channels (expected); sensing fails with prob 1-rho
        EK = M * (1 - (1 - tau_c / M) ** N)
        p_other_bulk = tau_b / max(M - EK, 1.0) * rho + tau_b / M * (1 - rho)           # other bulk sender hits a given FREE channel
        pb = 1 - ((1 - p_other_bulk) * (1 - tau_c / M * (1 - rho))) ** (N - 1)
    return dict(crit_pcoll=pc, bulk_pcoll=pb, crit_attempt=attempt_success(pc, b), bulk_attempt=attempt_success(pb, b), crit_msg=1 - (1 - attempt_success(pc, b)) ** R)


def knee(M, priority, thr=0.95, Nmax=2000, **kw):
    """smallest N whose analytic critical message delivery is < thr (None if never)."""
    for N in range(1, Nmax):
        if analytic(N, M=M, priority=priority, **kw)["crit_msg"] < thr: return N
    return None


# ----------------------------------------------------------------- Monte Carlo
def mc(N, M=13, tau_c=0.1, tau_b=0.5, b=0.2, rho=0.9, priority=False, T=None, seed=1, tau_b_vec=None, chunk=2000):
    """Monte Carlo. Returns per-class success rates and per-link counts. tau_b_vec: per-link bulk probabilities (heterogeneous loads)."""
    rng = np.random.default_rng(seed); T = T or max(2000, 400000 // N); tb = np.full(N, tau_b) if tau_b_vec is None else np.asarray(tau_b_vec)
    cs_n = cs_s = bs_n = bs_s = 0; link_tx = np.zeros(N); link_ok = np.zeros(N); done = 0
    while done < T:
        t = min(chunk, T - done); done += t
        u = rng.random((t, N)); crit = u < tau_c; bulk = (u >= tau_c) & (u < tau_c + tb[None, :]); send = crit | bulk
        ch = rng.integers(0, M, (t, N)); tt = np.repeat(np.arange(t), N).reshape(t, N)
        if priority:
            occ = np.zeros((t, M), bool); occ[tt[crit], ch[crit]] = True
            sense = rng.random((t, N)) < rho; free = ~occ; nfree = free.sum(1); cs = np.cumsum(free, axis=1)
            r = np.floor(rng.random((t, N)) * np.maximum(nfree, 1)[:, None]).astype(int)
            alt = (cs[:, None, :] > r[:, :, None]).argmax(2)
            use_alt = bulk & sense & (nfree[:, None] > 0); ch = np.where(use_alt, alt, ch)
        cnt = np.bincount((tt[send] * M + ch[send]), minlength=t * M).reshape(t, M)
        collide = cnt[tt, ch] > 1; busy = rng.random((t, M)) < b; bad = collide | busy[tt, ch] | (rng.random((t, N)) < P_CLEAN)
        ok = send & ~bad
        cs_n += crit.sum(); cs_s += (crit & ok).sum(); bs_n += bulk.sum(); bs_s += (bulk & ok).sum(); link_tx += send.sum(0); link_ok += ok.sum(0)
    return dict(crit_attempt=cs_s / max(cs_n, 1), bulk_attempt=bs_s / max(bs_n, 1), n_crit=int(cs_n), n_bulk=int(bs_n), link_tx=link_tx, link_ok=link_ok, T=T)


def jain(x):
    x = np.asarray(x, float); return float(x.sum() ** 2 / (len(x) * (x ** 2).sum()))


def main():
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    here = os.path.dirname(os.path.abspath(__file__)); print("defaults:", DEF, "p_clean", P_CLEAN)
    print("\n== per-attempt success, analytic vs Monte Carlo (plain, no priority), M=13 ==")
    print(f"{'N':>4s} {'P_coll theory':>13s} {'succ theory':>11s} {'succ MC':>8s} {'MC 95% +-':>9s}")
    Ns = [1, 2, 5, 10, 20, 30, 40, 60, 80, 120]; plain_mc = {}; worst = 0.0
    for N in Ns:
        a = analytic(N); m = mc(N, T=None); n = m["n_crit"] + m["n_bulk"]; mc_s = (m["crit_attempt"] * m["n_crit"] + m["bulk_attempt"] * m["n_bulk"]) / n
        th = a["crit_attempt"]; ci = 1.96 * math.sqrt(th * (1 - th) / n); plain_mc[N] = (mc_s, ci); worst = max(worst, abs(mc_s - th) / ci)
        print(f"{N:4d} {a['crit_pcoll']:13.3f} {th:11.3f} {mc_s:8.3f} {ci:9.4f}")
    print(f"largest |MC-theory| in units of the 95% half-width: {worst:.2f}")
    print("\n== priority scheme: delivery of critical MESSAGES (R=3 attempts) and bulk per-attempt, analytic (A) vs MC ==")
    print(f"{'N':>4s} | {'crit plain A':>12s} {'crit prio A':>11s} {'crit prio MC':>12s} | {'bulk plain A':>12s} {'bulk plain MC':>13s} {'bulk prio A':>11s} {'bulk prio MC':>12s}")
    rows = {}
    for N in [1, 2, 5, 10, 20, 30, 40, 50, 60, 80, 120]:
        ap, app = analytic(N), analytic(N, priority=True); m0 = mc(N, seed=2); m1 = mc(N, priority=True, seed=3)
        cm0 = 1 - (1 - m0["crit_attempt"]) ** 3; cm1 = 1 - (1 - m1["crit_attempt"]) ** 3
        rows[N] = dict(plain_A=ap["crit_msg"], prio_A=app["crit_msg"], plain_MC=cm0, prio_MC=cm1, bulk_plain_A=ap["bulk_attempt"], bulk_plain_MC=m0["bulk_attempt"], bulk_prio_A=app["bulk_attempt"], bulk_prio_MC=m1["bulk_attempt"])
        print(f"{N:4d} | {ap['crit_msg']:12.3f} {app['crit_msg']:11.3f} {cm1:12.3f} | {ap['bulk_attempt']:12.3f} {m0['bulk_attempt']:13.3f} {app['bulk_attempt']:11.3f} {m1['bulk_attempt']:12.3f}   (plain crit MC {cm0:.3f})")
    print("\n== knee: smallest N with critical message delivery < 0.95 (analytic; R=3 unless stated) ==")
    print(f"{'M':>3s} {'plain':>6s} {'priority rho=0.9':>17s} {'priority rho=1':>15s} {'plain R=1':>10s} {'prio R=1':>9s}")
    kn = {}
    for M in (4, 8, 13, 16, 32):
        kn[M] = (knee(M, False), knee(M, True), knee(M, True, rho=1.0), knee(M, False, R=1), knee(M, True, R=1)); print(f"{M:3d} {str(kn[M][0]):>6s} {str(kn[M][1]):>17s} {str(kn[M][2]):>15s} {str(kn[M][3]):>10s} {str(kn[M][4]):>9s}")
    m_chk = [mc(kn[13][1], priority=True, seed=5), mc(kn[13][1] - 1, priority=True, seed=6)]
    print(f"MC check around the M=13 priority knee: N={kn[13][1]-1}: critical msg {1-(1-m_chk[1]['crit_attempt'])**3:.3f}; N={kn[13][1]}: {1-(1-m_chk[0]['crit_attempt'])**3:.3f}")
    print("\n== sensitivity of the knee (M=13, priority) to background load b and critical load tau_c ==")
    for b in (0.0, 0.1, 0.2, 0.3, 0.4): print(f"  b={b:.1f}: knee plain {knee(13, False, b=b)}, priority {knee(13, True, b=b)}")
    for tc in (0.05, 0.1, 0.2, 0.4): print(f"  tau_c={tc}: knee plain {knee(13, False, tau_c=tc)}, priority {knee(13, True, tau_c=tc)}")
    # structured background: 3 blocks of channels busy in turn -> same marginal => same single-link delivery
    print("\n== structured vs uniform background, same average b (single link N=1 must agree) ==")
    rng = np.random.default_rng(9); T = 200000; blocks = np.repeat(np.arange(3), [5, 4, 4]); active = rng.random((T, 3)) < 0.2; ch = rng.integers(0, 13, T)
    ok = ~active[np.arange(T), blocks[ch]] & (rng.random(T) > P_CLEAN); print(f"  uniform-theory (1-0.2)(0.99) = {0.8*0.99:.4f}; structured MC = {ok.mean():.4f}")
    print("\n== Jain fairness (M=13, per-link tau_b ~ U[0.1,0.9]) ==")
    print(f"{'N':>4s} {'J throughput':>13s} {'J offered':>10s} {'J delivery ratio':>17s} {'J ratio, prio':>14s}")
    fair = {}
    for N in (5, 10, 20, 40, 80):
        tbv = np.random.default_rng(N).uniform(0.1, 0.9, N); tbv = np.minimum(tbv, 0.9 - 0.1)
        m = mc(N, tau_b_vec=tbv, T=20000, seed=4); mp = mc(N, tau_b_vec=tbv, T=20000, seed=4, priority=True)
        thr = m["link_ok"] / m["T"]; off = m["link_tx"] / m["T"]; ratio = m["link_ok"] / m["link_tx"]; ratio_p = mp["link_ok"] / mp["link_tx"]
        fair[N] = (jain(thr), jain(off), jain(ratio), jain(ratio_p)); print(f"{N:4d} {fair[N][0]:13.3f} {fair[N][1]:10.3f} {fair[N][2]:17.4f} {fair[N][3]:14.4f}")
    # identical links, finite-sample baseline
    m = mc(20, T=20000, seed=8); print(f"identical links N=20: Jain of delivery ratio {jain(m['link_ok']/m['link_tx']):.4f}, of throughput {jain(m['link_ok']):.4f} (sampling noise only)")

    # ------------- figures
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.2)); Nn = np.arange(1, 121)
    for M, c in ((4, "C3"), (8, "C1"), (13, "C0"), (32, "C2")): ax[0].plot(Nn, [analytic(n, M=M)["crit_pcoll"] for n in Nn], color=c, label=f"M={M} theory")
    ax[0].plot(Ns, [1 - (plain_mc[n][0] / (0.8 * 0.99)) for n in Ns], "k.", label="M=13 Monte Carlo"); ax[0].set_xlabel("co-located links N"); ax[0].set_ylabel("packet collision probability"); ax[0].legend(fontsize=8); ax[0].grid(alpha=.3); ax[0].set_title("Collision probability (tau=0.6)")
    ax[1].plot(Nn, [analytic(n)["crit_msg"] for n in Nn], "C3", label="critical, no priority"); ax[1].plot(Nn, [analytic(n, priority=True)["crit_msg"] for n in Nn], "C0", label="critical, first-pick priority")
    ax[1].plot(Nn, [analytic(n)["bulk_attempt"] for n in Nn], "C3--", label="bulk (per attempt), no priority"); ax[1].plot(Nn, [analytic(n, priority=True)["bulk_attempt"] for n in Nn], "C0--", label="bulk (per attempt), priority")
    ax[1].plot(list(rows), [rows[n]["prio_MC"] for n in rows], "C0o", ms=4); ax[1].plot(list(rows), [rows[n]["plain_MC"] for n in rows], "C3o", ms=4); ax[1].plot(list(rows), [rows[n]["bulk_prio_MC"] for n in rows], "C0s", ms=3); ax[1].plot(list(rows), [rows[n]["bulk_plain_MC"] for n in rows], "C3s", ms=3)
    ax[1].axhline(0.95, color="gray", ls=":"); ax[1].axvline(kn[13][0], color="C3", ls=":", lw=1); ax[1].axvline(kn[13][1], color="C0", ls=":", lw=1); ax[1].set_xlabel("co-located links N"); ax[1].set_ylabel("delivery"); ax[1].set_title(f"M=13, R=3: knees at N={kn[13][0]} (plain) and N={kn[13][1]} (priority); dots=MC", fontsize=9); ax[1].legend(fontsize=7); ax[1].grid(alpha=.3)
    Ms = [4, 6, 8, 13, 16, 24, 32]; ax[2].plot(Ms, [knee(m, False) for m in Ms], "C3o-", label="plain"); ax[2].plot(Ms, [knee(m, True) for m in Ms], "C0o-", label="priority (rho 0.9)"); ax[2].set_xlabel("channels M"); ax[2].set_ylabel("N at which critical delivery < 0.95"); ax[2].legend(); ax[2].grid(alpha=.3); ax[2].set_title("Knee vs number of channels")
    fig.tight_layout(); fig.savefig(os.path.join(here, "figures", "venue_delivery.png"), dpi=120); plt.close(fig)
    fig, ax = plt.subplots(figsize=(6, 4)); ks = list(fair)
    ax.plot(ks, [fair[k][0] for k in ks], "o-", label="throughput (unequal loads)"); ax.plot(ks, [fair[k][2] for k in ks], "s-", label="delivery ratio, no priority"); ax.plot(ks, [fair[k][3] for k in ks], "^-", label="delivery ratio, priority")
    ax.set_ylim(0.5, 1.01); ax.set_xlabel("links N"); ax.set_ylabel("Jain fairness index"); ax.legend(fontsize=8); ax.grid(alpha=.3); ax.set_title("Fairness across links (M=13)"); fig.tight_layout(); fig.savefig(os.path.join(here, "figures", "venue_jain.png"), dpi=120); plt.close(fig)


if __name__ == "__main__":
    main()
