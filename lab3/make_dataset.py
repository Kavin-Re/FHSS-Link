"""Generate the SIMULATED 'classify the jammer' dataset from sim/classify.py windows.

MODEL / ASSUMPTIONS
- Each row is ONE observation window of W slots from sim/classify.sim_window (a hopping link that observes only its own channel, ack result and RSSI),
  summarised by the 7 features of classify.features (see dataset/README.md). Labels: none, static, sweep, random, reactive.
- Variation per window (drawn uniformly, seeded): channels M in {8,13,16,24,32}; window length W in {100,150,200}; jammer duty in {1.0,0.75,0.5,0.25}
  (fraction of slots in which the jammer actually emits when it is on our channel; ignored for 'none'); jammer strength p_jam (loss prob. on a jammed
  hop) U(0.5,0.99); background loss p_clean U(0.005,0.04). 'static' uses 1-3 jammed channels, 'sweep' 1-3 channels advancing 1 per slot.
- Everything is simulated. Windows with fewer than 3 lost packets have all-zero loss-structure features by construction of classify.features
  (they carry only the loss rate); those windows are inherently ambiguous and are kept on purpose.
- Split: stratified 80/20 train/test with a fixed seed (SPLIT_SEED); also writes a few raw logs in the board serial format ($FH,...*CRC) from sim/emu_device.py.
Run: python3 make_dataset.py [--per-class 1300]
"""
import os, sys, csv, argparse, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, "..", "sim"))
import classify, emu_device
from serial_proto import parse

SPLIT_SEED = 12345; GEN_SEED = 2026
FEATS = ["rate", "top2_loss_share", "step_plus1", "loss_entropy", "rssi_excess", "repeat_rate", "phase_peak"]
Ms = [8, 13, 16, 24, 32]; Ws = [100, 150, 200]; DUTIES = [1.0, 0.75, 0.5, 0.25]


def generate(per_class=1300):
    rng = np.random.default_rng(GEN_SEED); rows = []; wid = 0
    for cls in classify.CLASSES:
        for _ in range(per_class):
            M = int(rng.choice(Ms)); W = int(rng.choice(Ws)); duty = float(rng.choice(DUTIES)); pj = float(rng.uniform(0.5, 0.99)); pc = float(rng.uniform(0.005, 0.04)); seed = int(rng.integers(1, 2**31 - 1))
            f = classify.sim_window(cls, M=M, W=W, seed=seed, p_jam=pj, p_clean=pc, duty=duty)
            rows.append(dict(id=wid, label=cls, M=M, W=W, duty=duty, p_jam=round(pj, 4), p_clean=round(pc, 4), seed=seed, **{n: round(float(v), 6) for n, v in zip(FEATS, f)})); wid += 1
    # stratified split with a fixed seed
    sr = np.random.default_rng(SPLIT_SEED); split = np.empty(len(rows), dtype=object)
    for cls in classify.CLASSES:
        idx = np.array([i for i, r in enumerate(rows) if r["label"] == cls]); sr.shuffle(idx); ntr = int(0.8 * len(idx)); split[idx[:ntr]] = "train"; split[idx[ntr:]] = "test"
    for r, s in zip(rows, split): r["split"] = s
    return rows


def write_csv(rows, path):
    cols = ["id", "split", "label", "M", "W", "duty", "p_jam", "p_clean", "seed"] + FEATS
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); [w.writerow({c: r[c] for c in cols}) for r in rows]


def write_raw_logs(outdir, slots=1500):
    os.makedirs(outdir, exist_ok=True); made = []
    for jam in ("none", "static", "sweep", "random"):
        p = os.path.join(outdir, f"{jam}_blind_M13.log")
        with open(p, "w") as f:
            for line, _ in emu_device.emulate("blind", jam, M=13, slots=slots, seed=7): f.write(line)
        made.append(p)
    return made


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--per-class", type=int, default=1300); a = ap.parse_args(argv); t0 = time.time()
    rows = generate(a.per_class); out = os.path.join(HERE, "dataset", "windows.csv"); write_csv(rows, out)
    print(f"wrote {len(rows)} windows to {out} in {time.time()-t0:.1f} s")
    for s in ("train", "test"): print(s, sum(r["split"] == s for r in rows), {c: sum(r["split"] == s and r["label"] == c for r in rows) for c in classify.CLASSES})
    z = sum(r["rate"] * r["W"] < 3 for r in rows); print(f"windows with < 3 lost packets (loss-structure features all zero): {z} ({100*z/len(rows):.1f} %)")
    print("by label: windows with <3 losses:", {c: sum(r["label"] == c and r["rate"] * r["W"] < 3 for r in rows) for c in classify.CLASSES})
    for p in write_raw_logs(os.path.join(HERE, "dataset", "raw")):
        lines = open(p).read().splitlines(); ok = sum(parse(l) is not None for l in lines); print(f"raw log {os.path.relpath(p, HERE)}: {len(lines)} lines, {ok} parse OK (CRC checked)")


if __name__ == "__main__":
    main()
