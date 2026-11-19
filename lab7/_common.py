"""Shared helpers for lab7 (simulation only; defensive/educational; no hardware, no network).
Layout: <root>/sim/*.py (existing, imported read-only) and <root>/lab7/*.py. numpy + matplotlib only."""
import os, sys, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SIM = os.environ.get("FHSS_SIM") or os.path.join(ROOT, "sim")
if SIM not in sys.path:
    sys.path.insert(0, SIM)
FIG = os.path.join(HERE, "figures"); os.makedirs(FIG, exist_ok=True)
OUT = os.path.join(HERE, "outputs"); os.makedirs(OUT, exist_ok=True)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
C = dict(black="#000000", orange="#E69F00", sky="#56B4E9", green="#009E73", yellow="#F0E442",
         blue="#0072B2", verm="#D55E00", pink="#CC79A7", grey="#7f7f7f")   # Okabe-Ito (colour-blind safe)
plt.rcParams.update({"figure.dpi": 110, "axes.grid": True, "grid.alpha": 0.25, "axes.spines.top": False,
                     "axes.spines.right": False, "font.size": 9, "legend.fontsize": 8, "legend.frameon": False})

def save_fig(fig, name):
    p = os.path.join(FIG, name); fig.savefig(p, bbox_inches="tight"); plt.close(fig); return p

def save_json(name, obj):
    with open(os.path.join(OUT, name), "w") as f: json.dump(obj, f, indent=1, default=float)

def key(idx, text):
    """The one printed key number per idea."""
    print(f"KEY[{idx}] {text}", flush=True)
