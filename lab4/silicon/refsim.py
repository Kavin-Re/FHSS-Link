"""Locate the existing FHSS-Link sim/ folder (link_sim.py, randtests.py) if importable.
Search order: $FHSS_SIM, ../../sim (when this folder is FHSS-Link/lab4/silicon), staged copy in the build container.
Everything here degrades gracefully: callers must check the returned module is not None."""
import os, sys, importlib
_HERE = os.path.dirname(os.path.abspath(__file__))
CANDIDATES = [os.environ.get("FHSS_SIM", ""), os.path.join(_HERE, "..", "..", "sim"),
              "/mnt/user-data/uploads/Github_projects/Projects/FHSS-Link/sim"]

def _find():
    for c in CANDIDATES:
        if c and os.path.isfile(os.path.join(c, "link_sim.py")):
            return os.path.abspath(c)
    return None

SIM_DIR = _find()

def load(name):
    """Import sim/<name>.py without modifying it. Returns module or None."""
    if SIM_DIR is None:
        return None
    if SIM_DIR not in sys.path:
        sys.path.append(SIM_DIR)
    try:
        return importlib.import_module(name)
    except Exception:
        return None
