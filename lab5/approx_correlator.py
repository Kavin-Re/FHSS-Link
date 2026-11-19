"""Experiment 1 - approximate-adder DS-SS correlator and a ladder-driven quality-scalable receiver (simulation only).

Model (self-contained; nothing imported from other workers' libraries):
- DS-SS BPSK, Gp = 32 chips/bit, fresh random +-1 code per bit (same convention as sim/fhss_sim.py), per-chip signal amplitude 1,
  per-chip noise variance sigma2 = Gp/(2 Eb/N0). Optional random-phase tone interferer, A = sqrt(2*JSR).
- ADC: 6-bit signed, step 0.5 (chip amplitude = 2 LSB, range +-16). Correlator = sequential accumulator, acc += c_j * q_j for 32 chips,
  W = 12-bit two's complement (|acc| <= 32*32). Decision = sign(acc).
- Adders: EXACT; LOA(l) = lower-part-OR adder (l low bits OR'ed, AND of bit l-1 as carry into the exact upper part);
  LOAC(l) = LOA(l) plus a constant bias correction (mean error calibrated once on a separate seed at 4 dB, subtracted from the result);
  TRUNC(t) = drop t LSBs of the ADC sample BEFORE the +-1 code multiply (floor; the random +-1 code makes the floor bias cancel) and use a (W-t)-bit adder;
  TRUNCRAW(t) = naive floor truncation AFTER the code multiply (biased towards -1), shown as the contrast case.
- Energy proxy (NOT a measurement): full-adder cell = 1.0, OR2 = 0.2, AND2 = 0.2 (assumed relative gate costs), counted per accumulate,
  normalised so EXACT = 1.0. Ignores ADC, wiring, leakage, clocking and the carry chain's timing slack.
"""
import numpy as np
import _common as cm
from _common import C, plt
import adaptive, ladder          # existing modules (imported from ../sim, never edited)

GP, W, STEP, QMAX = 32, 12, 0.5, 31
FA, OR2, AND2 = 1.0, 0.2, 0.2
MASK = (1 << W) - 1


def _signed(x, w=W):
    return np.where(x >= (1 << (w - 1)), x - (1 << w), x)


def add_exact(acc, x): return _signed((acc + x) & MASK)


def add_loa(acc, x, l):
    a, b = acc & MASK, x & MASK
    low = (a | b) & ((1 << l) - 1)
    cin = (a >> (l - 1)) & (b >> (l - 1)) & 1
    high = ((a >> l) + (b >> l) + cin) & ((1 << (W - l)) - 1)
    return _signed((high << l) | low)


def energy(cfg):
    kind = cfg[0]
    if kind == "exact": per = W * FA
    elif kind in ("loa", "loac"): per = (W - cfg[1]) * FA + cfg[1] * OR2 + AND2
    elif kind in ("trunc", "truncraw"): per = (W - cfg[1]) * FA
    else: raise ValueError(cfg)
    return per * GP / (W * FA * GP)


_BIAS = {}


def _run(cfg, ebn0_db, nbits, jsr_db, seed, bias=0):
    rng = np.random.default_rng(seed)
    sigma = np.sqrt(GP / (2 * 10 ** (ebn0_db / 10)))
    b = rng.choice([-1, 1], size=nbits)
    phi = rng.uniform(0, 2 * np.pi, size=nbits)
    A = 0.0 if jsr_db is None else np.sqrt(2 * 10 ** (jsr_db / 10))
    acc = np.zeros(nbits, dtype=np.int64); kind = cfg[0]
    for j in range(GP):
        c = rng.choice([-1, 1], size=nbits)
        r = b * c + rng.normal(0, sigma, nbits) + A * np.cos(2 * np.pi * 0.1 * j + phi)
        q = np.clip(np.rint(r / STEP), -QMAX - 1, QMAX).astype(np.int64)
        if kind == "trunc": q = q >> cfg[1]
        x = q * c
        if kind == "exact": acc = add_exact(acc, x)
        elif kind in ("loa", "loac"): acc = add_loa(acc, x, cfg[1])
        elif kind == "truncraw": acc = acc + (x >> cfg[1])
        else: acc = acc + x                                  # trunc: (W-t)-bit adder, no wrap at these widths
    return b, acc


def correlate_ber(cfg, ebn0_db, nbits=100_000, jsr_db=None, seed=7):
    """BER of the fixed-point correlator under config cfg. Common random numbers: same seed -> same noise for every cfg."""
    if cfg[0] == "loac":
        if cfg not in _BIAS:       # calibrate constant offset on an independent seed (zero jammer, 4 dB)
            _, a_l = _run(("loa", cfg[1]), 4.0, 50_000, None, 999); _, a_e = _run(("exact",), 4.0, 50_000, None, 999)
            _BIAS[cfg] = int(np.rint(np.mean(a_l - a_e)))
        b, acc = _run(cfg, ebn0_db, nbits, jsr_db, seed); acc = acc - _BIAS[cfg]
    else:
        b, acc = _run(cfg, ebn0_db, nbits, jsr_db, seed)
    return float(np.mean(np.sign(acc + 0.0) != b))


CONFIGS = [("exact",)] + [("loa", l) for l in range(1, 7)] + [("loac", l) for l in range(1, 8)] + [("trunc", t) for t in range(1, 6)] + [("truncraw", t) for t in (1, 2, 3)]
COND = {"stress4dB": (4.0, None), "clean8dB": (8.0, None), "jam": (8.0, 15.0)}


def sweep(nbits=100_000):
    res = {}
    for cfg in CONFIGS:
        res[cfg] = dict(energy=energy(cfg), **{k: correlate_ber(cfg, e, nbits, j) for k, (e, j) in COND.items()})
    return res


def pick_modes(res, tol_normal=1.30, tol_adapt=1.10):
    """Cheapest config whose stress-point BER (4 dB, resolved well) is within a factor tol of exact. Harsher than the operating point on purpose."""
    base = res[("exact",)]["stress4dB"]
    def cheapest(tol):
        ok = [(v["energy"], c) for c, v in res.items() if v["stress4dB"] <= tol * base + 1e-12]
        return min(ok)[1]
    return {"NORMAL": cheapest(tol_normal), "ADAPT": cheapest(tol_adapt), "CODED": ("exact",), "SURVIVAL": ("exact",)}


def per_from_ber(ber, nb=16): return 1 - (1 - ber) ** nb


def scalable_run(policy, mode_cfg, per, seed=1, T=10000, M=13):
    """Closed loop over the ladder scenario (ladder.PHASES, ladder.jam_set). Channel jammed -> 'jam' PHY condition, else clean8dB.
    policy: fixed_exact | fixed_cheap (NORMAL's config, no ladder) | ladder_exact (ladder modes, exact adders everywhere)
            | ladder_scalable (ladder modes; adder config follows the mode: approximate when NORMAL/ADAPT, exact when CODED/SURVIVAL).
    The ladder controller mirrors the thresholds/hysteresis of sim/ladder.py (copied, not edited)."""
    rng = np.random.default_rng(seed)
    blind = adaptive.Blind(M, np.random.default_rng(seed + 1)); ts = adaptive.Thompson(M, np.random.default_rng(seed + 2))
    use_ladder = policy.startswith("ladder"); mode = "NORMAL"; hist = []; calm = 0; occ = {m: 0 for m in ladder.MODES}
    ok_ph = {}; n_ph = {}; E = 0.0
    for t in range(T):
        ph = ladder.phase_name(t); J = ladder.jam_set(t, rng, M)
        c = ts.pick() if mode == "ADAPT" else blind.pick()
        cfg = mode_cfg[mode] if policy == "ladder_scalable" else mode_cfg["NORMAL"] if policy == "fixed_cheap" else ("exact",)
        E += energy(cfg); occ[mode] += 1
        ok = rng.random() < 1 - per[cfg]["jam" if c in J else "clean8dB"]
        ts.update(c, float(ok)); blind.update(c, float(ok)); hist.append(0 if ok else 1)
        ok_ph[ph] = ok_ph.get(ph, 0) + ok; n_ph[ph] = n_ph.get(ph, 0) + 1
        if use_ladder:
            loss = np.mean(hist[-50:]) if len(hist) >= 20 else 0.0
            want = 0 if loss < 0.08 else 1 if loss < 0.25 else 2 if loss < 0.55 else 3
            cur = ladder.MODES.index(mode)
            if want > cur: mode = ladder.MODES[want]; calm = 0
            elif want < cur:
                still = mode == "ADAPT" and (ts.a / (ts.a + ts.b)).min() < 0.6
                calm = 0 if still else calm + 1
                if calm >= 100: mode = ladder.MODES[want]; calm = 0
            else: calm = 0
    return dict(pdr=sum(ok_ph.values()) / T, energy=E / T, phase={k: ok_ph[k] / n_ph[k] for k in n_ph}, occupancy={k: v / T for k, v in occ.items()})


def main(nbits=100_000, seeds=(1, 2, 3)):
    res = sweep(nbits)
    modes = pick_modes(res)
    per = {c: {k: per_from_ber(res[c][k]) for k in COND} for c in res}
    lines = ["cfg | energy | BER@4dB | BER@8dB | BER@8dB+tone15dB"]
    for c, v in res.items(): lines.append(f"{str(c):16s} {v['energy']:.3f}  {v['stress4dB']:.5f}  {v['clean8dB']:.5f}  {v['jam']:.4f}")
    lines.append(f"mode configs: {modes}")
    runs = {}
    for pol in ("fixed_exact", "fixed_cheap", "ladder_exact", "ladder_scalable"):
        rs = [scalable_run(pol, modes, per, seed=s) for s in seeds]
        runs[pol] = dict(pdr=float(np.mean([r["pdr"] for r in rs])), energy=float(np.mean([r["energy"] for r in rs])),
                         phase={k: float(np.mean([r["phase"][k] for r in rs])) for k in rs[0]["phase"]},
                         occupancy={k: float(np.mean([r["occupancy"][k] for r in rs])) for k in rs[0]["occupancy"]})
        lines.append(f"{pol:9s} PDR {runs[pol]['pdr']:.4f}  energy {runs[pol]['energy']:.3f}  phases { {k: round(v, 3) for k, v in runs[pol]['phase'].items()} }  occ { {k: round(v, 2) for k, v in runs[pol]['occupancy'].items()} }")
    tol_rows = []
    for tn in (1.3, 2.0, 4.0):                      # looser NORMAL tolerance -> cheaper clean mode; ADAPT stays at 1.1x
        md = pick_modes(res, tn, 1.10)
        rs = [scalable_run("ladder_scalable", md, per, seed=s) for s in seeds]
        row = dict(tol=tn, normal=str(md["NORMAL"]), pdr=float(np.mean([r["pdr"] for r in rs])), energy=float(np.mean([r["energy"] for r in rs])),
                   clean_pdr=float(np.mean([r["phase"]["clean"] for r in rs])))
        tol_rows.append(row); lines.append(f"tolerance sweep NORMAL<= {tn}x exact stress BER: {row}")
    runs["tolerance_sweep"] = tol_rows
    print("\n".join(lines))
    # ---- figure
    fig, ax = plt.subplots(1, 3, figsize=(14, 4.2))
    fam = {"loa": (C["blue"], "o", "LOA(l)"), "loac": (C["sky"], "D", "LOA(l) + bias correction"), "trunc": (C["green"], "s", "TRUNC(t) before code multiply"), "truncraw": (C["verm"], "^", "TRUNC(t) after multiply (biased)")}
    for a, key, ttl in ((ax[0], "stress4dB", "Eb/N0 = 4 dB, no tone"), (ax[1], "jam", "Eb/N0 = 8 dB, tone JSR = 15 dB")):
        for kind, (col, mk, lab) in fam.items():
            pts = sorted([(v["energy"], v[key], c[1]) for c, v in res.items() if c[0] == kind])
            a.plot([p[0] for p in pts], [p[1] for p in pts], "-" + mk, color=col, label=lab, ms=4)
            if key == "stress4dB":
                for e, b, p in pts: a.annotate(str(p), (e, b), fontsize=6, xytext=(2, 3), textcoords="offset points")
        ex = res[("exact",)]
        a.plot([1.0], [ex[key]], "*", color="k", ms=11, label="exact adder"); a.set_yscale("log"); a.set_ylim(1e-4, 0.7); a.set_xlabel("energy proxy (exact = 1)"); a.set_ylabel("BER"); a.set_title(ttl)
        a.invert_xaxis()
    ax[0].legend(loc="upper left")
    for pol, col in (("fixed_exact", C["grey"]), ("fixed_cheap", C["verm"]), ("ladder_exact", C["black"]), ("ladder_scalable", C["blue"])):
        ax[2].scatter(runs[pol]["energy"], runs[pol]["pdr"], s=90, color=col, label=pol, zorder=3)
        off = {"fixed_exact": (-8, 12), "fixed_cheap": (6, 6), "ladder_exact": (-10, -26), "ladder_scalable": (6, 10)}[pol]
        ax[2].annotate(f"{pol}: PDR {runs[pol]['pdr']:.3f}, E {runs[pol]['energy']:.2f}", (runs[pol]["energy"], runs[pol]["pdr"]), fontsize=6.5, xytext=off, textcoords="offset points", ha="right" if off[0] < 0 else "left")
    ax[2].set_xlim(0.88, 1.03); ax[2].set_ylim(0.76, 0.96); ax[2].set_xlabel("mean energy proxy per slot"); ax[2].set_ylabel("slot delivery over ladder scenario"); ax[2].set_title("quality-scalable receiver (3 seeds)")
    fig.suptitle("Approximate-adder DS-SS correlator (Gp=32, 12-bit accumulator); energy proxy is an assumption, not a measurement", fontsize=9)
    cm.save_fig(fig, "fig1_approx_correlator.png")
    cm.save_json("exp1_approx_correlator.json", dict(configs={str(c): v for c, v in res.items()}, modes={k: str(v) for k, v in modes.items()}, runs=runs))
    open(cm.os.path.join(cm.OUT, "exp1_approx_correlator.txt"), "w").write("\n".join(lines) + "\n")
    return res, modes, runs


if __name__ == "__main__":
    main()
