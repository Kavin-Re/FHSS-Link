"""Regenerates every lab6 figure, number file and the scorecard. Usage: python3 run_all.py [exp1 ... exp8]. Whole run about 1 minute."""
import sys, time, importlib
EXPS = {"exp1": "exp1_bandit_poison", "exp2": "exp2_learning_rate", "exp3": "exp3_control_plane", "exp4": "exp4_time_push", "exp5": "exp5_prng_graveyard",
        "exp6": "exp6_keyfromair_drain", "exp7": "exp7_myopic_jammer", "exp8": "exp8_scorecard"}
for k in (sys.argv[1:] or list(EXPS)):
    t = time.time(); print(f"===== {k}: {EXPS[k]}", flush=True); importlib.import_module(EXPS[k]).main(); print(f"[{k} done in {time.time() - t:.0f}s]", flush=True)
