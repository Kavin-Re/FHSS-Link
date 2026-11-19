#!/usr/bin/env python3
"""Cross-validation of the C reference against the Python references in the FHSS-Link repo.
usage: xval.py <path to build/xval> <FHSS-Link repo root>   (random but seeded; prints counts; exit 1 on any mismatch)
 - hop schedule vs rtl/hop_engine/model/hop_model.py : hop()  (random keys, slots incl. near 2^56, several M/RW/NCH)
 - serial encode/parse vs sim/serial_proto.py        (encode byte-exact; parse: C accepts a subset of Python, with equal values)
 - safety guard policy vs sim/safety.py              (the ORIGINAL source, run with its time constants rescaled seconds->ms by text substitution; token tag is SipHash in C vs HMAC in Python so tags are compared only as accept/reject)
 - ladder controller vs a transcription of the controller in sim/ladder.py (a transcription, so it checks the C port, not the design)"""
import sys, os, random, subprocess, importlib.util, hmac, hashlib
exe, root = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(root, "rtl/hop_engine/model")); sys.path.insert(0, os.path.join(root, "sim"))
import hop_model, serial_proto
rng = random.Random(20261028)
proc = subprocess.Popen([exe], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
def ask(line):
    proc.stdin.write(line + "\n"); proc.stdin.flush(); return proc.stdout.readline().rstrip("\n")
bad = {}; cnt = {}
def rec(name, ok, info=""):
    cnt[name] = cnt.get(name, 0) + 1
    if not ok:
        bad[name] = bad.get(name, 0) + 1
        if bad[name] <= 3: print("MISMATCH", name, info)
# ---- hop
for i in range(4000):
    key = rng.getrandbits(128); kb = key.to_bytes(16, "little")
    slot = rng.choice([rng.getrandbits(56), (1 << 56) - 1 - rng.randrange(50), rng.randrange(1000), rng.getrandbits(32)])
    M, RW, NCH = rng.choice([(13, 32, 2), (13, 8, 1), (13, 8, 4), (16, 32, 2), (37, 32, 2), (2, 32, 2), (1, 32, 2), (13, 6, 3), (200, 8, 2)])
    r = ask(f"H {kb.hex()} {slot} {M} {RW} {NCH}").split()
    ch, retries, first = hop_model.hop(key, slot, M, RW, NCH)
    rec("hop", r == ["0", str(ch), str(retries), str(first)], (hex(key), slot, M, RW, NCH, r, (ch, retries, first)))
# ---- serial encode
for i in range(3000):
    slot = rng.choice([rng.randrange(10), rng.getrandbits(32)]); ch = rng.randrange(256); ok = rng.randrange(2); rt = rng.randrange(256); rssi = rng.randrange(-128, 128)
    rec("serial_encode", ask(f"S {slot} {ch} {ok} {rt} {rssi}") + "\n" == serial_proto.encode(slot, ch, ok, rt, rssi))
# ---- serial parse: valid lines, and mutated lines
def parse_c(line):
    r = ask("P " + line.encode("latin-1").hex()).split()
    return None if r[0] == "ERR" else dict(slot=int(r[1]), ch=int(r[2]), ok=bool(int(r[3])), retries=int(r[4]), rssi=int(r[5]))
valid_lines = 0
for i in range(6000):
    line = serial_proto.encode(rng.getrandbits(32), rng.randrange(256), rng.randrange(2), rng.randrange(256), rng.randrange(-128, 128))
    m = rng.randrange(6)
    if m == 1: p = rng.randrange(len(line)); line = line[:p] + chr(rng.randrange(32, 127)) + line[p + 1:]
    elif m == 2: p = rng.randrange(len(line)); line = line[:p] + line[p + 1:]
    elif m == 3: line = line.replace("*", "") if rng.random() < .5 else line + "x"
    elif m == 4: line = line.replace("FH", "fh") if rng.random() < .5 else "  " + line.rstrip("\n") + "\r\n"
    elif m == 5: line = line.replace(",", ",+", 1)
    c, p = parse_c(line), serial_proto.parse(line)
    valid_lines += c is not None
    rec("serial_parse", (c is None) or (c == p), (line, c, p))                   # C accepts => Python accepts with equal values
    rec("serial_parse_reject_agree", (p is not None) or (c is None), (line, c, p))
    if p is not None and c is None: rec("serial_parse_C_stricter_count", True)    # allowed (documented): range/format strictness
print(f"  serial parse: C accepted {valid_lines} of 6000 mutated/valid lines")
# ---- guard (original Python source, ms-scaled)
src = open(os.path.join(root, "sim/safety.py")).read().replace("10.0", "10000.0")
ns = {}; exec(compile(src, "safety_ms", "exec"), ns); PG = ns["Guard"]
REASON = [("kill switch", 1), ("no valid token", 2), ("not in the own-link", 3), ("power level", 4), ("duty cycle", 5), ("continuous burst", 6)]
for trial in range(300):
    ask("GI"); pkey = bytes(range(16)); g = PG(pkey, set(range(8)), max_power=1, max_duty=0.10, max_burst_s=2000.0, token_ttl_s=5000.0)
    t = 0; ctr = 0; killed = False
    for step in range(rng.randrange(40, 400)):
        t += rng.choice([1, 1, 1, 2, 5, 20, 100, 700, 3000])
        k = rng.random()
        if k < 0.04:
            ctr += rng.choice([1, 1, 1, 0, 2]) if rng.random() < 0.8 else 1
            good = rng.random() < 0.7; c_acc = ask(f"GT {t} {ctr} {int(good)}") == "1"
            tag = g.make_token(pkey, ctr)[1] if good else bytes(8)
            p_acc = g.accept_token(t, ctr, tag); rec("guard_token", c_acc == p_acc, (trial, step, t, ctr, good, c_acc, p_acc))
        elif k < 0.045 and not killed and rng.random() < 0.3:
            g.kill(t); ask(f"GK {t}"); killed = True
        else:
            ch = rng.choice([0, 1, 3, 7, 8, 12]); pw = rng.choice([0, 0, 1, 2]); dt = rng.choice([1, 1, 5, 10, 50, 200, 800])
            c = int(ask(f"GR {t} {ch} {pw} {dt}")); okp, why = g.request(t, ch, pw, dt)
            pc = 0 if okp else next(code for key, code in REASON if key in why)
            rec("guard_request", c == pc, (trial, step, t, ch, pw, dt, c, why))
# ---- ladder controller
MODES = ["NORMAL", "ADAPT", "CODED", "SURVIVAL"]
def py_ladder(seq):
    mode = 0; hist = []; calm = 0; out = []
    for (ok, avoiding) in seq:
        hist.append(0 if ok else 1)
        loss = sum(hist[-50:]) / len(hist[-50:]) if len(hist) >= 20 else 0.0
        want = 0 if loss < 0.08 else 1 if loss < 0.25 else 2 if loss < 0.55 else 3
        if want > mode: mode = want; calm = 0
        elif want < mode:
            still = mode == 1 and avoiding
            calm = 0 if still else calm + 1
            if calm >= 100: mode = want; calm = 0
        else: calm = 0
        out.append(mode)
    return out
for trial in range(60):
    seq = []; p = rng.choice([0.0, 0.05, 0.2, 0.5, 0.9])
    for seg in range(rng.randrange(3, 9)):
        p = rng.choice([0.0, 0.02, 0.1, 0.2, 0.4, 0.7, 0.95]); av = rng.random() < 0.5
        seq += [(rng.random() >= p, av if rng.random() < 0.9 else not av) for _ in range(rng.randrange(30, 400))]
    exp = py_ladder(seq); ask("LI")
    got = [int(ask(f"LS {i} {int(ok)} {rng.randrange(13)} {int(av)}").split()[0]) for i, (ok, av) in enumerate(seq)]
    rec("ladder", got == exp, (trial, next((i for i, (a, b) in enumerate(zip(got, exp)) if a != b), -1)))
proc.stdin.close()
for k in sorted(cnt): print(f"  {k:32s} {cnt[k]:6d} cases, {bad.get(k, 0)} mismatches")
sys.exit(1 if bad else 0)
