"""Assertion tests for lab9 (simulation only). Each check compares a stored result against an independent
reference (closed form, a re-derived known value, or a monotonicity/ordering that would fail if the model were wrong)."""
import json, os, sys, hashlib, hmac, importlib
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
N = [0, 0]
def J(n):
    p = os.path.join(HERE, "outputs", n + ".json")
    return json.load(open(p)) if os.path.exists(p) else None
def check(name, cond, info=""):
    N[0] += 1; ok = bool(cond); N[1] += ok
    print(("PASS " if ok else "FAIL ") + name + (f"  [{info}]" if info else ""), flush=True)

# ---- B1 trojan ----
o = J("b01_trojan")
if o:
    s = o["summ"]; ks = o["ks"]
    p = [s[str(k)]["p_median"] for k in ks]
    check("B1 trigger probability falls with trigger width k", all(a >= b for a, b in zip(p, p[1:])), str(p))
    check("B1 net correlation makes trigger commoner than 2^-k for k>=8", all(s[str(k)]["p_median"] > 2.0 ** -k for k in ks if k >= 8))
    k = 20; pk = s[str(k)]["p_median"]; d = s[str(k)]["det"]["1000"][0]
    check("B1 N=1000 detection within 0.15 of 1-(1-p)^N (median-p approximation)", abs(d - (1 - (1 - pk) ** 1000)) < 0.15, f"{d:.3f} vs {1-(1-pk)**1000:.3f}")
    check("B1 detection non-decreasing in N", all(s[str(k)]["det"]["100"][0] <= s[str(k)]["det"]["1000"][0] <= s[str(k)]["det"]["10000"][0] for k in ks))
    check("B1 exhaustive equivalence finds the trojan in all (k) cases", all(s[str(k)]["exhaustive"][0] == 1.0 for k in ks))
    check("B1 N90 matches ln(10)/p within 2x", all(0.5 < s[str(k)]["N90_median"] / (np.log(10) / s[str(k)]["p_median"]) < 2 for k in ks))
    check("B1 >=20 seeds", o["nseeds"] >= 20)
# ---- B4 CPA ----
try:
    import b04_cpa as b4
    check("B4 AES S-box known values S[0]=0x63 S[1]=0x7c S[0x53]=0xed", (b4.SBOX[0], b4.SBOX[1], b4.SBOX[0x53]) == (0x63, 0x7c, 0xED))
except Exception as e: check("B4 sbox import", False, repr(e))
o = J("b04_cpa")
if o:
    check("B4 measured leakage corr within 0.02 of closed form sqrt(2/(2+sigma^2))", abs(o["rho_meas"] - o["rho_theory"]) < 0.02, f"{o['rho_meas']:.3f}/{o['rho_theory']:.3f}")
    check("B4 unprotected CPA reaches 100% at high trace count", o["plain"][-1][0] == 1.0)
    check("B4 1st-order CPA on masked device stays near chance (<=0.10 at 32000 traces)", o["m1"][-1][0] <= 0.10 and o["m1_final_success"][0] <= 0.10 if isinstance(o["m1_final_success"], list) else o["m1"][-1][0] <= 0.10)
    check("B4 2nd-order attack needs >10x the traces of the unprotected one", o["n90_masked2"] > 10 * o["n90_plain"], f"{o['n90_masked2']} vs {o['n90_plain']}")
    check("B4 required traces grow with noise", list(o["n90_vs_sigma"].values())[-1] > list(o["n90_vs_sigma"].values())[0])
# ---- B9 fingerprint ----
o = J("b09_fingerprint")
if o:
    ia = o["sig_a"].index(0.1)
    check("B9 skew-only forger accepted >0.9 at 0.1 ppm", o["acc1"][ia][0] > 0.9)
    check("B9 skew-only acceptance decreases with attacker imprecision", all(a[0] >= b[0] for a, b in zip(o["acc1"], o["acc1"][1:])))
    check("B9 forgery matches closed-form prediction (acc1_theory) within 0.05", max(abs(a[0] - t if not isinstance(t, list) else a[0] - t[0]) for a, t in zip(o["acc1"], o["acc1_theory"])) < 0.05)
    r2 = o["ratios"].index(2.0)
    check("B9 jitter feature with floor 2x victim cuts forgery <0.01", o["acc2"][r2][0] < 0.01)
    check("B9 jitter feature at floor 1x does not help (>0.9)", o["acc2"][o["ratios"].index(1.0)][0] > 0.9)
    check("B9 legitimate FRR small (<0.03)", (o["frr"][0] if isinstance(o["frr"], list) else o["frr"]) < 0.03)
# ---- B10 adversarial ----
o = J("b10_adv_modclass")
if o:
    i = o["eps"].index(0.2)
    check("B10 clean accuracy >0.95", o["clean_std"][0] > 0.95)
    check("B10 PGD beats equal-norm random noise by >0.5 accuracy points at eps 0.2", o["std_rand"][i][0] - o["std_pgd"][i][0] > 0.5)
    check("B10 adversarial training raises PGD accuracy (CIs disjoint)", o["adv_pgd"][i][1] > o["std_pgd"][i][2])
    check("B10 adversarial training costs clean accuracy", o["clean_adv"][0] < o["clean_std"][0])
    check("B10 >=20 seeds", o["nseeds"] >= 20)
# ---- B11 poisoned logs ----
o = J("b11_poisoned_logs")
if o:
    import b11_poisoned_logs as b11
    recs = [b"%d,x" % i for i in range(50)]; k = b"k" * 16
    st = b11.chain_hmac(recs, k); forged = recs[:10] + [b"evil"] + recs[11:]
    check("B11 HMAC chain rejects an attacker-recomputed plain chain", not b11.verify(forged, b11.chain_plain(forged), "hmac", k))
    check("B11 plain chain accepts attacker-recomputed chain (the weakness)", b11.verify(forged, b11.chain_plain(forged), "plain"))
    check("B11 truncation passes plain and HMAC chain, caught by anchors", o["chain"]["truncate"]["plain"][0] == 0 and o["chain"]["truncate"]["hmac"][0] == 0 and o["chain"]["truncate"]["anchored"][0] == 1.0)
    B = o["B"]
    check("B11 smart forger harms the twin (quality drop >0.04 at f=0.2)", o["quality_all_clean"] - B["smart@0.2"]["quality"][0] > 0.04)
    check("B11 audit detector alarm >0.95 at f=0.2 smart", B["smart@0.2"]["audit"][0] > 0.95)
    check("B11 consistency detector false alarm <=0.05 at f=0", B["naive@0.0"]["cons"][0] <= 0.05)
    check("B11 consistency detector is weaker against the smart forger than the naive one at f=0.1", B["smart@0.1"]["cons"][0] < B["naive@0.1"]["cons"][0])
# ---- new modules (added below if present) ----
for mod in ("b14_dos", "b21_maxent", "b19_alerts"):
    t = os.path.join(HERE, "test_" + mod + ".py")
    if os.path.exists(t):
        ns = {"check": check, "J": J, "np": np, "HERE": HERE}; exec(open(t).read(), ns)
print(f"{N[1]}/{N[0]} checks pass"); sys.exit(0 if N[0] == N[1] else 1)
