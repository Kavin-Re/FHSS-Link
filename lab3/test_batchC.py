"""Tests for lab3 batch C modules (survival codec, hash chain, LMS cancel, wifi survey tooling, venue model, packaging, dataset).
Run: python3 lab3/test_batchC.py   (prints PASS/FAIL per check, 'ALL PASSED' at the end, non-zero exit on the first failure)"""
import os, sys, json, math, shutil, stat, subprocess, tempfile, textwrap
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "sim"))


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name); assert cond, name


def sh(cmd, **kw): return subprocess.run(cmd, capture_output=True, text=True, **kw)


# ------------------------------------------------------------------ 1. survival codec
import survival_codec as sc
train = sc.make_trajs(8, 300, 1000); test = sc.make_trajs(3, 300, 900000)
c = sc.Codec(1, 5, 0.5, 1, keyint=20).train(train)
for f in sc.FIELDS:   # canonical Huffman: Kraft equality (complete prefix code) and prefix-free
    t = c.tables[f].enc; kraft = sum(2.0 ** -l for _, l in t.values()); words = [format(cd, f"0{l}b") for cd, l in t.values()]
    check(f"Huffman {f}: Kraft sum == 1 and prefix-free", abs(kraft - 1) < 1e-9 and not any(a != b and b.startswith(a) for a in words for b in words))
enc = sc.Encoder(c); dec = sc.Decoder(c); ok = True; maxe = 0.0; sizes = []
for m in test[0]:
    d = enc.send(m); sizes.append(len(d)); q, stale = dec.receive(d); r = c.dequant(q); ok &= (q == enc.prev) and not stale
    maxe = max(maxe, abs(r["x"] - m["x"]), abs(r["y"] - m["y"]))
check("encoder/decoder states identical for 300 messages (no drift)", ok)
check(f"position error <= half step ({maxe:.2f} m <= 0.5 m, + clipping at box edge)", maxe <= 0.5 + 1e-9)
check("delta messages much smaller than keyframes", np.mean(sizes) < 0.6 * 9 and max(sizes) <= 9 + 1)
check("keyframe is 9 bytes at 1 m / 5 deg", len(c.encode_key(test[0][0], 0)[0]) == 9)
# CRC: every single-bit flip inside the used bits is detected (flips of trailing pad bits are harmless)
enc = sc.Encoder(c); prev = None; pd = (0, 0); undetected = 0; flips = 0
for m in test[1][:60]:
    d = enc.send(m); kind, seq, q0 = c.decode(d, prev, pd)
    for bit in range(8 * len(d)):
        b = bytearray(d); b[bit // 8] ^= 1 << (7 - bit % 8)
        try: k2, s2, q2 = c.decode(bytes(b), prev, pd); undetected += (q2, s2, k2) != (q0, seq, kind)
        except ValueError: pass
        flips += 1
    pd = (q0["x"] - prev["x"], q0["y"] - prev["y"]) if (kind == 0 and prev) else (0, 0); prev = q0
check(f"CRC-8: wrong-content acceptances {undetected} of {flips} single-bit corruptions (< 0.5 %; not zero because variable-length parsing can misplace the CRC)", undetected / flips < 0.005)
# loss and resynchronisation
enc = sc.Encoder(c); dec = sc.Decoder(c, "gap"); msgs = [enc.send(m) for m in test[2][:60]]; states = []
for i, d in enumerate(msgs): states.append(dec.receive(None if i in (5, 6) else d))
check("gap detected: decoder reports stale after lost messages 5,6", states[5][1] and states[6][1] and states[7][1])
check("stale until next keyframe (msg 20), then state exact again", states[19][1] and (not states[20][1]) and states[20][0] == c.quant(test[2][20]))
dec = sc.Decoder(c, "gap"); st2 = [dec.receive(None if i == 20 else d) for i, d in enumerate(msgs)]
check("lost keyframe 20: stale through 21..39, recovered at keyframe 40", all(st2[i][1] for i in range(20, 40)) and (not st2[40][1]) and st2[40][0] == c.quant(test[2][40]))
r_all = sc.evaluate(sc.Codec(1, 5, 0.5, 1, keyint=1).train(train), test)["bytes_per_msg"]; r_d = sc.evaluate(c, test)["bytes_per_msg"]
check(f"delta+Huffman uses fewer bytes than all-keyframe ({r_d:.2f} < {r_all:.2f})", r_d < 0.6 * r_all)
r_hi = sc.evaluate(sc.Codec(1, 5, 0.5, 1).train(train), test); r_lo = sc.evaluate(sc.Codec(16, 20, 2, 5).train(train), test)
check("rate-distortion monotone: coarser quantisation => fewer bytes and larger error", r_lo["bytes_per_msg"] < r_hi["bytes_per_msg"] and r_lo["pos_rms"] > 5 * r_hi["pos_rms"])
lat, lon = sc.xy_to_latlon(1234.5, 6789.0); x, y = sc.latlon_to_xy(lat, lon)
check("lat/lon <-> metres round trip", abs(x - 1234.5) < 1e-6 and abs(y - 6789.0) < 1e-6)

# ------------------------------------------------------------------ 2. hash chain
import hashchain as hc
recs = [{"src": "t", "k": i, "v": f"decision {i}"} for i in range(50)]; lines = hc.build_lines(recs); v = hc.verify(lines)
check("hash chain: clean log verifies (50 records, 4 blocks)", v["ok"] and v["n_records"] == 50 and v["n_blocks"] == 4)
for kind in ("edit", "delete", "insert", "reorder"):
    n_ok = 0; rng = range(49) if kind == "reorder" else range(50)
    for i in rng:
        r = hc.verify(hc.tamper(lines, kind, i)); n_ok += (not r["ok"]) and r["first_bad"] == i
    check(f"hash chain: {kind} of ANY single record flagged at exactly that index ({n_ok}/{len(rng)})", n_ok == len(rng))
head = v["head"]; cut = lines[:-3]
check("truncating the tail is invisible alone but caught by an anchored head", hc.verify(cut)["ok"] and not hc.verify(cut, head=head)["ok"])
rw = hc.rewrite_from(lines, 20, "sha256", None, {"src": "forged"})
check("plain mode: a full recompute is accepted (integrity != authenticity) unless the head is anchored", hc.verify(rw)["ok"] and not hc.verify(rw, head=head)["ok"])
key = b"k" * 16; lh = hc.build_lines(recs, "hmac-sha256", key)
check("hmac mode verifies with the key, fails with a wrong key", hc.verify(lh, key=key)["ok"] and not hc.verify(lh, key=b"x" * 16)["ok"])
check("hmac mode: attacker without the key cannot rebuild a valid log", not hc.verify(hc.rewrite_from(lh, 20, "hmac-sha256", b"guess", {"src": "forged"}), key=key)["ok"])
hs = [l["hash"] for l in lines if l["t"] == "rec"][:16]; root = hc.merkle_root(hs)
check("Merkle inclusion proofs verify for all 16 leaves, not for a wrong leaf", all(hc.merkle_verify(hs[k], hc.merkle_proof(hs, k), root) for k in range(16)) and not hc.merkle_verify(hs[1], hc.merkle_proof(hs, 0), root))
check("sample_log.jsonl exists and verifies via CLI (exit 0)", sh([sys.executable, os.path.join(HERE, "verify_log.py"), os.path.join(HERE, "sample_log.jsonl")]).returncode == 0)
sl = open(os.path.join(HERE, "sample_log.jsonl")).read().splitlines(); srcs = {json.loads(l)["rec"]["src"] for l in sl if '"t": "rec"' in l}
check("sample log contains decisions from both ladder and guard", srcs == {"ladder", "guard"})
tmp = tempfile.mkdtemp(); bad = os.path.join(tmp, "bad.jsonl"); k = next(i for i, l in enumerate(sl) if '"i": 30,' in l)
sl2 = list(sl); sl2[k] = sl2[k].replace("allow", "deny", 1) if "allow" in sl2[k] else sl2[k].replace("guard", "gaurd", 1); open(bad, "w").write("\n".join(sl2) + "\n")
p = sh([sys.executable, os.path.join(HERE, "verify_log.py"), bad]); check("CLI verifier: edited line -> exit 1 and names record 30", p.returncode == 1 and "index = 30" in p.stdout)
check("CLI verifier: hmac log without key -> exit 2", sh([sys.executable, os.path.join(HERE, "verify_log.py"), os.path.join(HERE, "sample_log_hmac.jsonl")]).returncode == 2)
check("CLI verifier: hmac log with demo key -> exit 0", sh([sys.executable, os.path.join(HERE, "verify_log.py"), os.path.join(HERE, "sample_log_hmac.jsonl"), "--key-hex", b"demo-key-NOT-SECRET".hex()]).returncode == 0)

# ------------------------------------------------------------------ 3. LMS / NLMS / RLS cancellation
import lms_cancel as lc
d, s, intf, _, _ = lc.make_input(8000, 1)
check(f"input SINR is about -30 dB ({lc.sinr_db(s, intf):.1f})", -32 < lc.sinr_db(s, intf) < -29)
g = {a: lc.run_case(a, p, 1, N=8000)["gain"] for a, p in (("lms", 0.3), ("nlms", 0.3), ("rls", 0.998))}
check("LMS/NLMS/RLS each improve SINR by > 20 dB on a drifting tone + hum: " + str({k: round(v, 1) for k, v in g.items()}), all(v > 20 for v in g.values()))
check("wideband interferer cannot be cancelled (< 1 dB)", lc.run_case("nlms", 0.3, 1, N=8000, wideband=True)["gain"] < 1.0)
fast = lc.run_case("nlms", 0.3, 1, N=8000, hop_dwell=50)["gain"]
check(f"fast hopping defeats the canceller ({fast:.1f} dB vs {g['nlms']:.1f} dB stationary)", fast < g["nlms"] - 15)
check("step size sweep has an optimum (too small is slow, too large is noisy)", lc.run_case("lms", 0.001, 1, N=8000)["gain"] < lc.run_case("lms", 0.1, 1, N=8000)["gain"] and lc.run_case("lms", 0.1, 1, N=8000)["gain"] > lc.run_case("lms", 1.0, 1, N=8000)["gain"])
dd, ss, ii, bits, code = lc.make_input(25600, 3, Gp=64); sd = lc.despread_sinr(ii, code, 64)
check(f"despreading gain matches 10log10(Gp): bit SINR {sd:.1f} dB vs {lc.sinr_db(ss, ii) + 10*math.log10(64):.1f} dB", abs(sd - (lc.sinr_db(ss, ii) + 10 * math.log10(64))) < 1.5)

# ------------------------------------------------------------------ 4. wifi survey
script = os.path.join(HERE, "wifi_survey.sh")
check("wifi_survey.sh: bash -n syntax", sh(["bash", "-n", script]).returncode == 0)
src = open(script).read()
check("wifi_survey.sh: no sudo, no network-changing nmcli verbs, no SSID/BSSID fields requested", "sudo" not in src.replace("needs no sudo", "").replace("never needs sudo", "") and not any(w in src for w in ("nmcli dev wifi connect", "nmcli con", "nmcli radio", "iw dev $IFACE set", "ifconfig", "ip link set")) and "SSID,BSSID" not in src and "-f SSID" not in src)
fk = os.path.join(tmp, "fake"); os.makedirs(fk)
open(os.path.join(fk, "nmcli"), "w").write('#!/bin/sh\necho "$@" >> "$FAKE_ARGS"\nprintf "6:70:2437 MHz\\n1:45:2412 MHz\\n36:80:5180 MHz\\n11:30:2462 MHz\\n"\n'); os.chmod(os.path.join(fk, "nmcli"), 0o755)
env = dict(os.environ, PATH=fk + ":" + os.environ["PATH"], FAKE_ARGS=os.path.join(tmp, "args.txt")); out = os.path.join(tmp, "s.csv")
p = sh(["bash", script, "-n", "2", "-d", "0", "-o", out], env=env)
rows = [l.split(",") for l in open(out).read().splitlines() if not l.startswith("#")][1:]
check("fake nmcli: 3 x 2.4 GHz APs per scan x 2 scans appended (5 GHz row dropped)", p.returncode == 0 and len(rows) == 6 and {r[2] for r in rows} == {"6", "1", "11"})
check("fake nmcli: dBm estimate = pct/2-100", all(abs(float(r[5]) - (int(r[4]) / 2 - 100)) < 0.06 for r in rows) and [r[4] for r in rows[:3]] == ["70", "45", "30"])
check("script only asks nmcli for CHAN,SIGNAL,FREQ (never SSID/BSSID)", "-t -f CHAN,SIGNAL,FREQ dev wifi list" in open(os.path.join(tmp, "args.txt")).read() and all(len(r) == 6 for r in rows))
check("scan ids group scans (2 distinct ids, same salt)", len({r[1] for r in rows}) == 2 and len({r[1].split("-")[0] for r in rows}) == 1)
# iw fallback: nmcli exists but fails; iw prints BSSIDs and SSIDs that must not leak
open(os.path.join(fk, "nmcli"), "w").write("#!/bin/sh\nexit 1\n"); open(os.path.join(fk, "iw"), "w").write(textwrap.dedent("""\
    #!/bin/sh
    if [ "$1" = dev ] && [ -z "$2" ]; then printf 'phy#0\\n\\tInterface wlan9\\n'; exit 0; fi
    printf 'BSS aa:bb:cc:dd:ee:ff(on wlan9)\\n\\tfreq: 2437\\n\\tsignal: -55.00 dBm\\n\\tSSID: SecretCampusNet\\nBSS 11:22:33:44:55:66(on wlan9)\\n\\tfreq: 5180\\n\\tsignal: -40.00 dBm\\n\\tSSID: Five\\nBSS de:ad:be:ef:00:01(on wlan9)\\n\\tfreq: 2412\\n\\tsignal: -80.50 dBm\\n\\tSSID: Other\\n'
    """)); os.chmod(os.path.join(fk, "iw"), 0o755); out2 = os.path.join(tmp, "s2.csv"); p = sh(["bash", script, "-o", out2], env=env); txt = open(out2).read()
check("iw fallback works and leaks no SSID/BSSID text", p.returncode == 0 and "via iw" in p.stderr and "SecretCampusNet" not in txt and "aa:bb" not in txt and "Other" not in txt and txt.count("\n") == 4)
check("iw fallback values: ch 6 at -55 dBm -> 90 %, ch 1 at -80.5 -> 39 %", any(l.split(",")[2:6] == ["6", "2437", "90", "-55.0"] for l in txt.splitlines()) and any(l.split(",")[2:5] == ["1", "2412", "39"] for l in txt.splitlines()))
open(os.path.join(fk, "nmcli"), "w").write("#!/bin/sh\nexit 0\n"); out3 = os.path.join(tmp, "s3.csv"); p = sh(["bash", script, "-o", out3], env=env)
check("empty scan writes a channel-0 marker row", p.returncode == 0 and ",0,0,0,-100.0" in open(out3).read())
check("bad arguments rejected (exit 2)", sh(["bash", script, "-n", "abc"], env=env).returncode == 2 and sh(["bash", script, "-r", "maybe"], env=env).returncode == 2)
import wifi_survey as ws
syn = os.path.join(tmp, "synthetic_test.csv"); ws.synthesize(syn, seed=3, days=1)
check("synthetic file is labelled in its header", open(syn).readline().startswith("# SYNTHETIC DATA"))
synth, scans = ws.read_csv(syn); res = ws.analyse(scans); js = ws.to_json(res, synth, "synthetic_test.csv")
check("analyser carries the synthetic flag into the JSON", synth and js["synthetic"] is True and "ASSUMPTION" in js["mapping"])
check("loss probabilities within [0.01, 0.95] for all 13 channels", len(js["loss_by_channel"]) == 13 and all(0.01 <= v <= 0.95 for v in js["loss_by_channel"].values()))
check("effective channel numbers are sane: M_indep 3.7 < M_eff_sum < 13, M_orth 3", res["m_eff"]["M_orth"] == 3 and 3.7 < res["m_eff"]["M_eff_sum"] < 13 and res["m_eff"]["M_eff_ipr"] <= 13)
busiest = max(range(1, 14), key=lambda c: res["per_channel"][c]["aps_per_scan"]); check("busiest channel in the synthetic data is 1, 6 or 11", busiest in (1, 6, 11))
day = np.mean([res["by_hour"][h]["aps_per_scan"] for h in range(10, 16)]); night = np.mean([res["by_hour"][h]["aps_per_scan"] for h in (0, 1, 2, 3)])
check(f"time-of-day pattern shows the built-in daytime bump ({day:.1f} vs {night:.1f} APs/scan)", day > night + 3)
c1 = ws.loss_per_scan([(6, -50.0)], 0.1); check("overlap model: AP on ch 6 hurts ch 6 most, ch 1 not at all (11 not at all)", c1[5] > c1[3] > c1[2] and c1[0] == 0 and c1[10] == 0)
synth2, scans2 = ws.read_csv(out); check("real-format CSV (fake nmcli) is not flagged synthetic and has 2 scans", (not synth2) and len(scans2) == 2)
check("CLI analyse exits 0 and writes JSON", sh([sys.executable, os.path.join(HERE, "wifi_survey.py"), "analyse", syn, "--json", os.path.join(tmp, "j.json")]).returncode == 0 and os.path.exists(os.path.join(tmp, "j.json")))
check("shipped synthetic sample is named synthetic_*.csv and labelled", os.path.exists(os.path.join(HERE, "synthetic_wifi_survey.csv")) and "SYNTHETIC" in open(os.path.join(HERE, "synthetic_wifi_survey.csv")).readline())

# ------------------------------------------------------------------ 5. venue
import venue as ve
th = ve.analytic(30)["crit_attempt"]; m = ve.mc(30, T=20000, seed=11); n = m["n_crit"] + m["n_bulk"]; mcs = (m["crit_attempt"] * m["n_crit"] + m["bulk_attempt"] * m["n_bulk"]) / n
check(f"plain collision model: MC {mcs:.3f} vs theory {th:.3f} within 4 sigma", abs(mcs - th) < 4 * math.sqrt(th * (1 - th) / n))
a = ve.analytic(30, priority=True); mp = ve.mc(30, priority=True, T=20000, seed=12)
check(f"priority critical: MC {mp['crit_attempt']:.3f} vs exact analytic {a['crit_attempt']:.3f}", abs(mp["crit_attempt"] - a["crit_attempt"]) < 4 * math.sqrt(a["crit_attempt"] * (1 - a["crit_attempt"]) / mp["n_crit"]))
check(f"priority bulk (approximate analytic) within 0.02 of MC ({mp['bulk_attempt']:.3f} vs {a['bulk_attempt']:.3f})", abs(mp["bulk_attempt"] - a["bulk_attempt"]) < 0.02)
check("priority raises critical delivery and lowers bulk delivery at N=30", a["crit_msg"] > ve.analytic(30)["crit_msg"] + 0.3 and a["bulk_attempt"] < ve.analytic(30)["bulk_attempt"])
k0, k1 = ve.knee(13, False), ve.knee(13, True); check(f"knee (critical < 0.95): plain N={k0}, priority N={k1}; priority knee much later", k0 == 6 and k1 == 21)
check("delivery falls monotonically with N; more channels M moves the knee out", all(ve.analytic(n + 1)["crit_msg"] <= ve.analytic(n)["crit_msg"] for n in range(1, 100)) and ve.knee(32, True) > ve.knee(13, True) > ve.knee(8, True))
mi = ve.mc(10, T=20000, seed=3); check("Jain index: identical links ~1, extreme inequality low", ve.jain(mi["link_ok"] / mi["link_tx"]) > 0.99 and ve.jain([1, 0, 0, 0]) == 0.25 and ve.jain([2, 2, 2]) == 1.0)

# ------------------------------------------------------------------ 6. packaging
py = [sys.executable, "-m", "fhss_lab"]; kw = dict(cwd=ROOT)
p = sh(py + ["--help"], **kw); check("python -m fhss_lab --help lists the 4 subcommands", p.returncode == 0 and all(w in p.stdout for w in ("run", "emulate", "classify", "bench")))
check("each subcommand has --help", all(sh(py + [c, "--help"], **kw).returncode == 0 for c in ("run", "emulate", "classify", "bench")))
p = sh(py + ["run", "--nbits", "20000"], **kw); check("run prints a BER table and PDR rows", p.returncode == 0 and "JSR dB" in p.stdout and "M= 13: PDR" in p.stdout)
lg = os.path.join(tmp, "e.log"); p = sh(py + ["emulate", "--jammer", "sweep", "--slots", "300", "--out", lg], **kw)
from serial_proto import parse
L = open(lg).read().splitlines(); check("emulate writes 300 CRC-valid serial lines", p.returncode == 0 and len(L) == 300 and all(parse(l) for l in L))
p = sh(py + ["classify", "--train", "15", "--test", "10"], **kw); acc = float(p.stdout.split("softmax accuracy")[1].split()[0]) if p.returncode == 0 else 0
check(f"classify prints accuracies (softmax {acc:.2f} > 0.5)", acc > 0.5)
p = sh(py + ["bench", "--only", "test_proto.py", "test_safety.py"], **kw); check("bench runs sim tests with exit status", p.returncode == 0 and "ALL PASSED" in p.stdout)
for f in ("pyproject.toml", "Dockerfile", ".github/workflows/tests.yml"): check(f"{f} exists", os.path.exists(os.path.join(ROOT, f)))
wf = open(os.path.join(ROOT, ".github", "workflows", "tests.yml")).read(); check("workflow installs numpy matplotlib and runs ./run_tests.sh", "pip install numpy matplotlib" in wf and "./run_tests.sh" in wf)
check("fhss_lab re-exports sim modules lazily", sh([sys.executable, "-c", "import fhss_lab; print(fhss_lab.fhss_sim.qfunc(0.0), fhss_lab.link_sim.lfsr_hops(3, 13))"], **kw).stdout.startswith("0.5"))

# ------------------------------------------------------------------ 7. dataset
import make_dataset as md
a1 = md.generate(12); a2 = md.generate(12); check("dataset generation is deterministic (fixed seeds)", a1 == a2 and len(a1) == 60)
csvp = os.path.join(HERE, "dataset", "windows.csv"); import csv
rows = list(csv.DictReader(open(csvp))); check(f"dataset has >= 6000 windows ({len(rows)})", len(rows) >= 6000)
tr = [r for r in rows if r["split"] == "train"]; te = [r for r in rows if r["split"] == "test"]
check("split is 80/20 and stratified over 5 classes", abs(len(tr) / len(rows) - 0.8) < 0.01 and len({r["label"] for r in rows}) == 5 and all(sum(r["label"] == c for r in te) == len(te) // 5 for c in {r["label"] for r in rows}))
check("windows vary in M, duty and jammer strength", len({r["M"] for r in rows}) >= 4 and len({r["duty"] for r in rows}) >= 4 and len({round(float(r["p_jam"]), 1) for r in rows}) >= 4)
sys.path.insert(0, os.path.join(HERE, "dataset")); import baseline as bl
res = bl.main(csvp); check(f"baseline test accuracy: softmax {res['softmax']:.3f} > centroid {res['nearest centroid']:.3f} > majority {res['majority']:.3f}", res["softmax"] > res["nearest centroid"] > res["majority"] and res["softmax"] > 0.7)
logs = [f for f in os.listdir(os.path.join(HERE, "dataset", "raw")) if f.endswith(".log")]; check("raw serial logs present and parse", len(logs) >= 3 and all(parse(l) for f in logs for l in open(os.path.join(HERE, "dataset", "raw", f)).read().splitlines()[:50]))
check("dataset README states simulated + MIT", "SIMULATED" in open(os.path.join(HERE, "dataset", "README.md")).read() and "MIT" in open(os.path.join(HERE, "dataset", "README.md")).read())
shutil.rmtree(tmp, ignore_errors=True)
print("ALL PASSED")
