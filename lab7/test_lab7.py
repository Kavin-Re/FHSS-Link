"""lab7 tests: assertion-based, one group per idea. `python3 test_lab7.py` (about 1-2 min). Exit code 1 if any check fails."""
import sys, glob, os, socket, time
import numpy as np
from _common import *

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append(bool(cond)); print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)

def t_b05():
    import b05_timing as m, hmac, hashlib
    tag = hmac.new(b"k", b"m", hashlib.sha256).digest()[:8]
    eq, it = m.early_exit_compare(tag, tag); check("B5 compare iterations = tag length when equal", eq and it == 8)
    wrong = bytes([tag[0] ^ 1]) + tag[1:]; check("B5 mismatch at byte 0 exits after 1 iteration", m.early_exit_compare(tag, wrong) == (False, 1))
    rec, q = m.attack_exact(tag); check("B5 noise-free attack recovers the full tag", rec == tag, f"{q} queries")
    check("B5 noise-free attack needs <= 8*256 queries", q <= 8 * 256)
    r = m.run(fast=True)
    check("B5 single measurement at sigma/delta=2 fails", r["tag_p"][2][0] < 0.01, f"{r['tag_p'][2][0]:.4f}")
    check("B5 sigma/delta=0.5 forged with n<=16", r["need_n"][0.5] is not None and r["need_n"][0.5] <= 16, str(r["need_n"][0.5]))
    ns = [r["need_n"][x] for x in (0.5, 1, 2, 4)]
    check("B5 repeats needed grow with noise", all(a is not None for a in ns) and ns == sorted(ns) and ns[0] < ns[-1], str(ns))
    check("B5 constant-time stays near chance (<=0.02 per byte)", max(r["ct_byte_p"].values()) <= 0.02, str(r["ct_byte_p"]))

def t_b06():
    import b06_carryoff as m
    r = m.run(fast=True)
    o = r["grades"]["OCXO-like (clk noise 0.03 m/step)"]; t = r["grades"]["TCXO-like (clk noise 0.3 m/step)"]
    check("B6 attack-free false alarm <= 3 % (both grades)", o["fa"] <= 0.03 and t["fa"] <= 0.03, f"{o['fa']:.3f} {t['fa']:.3f}")
    i5, i1, i02 = r["rates"].index(5.0), r["rates"].index(1.0), r["rates"].index(0.2)
    check("B6 fast drag (5 m/s) caught before 50 m error, both grades", o["safe"][i5] >= 0.9 and t["safe"][i5] >= 0.9, f"{o['safe'][i5]:.2f} {t['safe'][i5]:.2f}")
    check("B6 stable clock catches 1 m/s drag", o["safe"][i1] >= 0.9, f"{o['safe'][i1]:.2f}")
    check("B6 stable clock is at least as good as TCXO at 1 m/s", o["safe"][i1] >= t["safe"][i1] - 0.05 and o["det_delay_s"][i1] <= t["det_delay_s"][i1])
    check("B6 slow drag (0.2 m/s) evades within the window (honest limit)", o["safe"][i02] < 0.5, f"{o['safe'][i02]:.2f}")
    check("B6 undefended: 50 m error needs > 30 s at 1 m/s", o["undefended_t_to_harm_s"][i1] > 30)

def t_b12():
    import b12_fuzz as m, serial_proto as sp
    r = m.run(fast=True); so, ss = r["stats"]["orig"], r["stats"]["strict"]
    check("B12 original parser never raises", so["crash"] == 0, str(so["crash"])); check("B12 strict parser never raises", ss["crash"] == 0)
    check("B12 original parser accepts out-of-range fields (finding)", so["out_of_range"] > 0, str(so["out_of_range"]))
    check("B12 original parser accepts non-canonical forms (finding)", so["noncanon"] > 0, str(so["noncanon"]))
    check("B12 strict parser: 0 non-canonical and 0 out-of-range accepted", ss["noncanon"] == 0 and ss["out_of_range"] == 0)
    check("B12 round trip, both parsers", r["roundtrip_bad"] == 0)
    forged = "$FH,5,99,1,0,-50*%02X\n" % sp.crc8(b"FH,5,99,1,0,-50")
    check("B12 valid-CRC but ch=99 line: original accepts, strict rejects", sp.parse(forged) is not None and m.parse_strict(forged) is None)
    check("B12 strict parser accepts every canonical line", all(m.parse_strict(l) is not None for l in m.seed_lines(300, np.random.default_rng(0))))
    check("B12 CRC detects every burst <= 8 bits", r["burst_miss"] == 0)
    u = r["undetected"]
    check("B12 CRC detects all 1-, 3-, 5-bit body errors (odd weight)", u[1] == 0 and u[3] == 0 and u[5] == 0)
    check("B12 2-bit miss fraction matches period-127 pairs", 0.002 < u[2] < 0.005, f"{u[2]:.5f}")
    check("B12 4-bit miss fraction is of order 1/256", 0.002 < u[4] < 0.02, f"{u[4]:.5f}")
    check("B12 exhaustive 1- and 2-bit whole-line flips: none accepted with wrong content", r["whole_line"][1][0] == 0 and r["whole_line"][2][0] == 0, str(r["whole_line"]))
    check("B12 coverage-guided run reaches >= 14 of the parser's lines", r["coverage"]["lines"] >= 14, f"{r['coverage']['lines']}/{r['coverage']['total']}")

def t_b13():
    import b13_dolevyao as m
    from safety import Guard
    g = Guard(m.KEY, {3}); c, tag = Guard.make_token(m.KEY, 1)
    check("B13 guard accepts a good token once, rejects its replay", g.accept_token(0, c, tag) and not g.accept_token(1, c, tag))
    check("B13 guard rejects forged tag", not Guard(m.KEY, {3}).accept_token(0, 5, bytes(8)))
    r = m.run(fast=True); o, c2 = r["original"], r["challenge"]
    check("B13 exhaustive search covers > 5,000 sequences", o["sequences"] > 5000 and c2["sequences"] > 5000, f"{o['sequences']} {c2['sequences']}")
    check("B13 original protocol: S1 (stale authorisation) counterexample found", "S1" in o["violations"], str(sorted(o["violations"])))
    check("B13 original protocol: no replay (S2) or forgery (S3) violation", "S2" not in o["violations"] and "S3" not in o["violations"])
    check("B13 challenge-response fix: no violation of S1-S3", not c2["violations"], str(sorted(c2["violations"])))
    tr = o["violations"]["S1"]["trace"]; w = m.World("original")
    for a in tr: w.step(tuple(a))
    check("B13 counterexample replays to the violation", w.viol is not None and w.viol[0].startswith("S1"))

def t_b15():
    import b15_permleak as m
    r = m.run(fast=True); by = {m.label(x): x for x in r["results"]}
    check("B15 iid attacker hit ~ 1/M", abs(by["iid"]["hit"] - 1 / 13) < 0.012, f"{by['iid']['hit']:.4f}")
    check("B15 permutation epochs: hit ~ H_M/M (theory 0.2446)", abs(by["perm"]["hit"] - r["theory_perm"]) < 0.02, f"{by['perm']['hit']:.4f}")
    check("B15 permutation leaks >= 2.5x more than iid", by["perm"]["hit"] / by["iid"]["hit"] > 2.5)
    check("B15 permutation coverage: max gap <= 2M-1", by["perm"]["max_gap"] <= 25)
    f = {(x["L"], x["W"]): x for x in r["frontier"]}
    check("B15 guard(L=3,W=39) leaks less than permutation epochs", f[(3, 39)]["hit"] < by["perm"]["hit"] - 0.04, f"{f[(3,39)]['hit']:.3f}")
    check("B15 guard coverage guarantee holds (gap <= W)", all(x["max_gap"] <= x["W"] for x in r["frontier"]))
    check("B15 guard keeps channel usage near uniform", all(x["freq_dev"] < 0.02 for x in r["results"]))

def t_b16():
    import b16_traffic as m
    r = m.run(fast=True); p = {x["name"]: x for x in r["points"]}
    check("B16 estimator floor: shuffled labels give ~0 bits", r["mi_shuffled"] < 0.01, f"{r['mi_shuffled']:.4f}")
    check("B16 undefended link leaks > 0.5 bit", p["none"]["mi"] > 0.5, f"{p['none']['mi']:.3f}")
    check("B16 padding alone reduces but does not remove the leak", 0.1 < p["pad bursts"]["mi"] < p["none"]["mi"])
    check("B16 constant-rate cover T=40 drives the leak to ~0", p["cover T=40"]["mi"] < 0.01)
    cov = [x for x in r["points"] if x["name"].startswith("cover")]
    check("B16 leak falls and cost rises as the cover budget grows", all(a["mi"] >= b["mi"] - 0.02 for a, b in zip(cov, cov[1:])) and all(a["cost"] < b["cost"] for a, b in zip(cov, cov[1:])))
    check("B16 MI never exceeds log2(4)=2 bits", all(x["mi"] <= 2.0 for x in r["points"]))

def t_b20():
    import b20_fish as m
    r = m.run(fast=True); d = {n: i for i, n in enumerate(r["defs"])}; j = {n: i for i, n in enumerate(r["jams"])}; mat = np.array(r["delivery"])
    check("B20 JAR vs static jammer >= 0.95", mat[d["JAR"], j["static"]] >= 0.95, f"{mat[d['JAR'], j['static']]:.3f}")
    check("B20 JAR beats Thompson vs static jammer or ties within 0.03", mat[d["JAR"], j["static"]] >= mat[d["thompson"], j["static"]] - 0.03)
    check("B20 fixed channel vs static jammer collapses (<0.1)", mat[d["fixed"], j["static"]] < 0.1)
    check("B20 blind hopping ~0.8 against every jammer", np.all(np.abs(mat[d["blind"]] - 0.8) < 0.06), str(np.round(mat[d["blind"]], 3)))
    check("B20 pure JAR is beaten by the tracking jammer (honest failure, < 0.2)", mat[d["JAR"], j["tracker"]] < 0.2, f"{mat[d['JAR'], j['tracker']]:.3f}")
    check("B20 random dither (JAR+eps) restores delivery vs tracker (> 0.5)", mat[d["JAR+eps"], j["tracker"]] > 0.5, f"{mat[d['JAR+eps'], j['tracker']]:.3f}")

def t_b23():
    import b23_redblue as m
    out = m.loop(rounds=4, red_pop=6, slots=400, log_path=None)
    ents = out["entries"]
    check("B23 hash chain verifies", m.Referee.verify(ents))
    import copy
    bad = copy.deepcopy(ents); bad[5]["payload"] = {"tampered": 1}
    check("B23 tampering with a log entry is detected", not m.Referee.verify(bad))
    refused = [e for e in ents if e["action"] == "SUBMIT_REFUSED"]
    check("B23 all 4 hostile submissions were refused (not executed)", len(refused) == 4, str(len(refused)))
    check("B23 sandbox blocked socket inside the loop", out["socket_blocked"])
    check("B23 sandbox restored socket afterwards", socket.socket.__module__ == "socket")
    check("B23 validator rejects extra key, out-of-budget k, bad kind", not m.validate(dict(m.rand_prog(np.random.default_rng(0)), cmd="x"))[0] and not m.validate(dict(m.rand_prog(np.random.default_rng(0)), k=13))[0] and not m.validate(dict(m.rand_prog(np.random.default_rng(0)), kind="os"))[0])
    check("B23 every action is logged (round start, red, blue, referee)", {"red", "blue", "referee", "sandbox"} >= {e["actor"] for e in ents} and {"ROUND_START", "SUBMIT_RUN", "PATCH_EVAL", "PATCH_APPLIED", "END"} <= {e["action"] for e in ents})
    gv = (13 - 2) / 13 * 0.99 + 2 / 13 * 0.05
    final = out["history"][-1]["blue_worst_case"]
    check("B23 final blue worst case >= game value - 0.025 (uniform hopping guarantees it)", final >= gv - 0.025, f"{final:.3f} vs {gv:.3f}")
    check("B23 red's best attack never beats the game value by > 0.03", all(h["red_best_delivery"] >= gv - 0.03 for h in out["history"]))
    findings = {}
    for f in sorted(glob.glob(os.path.join(HERE, "b*.py"))):
        a = m.audit_source(f)
        if a: findings[os.path.basename(f)] = a
    check("B23 static audit: no forbidden imports or eval/exec in any lab7 script", not findings, str(findings))
    check("B23 scripts contain no network imports (socket only inside the sandbox module)", all(("import socket" not in open(f).read()) or f.endswith("b23_redblue.py") for f in glob.glob(os.path.join(HERE, "b*.py"))))

if __name__ == "__main__":
    only = sys.argv[1:]
    for name, fn in [("b05", t_b05), ("b06", t_b06), ("b12", t_b12), ("b13", t_b13), ("b15", t_b15), ("b16", t_b16), ("b20", t_b20), ("b23", t_b23)]:
        if only and name not in only: continue
        t0 = time.time(); print(f"--- {name}")
        try: fn()
        except Exception as e: import traceback; traceback.print_exc(); check(f"{name} raised {type(e).__name__}", False, str(e))
        print(f"    ({time.time()-t0:.1f} s)")
    print(f"\n{sum(RESULTS)}/{len(RESULTS)} checks passed" + ("  ALL PASSED" if all(RESULTS) else "  FAILURES"))
    sys.exit(0 if all(RESULTS) else 1)
