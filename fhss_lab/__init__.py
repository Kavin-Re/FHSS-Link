"""fhss_lab: thin, importable wrappers around the FHSS-Link simulators in ../sim (the originals stay where they are; nothing is copied).

The sim/ modules import each other by bare name, so the sim directory is appended to sys.path. Locate it with the FHSS_SIM_DIR environment
variable, otherwise <repo>/sim next to this package (works from a checkout or `pip install -e .`; a plain wheel install has no sim/ and says so).
Re-exports (lazy, only imported when used): fhss_sim, link_sim, adaptive, classify, fec, ladder, safety, serial_proto, emu_device.
"""
import os, sys, importlib
from pathlib import Path

__version__ = "0.1.0"


def sim_dir() -> Path:
    env = os.environ.get("FHSS_SIM_DIR")
    p = Path(env) if env else Path(__file__).resolve().parent.parent / "sim"
    if not (p / "fhss_sim.py").exists():
        raise ImportError(f"sim directory not found at {p}; run from a repository checkout or set FHSS_SIM_DIR")
    return p


def _load(name):
    d = str(sim_dir())
    if d not in sys.path: sys.path.append(d)
    return importlib.import_module(name)


_MODS = ("fhss_sim", "link_sim", "adaptive", "classify", "fec", "ladder", "safety", "serial_proto", "emu_device")


def __getattr__(name):
    if name in _MODS:
        m = _load(name); globals()[name] = m; return m
    raise AttributeError(name)


# ---- convenience wrappers (same models, same numbers as the sim/ scripts)
def ber_table(ebn0_db=10.0, jsr_db=(0.0, 10.0, 20.0), nbits=100_000, M=13, Gp=32):
    """Rows: (JSR dB, BER fixed, BER FH, BER DS) from fhss_sim.simulate_ber (Monte Carlo)."""
    s = _load("fhss_sim"); rows = []
    for j in jsr_db:
        rows.append((j, s.simulate_ber("fixed", ebn0_db, j, nbits), s.simulate_ber("fh", ebn0_db, j, nbits, M=M, k=1), s.simulate_ber("ds", ebn0_db, j, min(nbits, 40_000), Gp=Gp)))
    return rows


def pdr_table(M_list=(1, 4, 13, 32), ebn0_db=10.0, jsr_db=10.0, L=256):
    """Rows: (M, theoretical PDR with one jammed channel) from fhss_sim.pdr_theory."""
    s = _load("fhss_sim"); return [(M, s.pdr_theory(ebn0_db, 10 ** (jsr_db / 10), M, 1, L)) for M in M_list]


def emulate(defender="blind", jammer="static", slots=3000, M=13, seed=1):
    """Generator of serial-format lines ($FH,...*CRC) from sim/emu_device.py."""
    e = _load("emu_device")
    for line, _ in e.emulate(defender, jammer, M=M, slots=slots, seed=seed): yield line


def classifier_accuracy(n_train=40, n_test=30, seed=0):
    """Quick accuracy of the rule-based and softmax classifiers of sim/classify.py on freshly simulated windows."""
    import numpy as np
    c = _load("classify")
    def make(n, off):
        X, y = [], []
        for i in range(n):
            for ci, k in enumerate(c.CLASSES): X.append(c.sim_window(k, seed=off + i * 7 + ci)); y.append(ci)
        return np.array(X), np.array(y)
    Xtr, ytr = make(n_train, seed); Xte, yte = make(n_test, seed + 10**6); m = c.softmax_train(Xtr, ytr, len(c.CLASSES))
    return dict(rule=float((np.array([c.CLASSES.index(c.rule(f)) for f in Xte]) == yte).mean()), softmax=float((c.softmax_predict(m, Xte) == yte).mean()), n_test=len(yte))
