"""Shared helpers for lab6 (simulation only, own-link model, no hardware). Self-contained: copies the few constants it needs from
sim/ (M=13 channels, p_jam=0.95, p_clean=0.01) instead of importing, so nothing in sim/ is touched or required."""
import os, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "figures"); os.makedirs(FIG, exist_ok=True)
OUT = os.path.join(HERE, "outputs"); os.makedirs(OUT, exist_ok=True)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
C = dict(black="#000000", orange="#E69F00", sky="#56B4E9", green="#009E73", yellow="#F0E442",
         blue="#0072B2", verm="#D55E00", pink="#CC79A7", grey="#7f7f7f")
plt.rcParams.update({"figure.dpi": 110, "axes.grid": True, "grid.alpha": 0.25, "axes.spines.top": False,
                     "axes.spines.right": False, "font.size": 9, "legend.fontsize": 8, "legend.frameon": False})
M_DEF, P_JAM, P_CLEAN = 13, 0.95, 0.01

def save_json(name, obj):
    with open(os.path.join(OUT, name), "w") as f: json.dump(obj, f, indent=1, default=float)

def save_fig(fig, name):
    p = os.path.join(FIG, name); fig.savefig(p, bbox_inches="tight"); plt.close(fig); return p

def key(label, value):
    print(f"KEY NUMBER: {label} = {value}", flush=True)
