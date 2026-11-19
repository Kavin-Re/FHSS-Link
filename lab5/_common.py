"""Shared helpers for lab5 (simulation only). Imports existing modules from ../sim; never edits them.
Layout expected: <root>/sim/*.py and <root>/lab5/*.py (on the laptop) or <root>/sim and <root>/experiments (cloud build)."""
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
# Okabe-Ito colour-blind-safe palette
C = dict(black="#000000", orange="#E69F00", sky="#56B4E9", green="#009E73", yellow="#F0E442",
         blue="#0072B2", verm="#D55E00", pink="#CC79A7", grey="#7f7f7f")
plt.rcParams.update({"figure.dpi": 110, "axes.grid": True, "grid.alpha": 0.25, "axes.spines.top": False,
                     "axes.spines.right": False, "font.size": 9, "legend.fontsize": 8, "legend.frameon": False})

M_DEF, K_DEF, P_JAM, P_CLEAN = 13, 1, 0.95, 0.01   # same constants as sim/adaptive.py, sim/game.py
def game_value(M=13, k=1, p_jam=P_JAM, p_clean=P_CLEAN):
    """Delivery of uniform hopping vs a k-channel jammer: (1-k/M)(1-p_clean) + (k/M)(1-p_jam). M=13,k=1 -> 0.91769."""
    return (1 - k / M) * (1 - p_clean) + (k / M) * (1 - p_jam)

def save_json(name, obj):
    with open(os.path.join(OUT, name), "w") as f: json.dump(obj, f, indent=1)

def save_fig(fig, name):
    p = os.path.join(FIG, name); fig.savefig(p, bbox_inches="tight"); plt.close(fig); return p

def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)
    return bool(cond)
