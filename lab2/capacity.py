"""Module 5 - information theory of the jammed link and the gap of the sim/fec.py codes to capacity.

Model / assumptions
- Packet-level (hop) channel = erasure channel: a hop with jammed channel erases the packet with prob e_j=0.95
  (e_c=0.01 on a clean channel), consistent with sim/game.py. Capacity per slot (bits per packet bit) = 1 - erasure prob.
- Hopping vs k of M jammed: arbitrarily-varying erasure channel where the jammer picks the jammed set. With a hop
  sequence shared by TX/RX but unknown to the jammer (keyed schedule = common randomness) the capacity is
  1 - [e_c + (k/M)(e_j - e_c)] (the game value of module 4: erasure prob. is the complement of delivery). If the jammer
  knows the hop pattern (deterministic, leaked) the best it can do is jam the channel in use: capacity 1 - e_j.
- BSC(p): C = 1 - H2(p). AWGN: C = 0.5 log2(1+2 Es/N0)  (real BPSK-type signalling, per real dimension) with
  Es = R Eb; unconstrained-input Shannon limit Eb/N0 = (2^(2R)-1)/(2R); BPSK soft-input capacity by numerical integration;
  hard-decision BPSK = BSC with p = Q(sqrt(2 R Eb/N0)).
- Codes (sim/fec.py, used as-is): Hamming(7,4) R=4/7 (1-error-correcting, hard decision), conv K=3 r=1/2 (7,5) with
  hard-decision Viterbi, systematic (n,k) Cauchy MDS erasure code over GF(256).
- Operational definition of 'achieved': highest channel stress at which the decoded bit error rate (or block failure
  prob. for the erasure code) is <= 1e-3. 'Gap' = capacity at that stress minus code rate (bits), or dB in Eb/N0.
  Monte Carlo (finite sample, a few hundred error events per point) with log-linear interpolation to 1e-3.
- Caveats: hard-decision decoding only (soft Viterbi would close ~2 dB); BER target is arbitrary; finite-length
  erasure code gaps are computed exactly from the binomial law and cross-checked against the real fec decoder.
"""
import os, sys
import numpy as np
from math import erfc, sqrt, comb

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "sim")); sys.path.insert(0, HERE)
FIG = os.path.join(HERE, "figures")
EC, EJ = 0.01, 0.95


def h2(p):
    p = np.clip(np.asarray(p, float), 1e-15, 1 - 1e-15)
    return -p * np.log2(p) - (1 - p) * np.log2(1 - p)


def c_bsc(p): return 1 - h2(p)
def qf(x): return 0.5 * erfc(x / sqrt(2))


def c_hop(M, k, shared=True):
    return 1 - (EC + (k / M) * (EJ - EC)) if (shared or k == 0) else 1 - EJ


def bpsk_soft_cap(sigma2, n=40001):
    z = np.linspace(-12, 12, n); phi = np.exp(-z ** 2 / 2) / sqrt(2 * np.pi)
    sig = sqrt(sigma2); L = 2 * (1 + sig * z) / sigma2
    f = np.log2(1 + np.exp(-np.clip(L, -700, 700)))
    return 1 - float(np.sum(phi * f) * (z[1] - z[0]))


def ebn0_bpsk_soft(R):
    lo, hi = 1e-3, 100.0  # Eb/N0 linear; sigma2 = 1/(2 R EbN0)
    for _ in range(60):
        mid = sqrt(lo * hi)
        if bpsk_soft_cap(1 / (2 * R * mid)) > R: hi = mid
        else: lo = mid
    return 10 * np.log10(hi)


def ebn0_hard_from_p(p, R):
    lo, hi = 1e-2, 1e3
    for _ in range(80):
        mid = sqrt(lo * hi)
        if qf(sqrt(2 * R * mid)) > p: lo = mid
        else: hi = mid
    return 10 * np.log10(lo)


def p_for_capacity(R):
    lo, hi = 1e-9, 0.5
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if c_bsc(mid) > R: lo = mid
        else: hi = mid
    return lo


def interp_p(ps, bers, target=1e-3):
    lb = np.log(np.maximum(bers, 1e-8))
    for i in range(len(ps) - 1):
        if lb[i] <= np.log(target) < lb[i + 1]:
            f = (np.log(target) - lb[i]) / (lb[i + 1] - lb[i]); return ps[i] + f * (ps[i + 1] - ps[i])
    return None


def mds_fail(n, k, eps):
    """P(fewer than k of n packets arrive), iid erasure prob eps."""
    return sum(comb(n, j) * (1 - eps) ** j * eps ** (n - j) for j in range(k))


def best_k(n, eps, target=1e-3):
    ks = [k for k in range(1, n + 1) if mds_fail(n, k, eps) <= target]
    return max(ks) if ks else 0


def ge_erasures(N, steps, q, D, rng, stride=1):
    """Gilbert-Elliott erasure process (dwell mean D, bad prob q); returns bool (N, steps//stride) erased matrix sampled every `stride` slots."""
    s = rng.random(N) < q; out = []
    for t in range(steps):
        if t % stride == 0: out.append(rng.random(N) < np.where(s, EJ, EC))
        pb = np.where(s, 1 - (1 - q) / D, q / D); s = rng.random(N) < pb
    return np.stack(out, axis=1)


def main():
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from _budget import step
    import fec

    def s_hop():
        from game_lp import payoff_matrix, solve_matrix_game
        print("== A. capacity of the hopping link, M=13, erasure e_j=0.95 on jammed, e_c=0.01 on clean ==")
        print("k | jam fraction k/M | C shared-key hopping | game value module 4 (LP) | C if hop pattern leaked | C(erasure, same average eps)")
        for k in range(0, 7):
            A, _ = payoff_matrix(13, max(k, 1), 1 - EJ, 1 - EC) if k > 0 else (None, None)
            v = solve_matrix_game(A)[0] if k > 0 else 1 - EC
            eps = EC + (k / 13) * (EJ - EC)
            print(f"{k} | {k/13:.3f} | {c_hop(13,k):.4f} | {v:.4f} | {c_hop(13,k,False):.4f} | {1-eps:.4f}")
        print("capacity vs rates of simple MDS codes at the same loss: needs R <= C (see section D for finite-n gaps)")
    step("cap", "hop", s_hop)

    def s_awgn():
        print("\n== B. AWGN / BPSK Eb/N0 limits (dB) ==")
        print("R      | Shannon (real, unconstrained) | BPSK soft-decision | BPSK hard-decision (BSC cap) ")
        out = {}
        for R in (4 / 7, 0.5):
            sh = 10 * np.log10((2 ** (2 * R) - 1) / (2 * R)); so = ebn0_bpsk_soft(R)
            ph = p_for_capacity(R); ha = ebn0_hard_from_p(ph, R)
            out[R] = (sh, so, ha, ph)
            print(f"{R:.4f} | {sh:6.2f} | {so:6.2f} | {ha:6.2f}   (BSC p at capacity = {ph:.4f})")
        print(f"uncoded BPSK needs Eb/N0 = {ebn0_hard_from_p(1e-3, 1.0):.2f} dB for BER 1e-3")
        return out
    awgn = step("cap", "awgn", s_awgn)

    ps_h = [0.002, 0.004, 0.006, 0.008, 0.01, 0.015, 0.02, 0.03, 0.05]

    def s_ham():
        print("\n== C1. Hamming(7,4) on BSC(p): decoded info-bit error rate (400k info bits per point) ==")
        rng = np.random.default_rng(1); bers = []
        for p in ps_h:
            b = rng.integers(0, 2, 400000).astype(np.uint8); c = fec.ham_encode(b)
            e = (rng.random(len(c)) < p).astype(np.uint8); d = fec.ham_decode(c ^ e)
            bers.append(float(np.mean(d[:len(b)] != b))); print(f"p={p:.3f}: BER_out={bers[-1]:.2e}")
        ps = interp_p(ps_h, np.array(bers)); R = 4 / 7
        print(f"Hamming(7,4): p* (BER 1e-3) = {ps:.4f}; R={R:.4f}; C_BSC(p*)={float(c_bsc(ps)):.4f}; gap = {float(c_bsc(ps))-R:.4f} bits; p_cap(R)={p_for_capacity(R):.4f}")
        return bers, ps
    ham = step("cap", "ham", s_ham)

    ps_c = [0.002, 0.004, 0.006, 0.008, 0.01, 0.015, 0.02, 0.03]

    def s_conv():
        print("\n== C2. conv K=3 r=1/2 hard Viterbi on BSC(p): decoded BER (frames of 298 info bits, 100k bits per point) ==")
        rng = np.random.default_rng(2); bers = []
        for p in ps_c:
            err = 0; tot = 0
            for _ in range(336):
                b = rng.integers(0, 2, 298).astype(np.uint8); c = fec.conv_encode(b)
                e = (rng.random(len(c)) < p).astype(np.uint8); d = fec.viterbi_decode(c ^ e)
                err += int(np.sum(d != b)); tot += len(b)
            bers.append(err / tot); print(f"p={p:.3f}: BER_out={bers[-1]:.2e}")
        ps = interp_p(ps_c, np.array(bers)); R = 0.5
        print(f"conv K=3: p* (BER 1e-3) = {ps}; R=0.5; C_BSC(p*)={float(c_bsc(ps)):.4f}; gap = {float(c_bsc(ps))-R:.4f} bits; p_cap(R)={p_for_capacity(R):.4f}")
        return bers, ps
    conv = step("cap", "conv", s_conv)

    def s_ebn0():
        print("\n== C3. same codes expressed as Eb/N0 for BER 1e-3 (hard-decision BPSK/AWGN) ==")
        print("code | R | Eb/N0 needed [dB] | gap to hard-decision capacity [dB] | gap to BPSK-soft limit [dB] | gap to unconstrained Shannon [dB] | coding gain vs uncoded [dB]")
        unc = ebn0_hard_from_p(1e-3, 1.0)
        for name, R, ps in (("Hamming(7,4)", 4 / 7, ham[1]), ("conv K=3 r=1/2", 0.5, conv[1])):
            e = ebn0_hard_from_p(ps, R); sh, so, ha, _ = awgn[R]
            print(f"{name} | {R:.3f} | {e:.2f} | {e-ha:.2f} | {e-so:.2f} | {e-sh:.2f} | {unc-e:.2f}")
    step("cap", "ebn0", s_ebn0)

    def s_mds():
        print("\n== D1. MDS erasure code (n,k) over i.i.d. hop erasures: best rate with block failure <= 1e-3 ==")
        print("eps | capacity 1-eps | " + " | ".join(f"n={n}: R (gap)" for n in (8, 13, 16, 32, 64, 128, 255)))
        out = {}
        for eps in (0.1, 0.2, 0.3, 0.5):
            row = []
            for n in (8, 13, 16, 32, 64, 128, 255):
                k = best_k(n, eps); out[(eps, n)] = k / n; row.append(f"{k}/{n}={k/n:.3f} ({1-eps-k/n:.3f})")
            print(f"{eps:.1f} | {1-eps:.2f} | " + " | ".join(row))
        print("\n== D2. check of the formula against the real fec.erasure_encode/decode (Monte Carlo, 3000 trials) ==")
        rng = np.random.default_rng(3)
        for (n, k, eps) in ((8, 5, 0.3), (8, 6, 0.2), (13, 9, 0.2)):
            fails = 0
            for _ in range(3000):
                data = [rng.integers(0, 256, 4).astype(np.uint8) for _ in range(k)]
                pk = fec.erasure_encode(data, n); keep = rng.random(n) >= eps
                rec = {i: pk[i] for i in range(n) if keep[i]}
                dec = fec.erasure_decode(rec, n, k)
                if dec is None or not all((a == b).all() for a, b in zip(dec, data)): fails += 1
            print(f"(n,k)=({n},{k}) eps={eps}: MC failure {fails/3000:.4f}  binomial formula {mds_fail(n, k, eps):.4f}")
        return out
    mds = step("cap", "mds", s_mds)

    def s_burst():
        print("\n== D3. bursty hop loss (Gilbert-Elliott, mean eps=0.2): n=32 MDS code, best k with failure <= 1e-3 (200k blocks) ==")
        print("D (mean dwell) | interleaving stride | best k | rate | gap to capacity 0.8 | note")
        q = (0.2 - EC) / (EJ - EC); n = 32; N = 200000; rng = np.random.default_rng(7)
        res = {}
        for D, stride in ((1, 1), (5, 1), (20, 1), (5, 5), (20, 20)):
            er = ge_erasures(N, n * stride, q, D, rng, stride=stride)
            got = n - er.sum(axis=1); best = 0
            for k in range(1, n + 1):
                if np.mean(got < k) <= 1e-3: best = k
            res[(D, stride)] = best / n
            print(f"{D} | {stride} | {best} | {best/n:.3f} | {0.8 - best/n:.3f} | mean erasure frac {er.mean():.3f}")
        return res
    burst = step("cap", "burst", s_burst)

    def s_fig():
        fig, ax = plt.subplots(1, 3, figsize=(14, 4.2))
        ks = np.arange(0, 14)
        ax[0].plot(ks / 13, [c_hop(13, k) for k in ks], "o-", c="#1e8449", label="hop, keyed schedule (jammer blind)")
        ax[0].plot(ks / 13, [c_hop(13, k, False) for k in ks], "s--", c="#c0392b", label="hop pattern known to jammer")
        ax[0].set_xlabel("jammed fraction k/M"); ax[0].set_ylabel("capacity [bits per packet bit]"); ax[0].legend(fontsize=7); ax[0].grid(alpha=.3)
        ax[0].set_title("capacity of the hopping link (erasure AVC)")
        pp = np.linspace(0.0005, 0.12, 300)
        ax[1].plot(pp, c_bsc(pp), c="k", label="BSC capacity")
        ax[1].plot([ham[1]], [4 / 7], "o", c="#2471a3", label="Hamming(7,4)")
        ax[1].plot([conv[1]], [0.5], "s", c="#e67e22", label="conv K=3 r=1/2")
        for pc, R, c in ((ham[1], 4 / 7, "#2471a3"), (conv[1], 0.5, "#e67e22")):
            ax[1].annotate("", xy=(pc, float(c_bsc(pc))), xytext=(pc, R), arrowprops=dict(arrowstyle="<->", color=c))
        ax[1].set_xlabel("BSC crossover p at BER 1e-3"); ax[1].set_ylabel("rate / capacity"); ax[1].legend(fontsize=7); ax[1].grid(alpha=.3)
        ax[1].set_title("gap to capacity (arrows)")
        ns = [8, 13, 16, 32, 64, 128, 255]
        for eps, c in ((0.1, "#1e8449"), (0.2, "#2471a3"), (0.3, "#e67e22"), (0.5, "#c0392b")):
            ax[2].semilogx(ns, [1 - eps - mds[(eps, n)] for n in ns], "o-", c=c, label=f"eps={eps}")
        ax[2].set_xlabel("codeword length n"); ax[2].set_ylabel("gap = C - R [bits]"); ax[2].legend(fontsize=7); ax[2].grid(alpha=.3, which="both")
        ax[2].set_title("MDS erasure code, fail<=1e-3, i.i.d.")
        plt.tight_layout(); plt.savefig(os.path.join(FIG, "capacity.png"), dpi=110); print("saved figures/capacity.png")
    step("cap", "fig", s_fig)


if __name__ == "__main__":
    main()
