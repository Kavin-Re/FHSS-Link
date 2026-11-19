"""Tiny helper so long scripts can be run in short slices (LAB2_CACHE=1 LAB2_BUDGET=40 python3 x.py, repeat until done).
Without those environment variables everything just runs straight through and nothing is cached."""
import os, sys, time, pickle, io, contextlib

T0 = time.time()
BUDGET = float(os.environ.get("LAB2_BUDGET", "1e12"))
USE = os.environ.get("LAB2_CACHE") == "1"
CDIR = os.path.join(os.path.expanduser("~"), ".lab2cache")


def step(mod, name, fn):
    """fn() prints normally and returns a value; printed text is cached and replayed with the value."""
    path = os.path.join(CDIR, f"{mod}_{name}.pkl")
    if USE and os.path.exists(path):
        with open(path, "rb") as f: val, text = pickle.load(f)
    else:
        if time.time() - T0 > BUDGET:
            print("BUDGET_EXHAUSTED before step", name, flush=True); sys.exit(3)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            val = fn()
        text = buf.getvalue()
        if USE:
            os.makedirs(CDIR, exist_ok=True)
            with open(path, "wb") as f: pickle.dump((val, text), f)
    sys.stdout.write(text); sys.stdout.flush()
    return val
