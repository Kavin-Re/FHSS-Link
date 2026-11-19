"""Shared helpers for lab8 (simulation only, own-link model, no hardware, nothing imported from ../sim).

SPATIAL / LINK MODEL (one place, used by e12, e13, e14, e15; every constant is an assumption, not a measurement):
  * log-distance path loss   PL(d) = PL0 + 10 n log10(max(d, d0)/d0),  PL0 = 40 dB at d0 = 1 m (about 2.4 GHz free space), n = 3
  * receiver noise floor     N = -95 dBm
  * packet success           PRR(SINR_dB) = 1 / (1 + exp(-(SINR_dB - THETA)/W)),  THETA = 6 dB, W = 1 dB  (smooth stand-in for
                             a coded-packet waterfall; NOT a measured BER curve)
  * optional fading          Rayleigh power fading (exponential, mean 1) on every link and optional log-normal shadowing
  * 13 hop channels; a jammer occupies a subset of them in a given slot; the link hops uniformly at random.
Plain numpy + matplotlib so the tests run on the laptop (Python 3.10, numpy only, no scipy)."""
import os, json, math
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

M_DEF, P_JAM, P_CLEAN = 13, 0.95, 0.01      # copied from sim/ conventions (same as lab6)
PL0, N_EXP, D0 = 40.0, 3.0, 1.0
NOISE_DBM = -95.0
THETA, WIDTH = 6.0, 1.0
ARENA = 100.0                                 # metres, square arena


def save_json(name, obj):
    with open(os.path.join(OUT, name), "w") as f: json.dump(obj, f, indent=1, default=float)

def save_fig(fig, name):
    p = os.path.join(FIG, name); fig.savefig(p, bbox_inches="tight"); plt.close(fig); return p

def key(label, value):
    print(f"KEY NUMBER: {label} = {value}", flush=True)

# ---- radio model -------------------------------------------------------------------------------------------------------
def dbm2mw(x): return np.power(10.0, np.asarray(x, dtype=float) / 10.0)
def mw2dbm(x): return 10.0 * np.log10(np.maximum(np.asarray(x, dtype=float), 1e-300))
NOISE_MW = float(dbm2mw(NOISE_DBM))

def path_loss_db(d, n=None):
    n = N_EXP if n is None else n
    return PL0 + 10.0 * n * np.log10(np.maximum(d, D0) / D0)

def rx_mw(ptx_dbm, d, n=None):
    """mean received power in mW (no fading)"""
    return dbm2mw(np.asarray(ptx_dbm, dtype=float) - path_loss_db(d, n))

def prr(sinr_db):
    return 1.0 / (1.0 + np.exp(-(np.asarray(sinr_db, dtype=float) - THETA) / WIDTH))

def prr_from_mw(sig_mw, interf_mw=0.0):
    return prr(mw2dbm(sig_mw) - mw2dbm(NOISE_MW + interf_mw))

# ---- statistics --------------------------------------------------------------------------------------------------------
def t_crit(df):
    """two-sided 95% Student-t critical value (Cornish-Fisher expansion about z=1.96; error < 0.003 for df >= 10)"""
    z = 1.959964
    df = max(float(df), 1.0)
    return z + (z**3 + z) / (4 * df) + (5 * z**5 + 16 * z**3 + 3 * z) / (96 * df**2)

def ci95(x):
    """(mean, half-width) of a 95% t-interval over independent seeds"""
    x = np.asarray(x, dtype=float); n = len(x)
    if n < 2: return float(x.mean()), float("nan")
    return float(x.mean()), float(t_crit(n - 1) * x.std(ddof=1) / math.sqrt(n))

def fmt(x, d=3):
    m, h = ci95(x); return f"{m:.{d}f} +/- {h:.{d}f}"

def paired_ci(a, b):
    d = np.asarray(a, dtype=float) - np.asarray(b, dtype=float); return ci95(d)

# ---- geometry ----------------------------------------------------------------------------------------------------------
def polyline_points(waypoints, m):
    """m points equally spaced in arc length along a polyline"""
    wp = np.asarray(waypoints, dtype=float)
    seg = np.linalg.norm(np.diff(wp, axis=0), axis=1); cum = np.concatenate([[0], np.cumsum(seg)])
    s = np.linspace(0, cum[-1], m)
    x = np.interp(s, cum, wp[:, 0]); y = np.interp(s, cum, wp[:, 1])
    return np.stack([x, y], axis=1)

def grid_points(g, lo=0.0, hi=ARENA):
    xs = np.linspace(lo, hi, g); X, Y = np.meshgrid(xs, xs)
    return np.stack([X.ravel(), Y.ravel()], axis=1)

def dist(a, b):
    """pairwise distances: a (A,2), b (B,2) -> (A,B)"""
    return np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).sum(-1))

def random_instance(seed, n_way=4, m=40, g_j=50):
    """random patrol path (polyline of n_way waypoints), a base transmitter, jammer candidate grid"""
    rng = np.random.default_rng(seed)
    wp = rng.uniform(10, ARENA - 10, size=(n_way, 2))
    base = rng.uniform(20, ARENA - 20, size=2)
    path = polyline_points(wp, m)
    return dict(path=path, base=base, wp=wp, cand=grid_points(g_j, 0.0, ARENA))

# ---- minimal matrix-game solver (numpy only; independent check on the learning dynamics of e18) ------------------------
def solve_matrix_game(A):
    """Value and optimal row strategy of the zero-sum game max_x min_j x^T A[:, j], by a dense two-phase-free simplex
    (shift A > 0, LP: min sum(u) s.t. A^T u >= 1, u >= 0, solved as the dual max 1^T v s.t. A v <= 1 with Bland's rule).
    Returns (value, row_strategy x, column_strategy y)."""
    A = np.asarray(A, dtype=float); m, n = A.shape
    shift = 1.0 - A.min(); B = A + shift                      # all entries >= 1
    # dual LP for the column player: maximise sum(v) s.t. B v <= 1, v >= 0 ; value = 1/sum(v)
    T = np.zeros((m + 1, n + m + 1))
    T[:m, :n] = B; T[:m, n:n + m] = np.eye(m); T[:m, -1] = 1.0
    T[m, :n] = -1.0
    basis = list(range(n, n + m))
    for _ in range(10000):
        row = T[m, :-1]
        cand = np.where(row < -1e-12)[0]
        if len(cand) == 0: break
        j = cand[0]                                           # Bland
        col = T[:m, j]; pos = col > 1e-12
        if not pos.any(): raise RuntimeError("unbounded")
        ratios = np.full(m, np.inf); ratios[pos] = T[:m, -1][pos] / col[pos]
        r = int(np.argmin(ratios - 1e-15 * np.arange(m)))     # tie-break to lowest index
        T[r] /= T[r, j]
        for i in range(m + 1):
            if i != r: T[i] -= T[i, j] * T[r]
        basis[r] = j
    v = np.zeros(n)
    for i, b in enumerate(basis):
        if b < n: v[b] = T[i, -1]
    s = v.sum(); val = 1.0 / s - shift
    y = v / s
    u = T[m, n:n + m]                                         # duals of the slack columns give the row player's mix
    x = u / u.sum()
    return float(val), x, y
