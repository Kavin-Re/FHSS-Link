"""Shared helpers for lab9 (simulation only; defensive/educational; no hardware, no network).
Self-contained: numpy + matplotlib only; does not import or modify any other FHSS-Link file."""
import os, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "figures"); os.makedirs(FIG, exist_ok=True)
OUT = os.path.join(HERE, "outputs"); os.makedirs(OUT, exist_ok=True)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
C = dict(black="#000000", orange="#E69F00", sky="#56B4E9", green="#009E73", yellow="#F0E442",
         blue="#0072B2", verm="#D55E00", pink="#CC79A7", grey="#7f7f7f")   # Okabe-Ito
plt.rcParams.update({"figure.dpi": 110, "axes.grid": True, "grid.alpha": 0.25, "axes.spines.top": False,
                     "axes.spines.right": False, "font.size": 9, "legend.fontsize": 8, "legend.frameon": False})
NSEEDS = 30   # headline numbers use >= 20 seeds (30 here)

def save_fig(fig, name):
    p = os.path.join(FIG, name); fig.savefig(p, bbox_inches="tight"); plt.close(fig); return p
def save_json(name, obj):
    with open(os.path.join(OUT, name), "w") as f: json.dump(obj, f, indent=1, default=float)
def key(idx, text): print(f"KEY[{idx}] {text}", flush=True)

def mean_ci(x, n_boot=2000, seed=12345):
    """Mean with 95% bootstrap percentile CI over independent seeds. Returns (mean, lo, hi)."""
    x = np.asarray(x, float); r = np.random.default_rng(seed)
    bm = x[r.integers(0, len(x), (n_boot, len(x)))].mean(1)
    return float(x.mean()), float(np.percentile(bm, 2.5)), float(np.percentile(bm, 97.5))
def wilson(k, n, z=1.96):
    """Wilson 95% CI for a proportion k/n."""
    if n == 0: return (0.0, 0.0, 1.0)
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (float(p), float(max(0, c - h)), float(min(1, c + h)))
def fmt(t, p=3): return f"{t[0]:.{p}f} [{t[1]:.{p}f}, {t[2]:.{p}f}]"
