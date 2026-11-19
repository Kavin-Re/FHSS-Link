from link_sim import run, lfsr_hops
import numpy as np

def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name); assert cond

h = lfsr_hops(65535, 13)
st = lfsr_hops(65536, 2**16)
check("LFSR full period 65535 (all nonzero states once)", len(set(st[:65535])) == 65535 and st[65535] == st[0])
cnt = np.bincount(h, minlength=13) / len(h)
check("hop channels roughly uniform", cnt.max() - cnt.min() < 0.01)
r = run("static", M=13, slots=200000, hop=True, k=1)["pdr"]
check(f"FH static k=1 PDR {r:.3f} ~ analytic {(12/13)*0.99+(1/13)*0.05:.3f}", abs(r - ((12/13)*0.99+(1/13)*0.05)) < 0.005)
check("fixed link under static jammer is dead", run("static", hop=False)["pdr"] < 0.1)
check("ARQ raises PDR", run("static", max_tx=3)["pdr"] > run("static", max_tx=1)["pdr"])
check("excess drift without resync kills the link", run("static", drift=0.3)["pdr"] == 0.0)
print("ALL PASSED")
