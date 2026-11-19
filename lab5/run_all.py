"""Regenerates every lab5 figure and number file. Usage: python3 run_all.py [exp1 exp2 ...]  (default all; whole run takes about 3 minutes on a laptop-class CPU,
so run experiments one at a time if your shell has a time limit, e.g. python3 run_all.py exp4)."""
import sys, time, importlib
EXPS = {"exp1": "approx_correlator", "exp2": "fast_hop", "exp3": "relay_attack", "exp4": "soft_set", "exp5": "replay_mac", "exp6": "graceful", "exp7": "cfr_check"}
for k in (sys.argv[1:] or list(EXPS)):
    t = time.time(); print(f"===== {k}: {EXPS[k]}", flush=True); importlib.import_module(EXPS[k]).main(); print(f"[{k} done in {time.time() - t:.0f}s]", flush=True)
