"""B11 Poisoned logs (simulation): (A) store-level tampering vs hash chain variants; (B) source-level poisoning that keeps the chain valid,
its effect on a channel-selection digital twin, and two statistical detectors (sinr/ok consistency; trusted-audit comparison)."""
import hashlib, hmac
import numpy as np
from _common import *

# ---------- Part A: chain integrity ----------
def chain_plain(recs):
    h, out = b"\0" * 32, []
    for r in recs: h = hashlib.sha256(h + r).digest(); out.append(h)
    return out
def chain_hmac(recs, key):
    h, out = b"\0" * 32, []
    for r in recs: h = hmac.new(key, h + r, hashlib.sha256).digest(); out.append(h)
    return out
def verify(recs, stored, how, key=None):
    return (chain_hmac(recs, key) if how == "hmac" else chain_plain(recs)) == stored

def part_a(seed, n=600, anchor_every=200):
    rng = np.random.default_rng(seed); key_ = rng.bytes(16)
    recs = [b"%d,%d,%d,%.1f" % (i, rng.integers(16), rng.integers(2), rng.normal(10, 3)) for i in range(n)]
    sp, sh = chain_plain(recs), chain_hmac(recs, key_)
    anchors = {i: sp[i] for i in range(anchor_every - 1, n, anchor_every)}   # plain-chain heads published out-of-band
    def anchored_ok(recs2, st):
        if not verify(recs2, st, "plain"): return False
        return all(len(st) > i and st[i] == a for i, a in anchors.items())
    pos = int(rng.integers(0, n - 1)); forged = recs[:pos] + [recs[pos][:-1] + b"9"] + recs[pos + 1:]
    res = {}
    res["edit"] = dict(plain=not verify(forged, sp, "plain"), hmac=not verify(forged, sh, "hmac", key_), anchored=not anchored_ok(forged, sp))
    sp2 = chain_plain(forged)                  # attacker recomputes the whole chain; without the key he can only produce plain hashes
    res["rewrite"] = dict(plain=not verify(forged, sp2, "plain"), hmac=not verify(forged, sp2, "hmac", key_), anchored=not anchored_ok(forged, sp2))
    cut = int(rng.integers(n // 2, n - 1)); t_recs, t_p, t_h = recs[:cut], sp[:cut], sh[:cut]
    res["truncate"] = dict(plain=not verify(t_recs, t_p, "plain"), hmac=not verify(t_recs, t_h, "hmac", key_), anchored=not anchored_ok(t_recs, t_p), cut=cut)
    res["pos"] = pos
    return res

# ---------- Part B: source poisoning ----------
NCH, K_SEL, N_HON = 16, 12, 4000
JAM, DEFAME = [13, 14, 15], [0, 1, 2]
def sigm(x): return 1 / (1 + np.exp(-x))
def honest(rng):
    ch = rng.integers(0, NCH, N_HON); sinr = rng.normal(12, 3, N_HON) - 5.0 * np.isin(ch, JAM)
    ok = rng.random(N_HON) < sigm((sinr - 8) / 1.5); return ch, sinr, ok
def poison(rng, f, smart):
    k = int(f * N_HON); h = k // 2
    ch = np.concatenate([rng.choice(JAM, h), rng.choice(DEFAME, k - h)]); ok = np.concatenate([np.ones(h, bool), np.zeros(k - h, bool)])
    if smart: sinr = np.where(ok, rng.normal(14, 3, k), rng.normal(4, 3, k))      # sinr field made consistent with the claimed outcome
    else:     sinr = rng.normal(12, 3, k) - 5.0 * np.isin(ch, JAM)               # only ok flipped, sinr left as the honest distribution
    return ch, sinr, ok
def twin_select(ch, ok):
    rate = np.array([ok[ch == c].mean() if (ch == c).any() else 0 for c in range(NCH)]); return np.argsort(-rate)[:K_SEL], rate
def true_channel_quality():
    r = np.random.default_rng(99); out = np.zeros(NCH)
    for c in range(NCH):
        s = r.normal(12, 3, 200000) - 5.0 * (c in JAM); out[c] = (r.random(200000) < sigm((s - 8) / 1.5)).mean()
    return out
TRUEQ = true_channel_quality()

def irls(sinr, ok, it=12):
    X = np.stack([np.ones_like(sinr), sinr], 1); w = np.zeros(2); y = ok.astype(float)
    for _ in range(it):
        p = sigm(X @ w); W = p * (1 - p) + 1e-9; w = w + np.linalg.solve(X.T @ (X * W[:, None]) + 1e-6 * np.eye(2), X.T @ (y - p))
    return sigm(X @ w)
def detect_consistency(ch, sinr, ok, zthr=3.5):
    p = irls(sinr, ok); flags = []
    for c in range(NCH):
        m = ch == c; z = (ok[m] - p[m]).sum() / np.sqrt((p[m] * (1 - p[m])).sum() + 1e-9); flags.append(abs(z) > zthr)
    return np.array(flags)
def detect_audit(ch, ok, aud_ch, aud_ok, zthr=3.0):
    flags = []
    for c in range(NCH):
        m = ch == c; ma = aud_ch == c; pa = aud_ok[ma].mean() if ma.any() else 0.5; n = ma.sum()
        z = (ok[m].mean() - pa) / np.sqrt(max(pa * (1 - pa), 0.02) / max(n, 1)); flags.append(abs(z) > zthr)
    return np.array(flags)

def part_b(seed, f, smart):
    rng = np.random.default_rng(seed)
    ch, sinr, ok = honest(rng); aud = rng.random(N_HON) < 0.2
    a_ch, a_ok = ch[aud], ok[aud]
    if f > 0:
        pc, ps, po = poison(rng, f, smart); ch, sinr, ok = np.concatenate([ch, pc]), np.concatenate([sinr, ps]), np.concatenate([ok, po])
    sel, rate = twin_select(ch, ok)
    return dict(jam_in_set=int(np.isin(sel, JAM).sum()), quality=float(TRUEQ[sel].mean()),
                d_cons=bool(detect_consistency(ch, sinr, ok).any()), d_audit=bool(detect_audit(ch, ok, a_ch, a_ok).any()))

def run(fast=False):
    A = [part_a(s) for s in range(NSEEDS)]
    tab = {atk: {v: wilson(sum(a[atk][v] for a in A), len(A)) for v in ("plain", "hmac", "anchored")} for atk in ("edit", "rewrite", "truncate")}
    fgrid = [0.0, 0.02, 0.05, 0.1, 0.2, 0.4, 0.8]; nb = 60 if not fast else 25
    B = {}
    for smart in (False, True):
        for f in fgrid:
            r = [part_b(1000 + s, f, smart) for s in range(nb)]
            B[("smart" if smart else "naive") + f"@{f}"] = dict(jam=mean_ci([x["jam_in_set"] for x in r]), quality=mean_ci([x["quality"] for x in r]),
                                 cons=wilson(sum(x["d_cons"] for x in r), nb), audit=wilson(sum(x["d_audit"] for x in r), nb))
    out = dict(chain=tab, fgrid=fgrid, nb=nb, nseeds_chain=len(A), B=B, quality_all_clean=float(np.sort(TRUEQ)[::-1][:K_SEL].mean()))
    save_json("b11_poisoned_logs.json", out); return out

def plot(o):
    fig, ax = plt.subplots(1, 3, figsize=(12, 3.4)); fg = o["fgrid"]
    for atk, c in (("naive", C["sky"]), ("smart", C["verm"])):
        q = [o["B"][f"{atk}@{f}"]["quality"] for f in fg]
        ax[0].errorbar(fg, [x[0] for x in q], yerr=[[max(0,x[0]-x[1]) for x in q], [max(0,x[2]-x[0]) for x in q]], color=c, marker="o", capsize=2, label=f"{atk} forger")
    ax[0].axhline(o["quality_all_clean"], color=C["grey"], ls=":"); ax[0].set_xlabel("forged records / honest records"); ax[0].set_ylabel("true success rate of twin-selected set"); ax[0].legend(); ax[0].set_title("Harm to the twin")
    for k, atk in ((1, "naive"), (2, "smart")):
        for det, c, ls in (("cons", C["blue"], "-"), ("audit", C["orange"], "--")):
            m = [o["B"][f"{atk}@{f}"][det] for f in fg]
            ax[k].errorbar(fg, [x[0] for x in m], yerr=[[max(0,x[0]-x[1]) for x in m], [max(0,x[2]-x[0]) for x in m]], color=c, ls=ls, marker="o", capsize=2, label={"cons": "sinr/ok consistency", "audit": "trusted-audit compare"}[det])
        ax[k].set_xlabel("forged fraction"); ax[k].set_ylabel("P(alarm)"); ax[k].set_title(f"Detection, {atk} forger (f=0: false alarm)"); ax[k].legend()
    save_fig(fig, "b11_poisoned_logs.png")

if __name__ == "__main__":
    o = run(); plot(o); B = o["B"]
    key("B11", f"chain: rewrite-after-edit detected by plain chain {o['chain']['rewrite']['plain'][0]:.2f}, by HMAC chain {o['chain']['rewrite']['hmac'][0]:.2f}; "
               f"smart forger f=0.2: twin quality {B['smart@0.2']['quality'][0]:.3f} vs clean {o['quality_all_clean']:.3f}, consistency alarm {fmt(B['smart@0.2']['cons'])}, audit alarm {fmt(B['smart@0.2']['audit'])}; false alarm cons {B['naive@0.0']['cons'][0]:.2f}, audit {B['naive@0.0']['audit'][0]:.2f}")
