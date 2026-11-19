"""Tiny dependency-free test runner: python3 run_tests.py  (runs every test_* function in test_*.py)."""
import glob, importlib, os, sys, time, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
def main():
    names = sorted(os.path.basename(f)[:-3] for f in glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_*.py")))
    npass = nfail = 0
    for n in names:
        mod = importlib.import_module(n)
        for fn in sorted(x for x in dir(mod) if x.startswith("test_")):
            t = time.time()
            try:
                getattr(mod, fn)(); npass += 1; print(f"PASS {n}.{fn} ({time.time()-t:.1f}s)")
            except Exception:
                nfail += 1; print(f"FAIL {n}.{fn}"); traceback.print_exc()
    print(f"\n{npass} passed, {nfail} failed"); return 1 if nfail else 0
if __name__ == "__main__":
    sys.exit(main())
