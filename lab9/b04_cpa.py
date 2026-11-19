"""B4 Side-channel power analysis (simulation): Hamming-weight leakage of one S-box output byte,
correlation power analysis (CPA) key-byte recovery, then first-order Boolean masking and a 2nd-order attack.
Synthetic traces (HW + Gaussian noise); no hardware."""
import numpy as np
from _common import *

def make_sbox():
    # AES S-box: multiplicative inverse in GF(2^8) then affine map
    # simple robust implementation via exponentiation
    def gmul(a, b):
        p = 0
        for _ in range(8):
            if b & 1: p ^= a
            hi = a & 0x80; a = (a << 1) & 0xFF
            if hi: a ^= 0x1B
            b >>= 1
        return p
    inv = [0] * 256
    for x in range(1, 256):
        for y in range(1, 256):
            if gmul(x, y) == 1: inv[x] = y; break
    sb = []
    for x in range(256):
        b = inv[x]; r = 0
        for i in range(8):
            bit = ((b >> i) ^ (b >> ((i + 4) % 8)) ^ (b >> ((i + 5) % 8)) ^ (b >> ((i + 6) % 8)) ^ (b >> ((i + 7) % 8)) ^ (0x63 >> i)) & 1
            r |= bit << i
        sb.append(r)
    return np.array(sb, np.uint8)
SBOX = make_sbox()
HW = np.array([bin(i).count("1") for i in range(256)], float)
GUESS_H = HW[SBOX[np.arange(256)[None, :] ^ np.arange(256)[:, None]]]   # [pt, guess] -> HW(S[pt^g])

def corr_all(l, H):
    """Pearson correlation of trace vector l (n,) with each column of H (n,256)."""
    l = l - l.mean(); Hc = H - H.mean(0)
    return (Hc * l[:, None]).sum(0) / (np.sqrt((Hc ** 2).sum(0) * (l ** 2).sum()) + 1e-12)

def traces(rng, k, n, sigma, mode):
    pt = rng.integers(0, 256, n); v = SBOX[pt ^ k]
    if mode == "plain":
        return pt, HW[v] + rng.normal(0, sigma, n), None
    m = rng.integers(0, 256, n)                      # fresh random mask per trace
    l1 = HW[v ^ m] + rng.normal(0, sigma, n)         # masked intermediate at time t1
    l2 = HW[m] + rng.normal(0, sigma, n)             # mask itself at time t2
    return pt, l1, l2

def attack(pt, l1, l2, order, n):
    H = GUESS_H[pt[:n]]
    if order == 1: s = corr_all(l1[:n], H)
    else:
        comb = (l1[:n] - l1[:n].mean()) * (l2[:n] - l2[:n].mean())   # centred-product combining
        s = corr_all(comb, H)
    return s

def success_curve(mode, order, sigma, grid, seeds):
    S = np.zeros((len(seeds), len(grid)))
    for i, sd in enumerate(seeds):
        rng = np.random.default_rng(sd); k = int(rng.integers(256))
        pt, l1, l2 = traces(rng, k, max(grid), sigma, mode)
        for j, n in enumerate(grid):
            s = attack(pt, l1, l2, order, n)
            S[i, j] = (np.argmax(np.abs(s)) == k)
    return S

def n90(grid, curve):
    for n, v in zip(grid, curve):
        if v >= 0.9: return n
    return None

def run(fast=False):
    seeds = list(range(NSEEDS))
    sigma = 2.0
    g_plain = [3, 5, 8, 12, 20, 32, 50, 80, 130, 200, 320, 500]
    g_mask = [200, 350, 500, 700, 1000, 1400, 2000, 3000, 4000, 8000, 16000, 32000]
    sp = success_curve("plain", 1, sigma, g_plain, seeds)
    sm1 = success_curve("masked", 1, sigma, g_mask, seeds)
    sm2 = success_curve("masked", 2, sigma, g_mask, seeds)
    # noise scaling of the unprotected attack + theory
    sig_list = [0.5, 1, 2, 4, 8]; nn = {}
    for sg in sig_list:
        g = [3, 5, 8, 12, 20, 32, 50, 80, 130, 200, 320, 500, 800, 1300, 2000]
        c = success_curve("plain", 1, sg, g, seeds[:20]).mean(0); nn[sg] = n90(g, c)
    # measured correlation of the true key vs theory rho = sqrt(Var(HW)/(Var(HW)+sigma^2)), Var(HW)=2
    rng = np.random.default_rng(7); k = 0x3C
    pt, l, _ = traces(rng, k, 200000, sigma, "plain"); rho_meas = float(np.corrcoef(HW[SBOX[pt ^ k]], l)[0, 1])
    rho_th = float(np.sqrt(2 / (2 + sigma ** 2)))
    out = dict(sigma=sigma, g_plain=g_plain, g_mask=g_mask,
               plain=[mean_ci(sp[:, j]) for j in range(len(g_plain))],
               m1=[mean_ci(sm1[:, j]) for j in range(len(g_mask))], m2=[mean_ci(sm2[:, j]) for j in range(len(g_mask))],
               n90_plain=n90(g_plain, sp.mean(0)), n90_masked2=n90(g_mask, sm2.mean(0)), n90_masked1=n90(g_mask, sm1.mean(0)),
               m1_final_success=wilson(int(sm1[:, -1].sum()), len(seeds)),
               n90_vs_sigma={str(k_): v for k_, v in nn.items()}, rho_meas=rho_meas, rho_theory=rho_th, nseeds=len(seeds))
    save_json("b04_cpa.json", out); return out

def plot(o):
    fig, ax = plt.subplots(1, 2, figsize=(9, 3.4))
    for lab, g, key_, c in [("unprotected, 1st-order CPA", o["g_plain"], "plain", C["verm"])]:
        m = o[key_]; ax[0].errorbar(g, [x[0] for x in m], yerr=[[x[0]-x[1] for x in m], [x[2]-x[0] for x in m]], color=c, marker="o", capsize=2, label=lab)
    for lab, key_, c in [("masked, 1st-order CPA", "m1", C["grey"]), ("masked, 2nd-order CPA", "m2", C["blue"])]:
        m = o[key_]; ax[0].errorbar(o["g_mask"], [x[0] for x in m], yerr=[[x[0]-x[1] for x in m], [x[2]-x[0] for x in m]], color=c, marker="o", capsize=2, label=lab)
    ax[0].set_xscale("log"); ax[0].set_xlabel("traces"); ax[0].set_ylabel("P(key byte recovered)"); ax[0].set_title(f"sigma={o['sigma']} (noise/HW-std ratio {o['sigma']/np.sqrt(2):.1f})"); ax[0].legend()
    items = sorted((float(k), v) for k, v in o["n90_vs_sigma"].items()); sg = [i[0] for i in items]; nv = [i[1] or np.nan for i in items]
    ax[1].loglog(sg, nv, "o-", color=C["verm"], label="traces for 90% success"); ax[1].set_xlabel("noise sigma"); ax[1].set_ylabel("traces"); ax[1].legend()
    save_fig(fig, "b04_cpa.png")

if __name__ == "__main__":
    o = run(); plot(o)
    key("B4", f"sigma=2: unprotected 90% key recovery at {o['n90_plain']} traces; 1st-order masking: 1st-order CPA success at 32000 traces {fmt(o['m1_final_success'])}; "
              f"2nd-order CPA needs {o['n90_masked2']} traces ({o['n90_masked2']/o['n90_plain']:.0f}x); rho measured {o['rho_meas']:.3f} vs theory {o['rho_theory']:.3f}")
