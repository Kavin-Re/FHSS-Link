"""Beyond #12: property-based + coverage-guided fuzzing of the serial line parser and its CRC-8 (simulation only, offline strings).
Target: sim/serial_proto.py (imported read-only). Hardened comparison parser `parse_strict` lives HERE (the original is untouched).
Properties checked on every input: P1 never raises; P2 encode->parse round trip; P3 accepted lines are canonical (re-encoding equals the input);
P4 accepted fields are in range (ch 0..13, ok in {0,1}, retries 0..15, rssi -120..0, slot >= 0); P5 corrupted-but-accepted lines keep the original content.
CRC part: exact syndrome analysis of undetected error patterns by Hamming weight (CRC-8 poly 0x07 is linear with init 0)."""
import sys, re, random, itertools
import numpy as np
from _common import *
import serial_proto as sp

LINE_RE = re.compile(r"\$FH,(0|[1-9][0-9]{0,8}),([0-9]|1[0-3]),([01]),([0-9]|1[0-5]),(0|-[1-9][0-9]{0,2})\*([0-9A-F]{2})", re.ASCII)

def parse_strict(line):
    """Hardened parser: ASCII canonical form only, ranges enforced, one line, bounded length."""
    if not isinstance(line, str) or len(line) > 64: return None
    if line.endswith("\r\n"): line = line[:-2]
    elif line.endswith("\n"): line = line[:-1]
    m = LINE_RE.fullmatch(line)
    if not m: return None
    slot, ch, ok, ret, rssi, tag = m.groups()
    body = line[1:line.rindex("*")]
    if int(tag, 16) != sp.crc8(body.encode()): return None
    rssi = int(rssi)
    if not -120 <= rssi <= 0: return None
    return dict(slot=int(slot), ch=int(ch), ok=bool(int(ok)), retries=int(ret), rssi=rssi)

def in_range(d):
    return d["slot"] >= 0 and 0 <= d["ch"] <= 13 and 0 <= d["retries"] <= 15 and -120 <= d["rssi"] <= 0

def seed_lines(n, rng):
    return [sp.encode(int(rng.integers(0, 10**6)), int(rng.integers(0, 13)), int(rng.integers(0, 2)),
                      int(rng.integers(0, 4)), int(rng.integers(-95, -30))) for _ in range(n)]

ALIAS = ["+", "-", " ", "_", "0x", "٣", "０", "\t", "00", "1e3", "9" * 20, "\x00", "\n", ",", "*", "$"]
def mutate(line, rng, py):
    """Returns (mutated string, kind). kinds: blind | crcfix."""
    b = bytearray(line.encode("latin-1"))
    kind = "blind"
    op = rng.integers(0, 9)
    if op == 0:
        for _ in range(int(rng.integers(1, 5))):
            i = int(rng.integers(len(b))); b[i] ^= 1 << int(rng.integers(8))
    elif op == 1:
        b[int(rng.integers(len(b)))] = int(rng.integers(256))
    elif op == 2:
        b.insert(int(rng.integers(len(b) + 1)), int(rng.integers(256)))
    elif op == 3 and len(b) > 1:
        del b[int(rng.integers(len(b)))]
    elif op == 4:
        b = b[: int(rng.integers(len(b) + 1))]
    elif op == 5:
        b = b + bytearray(line.encode("latin-1"))             # two lines glued together
    elif op == 6:
        s = ALIAS[int(rng.integers(len(ALIAS)))]
        i = int(rng.integers(len(b) + 1)); b[i:i] = bytearray(s.encode("latin-1", "replace"))
    else:
        # structure-aware: mutate a field (even to out-of-range values) and recompute a VALID CRC (buggy firmware or a forger)
        f = ["FH", str(int(rng.integers(0, 10**6))), str(py.choice([-5, 0, 7, 12, 13, 14, 99, 99999, 2 ** 31])),
             str(py.choice([0, 1, 2, -1, 7])), str(py.choice([0, 3, 99, -4])), str(py.choice([-60, 0, 25, -300, 1000]))]
        body = ",".join(f)
        return f"${body}*{sp.crc8(body.encode()):02X}\n", "crcfix"
    return bytes(b).decode("latin-1"), kind

def content(d): return None if d is None else (d["slot"], d["ch"], d["ok"], d["retries"], d["rssi"])

def fuzz(n, seed=3):
    rng = np.random.default_rng(seed); py = random.Random(seed)
    seeds = seed_lines(100, rng)
    st = {p: {"crash": 0, "noncanon": 0, "out_of_range": 0, "silent_corrupt": 0, "accepted": 0} for p in ("orig", "strict")}
    examples = {}
    for it in range(n):
        s = seeds[it % len(seeds)]
        m, kind = mutate(s, rng, py)
        for name, fn in (("orig", sp.parse), ("strict", parse_strict)):
            try:
                d = fn(m)
            except Exception as e:                                   # P1
                st[name]["crash"] += 1; examples.setdefault((name, "crash"), (m, repr(e))); continue
            if d is None: continue
            st[name]["accepted"] += 1
            if m.strip() != sp.encode(d["slot"], d["ch"], d["ok"], d["retries"], d["rssi"]).strip():   # P3
                st[name]["noncanon"] += 1; examples.setdefault((name, "noncanon"), (m, d))
            if not in_range(d):                                       # P4
                st[name]["out_of_range"] += 1; examples.setdefault((name, "out_of_range"), (m, d))
            if kind == "blind" and m != s and content(d) != content(sp.parse(s)):   # P5
                st[name]["silent_corrupt"] += 1; examples.setdefault((name, "silent_corrupt"), (m, d, s))
    return st, examples

def roundtrip(n, seed=5):
    rng = np.random.default_rng(seed); bad = 0
    for _ in range(n):
        a = (int(rng.integers(0, 10**9)), int(rng.integers(0, 14)), int(rng.integers(0, 2)), int(rng.integers(0, 16)), int(rng.integers(-120, 1)))
        for fn in (sp.parse, parse_strict):
            d = fn(sp.encode(*a))
            if d is None or content(d) != (a[0], a[1], bool(a[2]), a[3], a[4]): bad += 1
    return bad

def coverage_fuzz(n, seed=9):
    """Greedy coverage-guided mutation: keep inputs that reach a new line of serial_proto.parse/crc8 (sys.settrace)."""
    rng = np.random.default_rng(seed); py = random.Random(seed)
    code_files = sp.__file__.rstrip("c")
    seen = set(); cur = set()
    def tracer(frame, event, arg):
        if frame.f_code.co_filename.rstrip("c") == code_files:
            if event == "line": cur.add(frame.f_lineno)
            return tracer
        return None
    lines_total = {ln for fn in (sp.parse, sp.crc8) for _, _, ln in fn.__code__.co_lines() if ln}
    corpus = seed_lines(5, rng); kept = 0; hist = []
    for it in range(n):
        s = corpus[int(rng.integers(len(corpus)))]
        m, _ = mutate(s, rng, py)
        cur.clear(); sys.settrace(tracer)
        try: sp.parse(m)
        except Exception: pass
        finally: sys.settrace(None)
        new = cur - seen
        if new:
            seen |= cur; corpus.append(m); kept += 1
        if it % 200 == 0: hist.append((it, len(seen & lines_total)))
    return len(seen & lines_total), len(lines_total), kept, hist

# ---------- CRC syndrome analysis ----------
def syndromes(nchars):
    """Syndrome (CRC change) of flipping each bit of an nchars-long body (init 0 => CRC is linear in the data)."""
    zero = bytes(nchars); base = sp.crc8(zero); out = []
    for i in range(nchars * 8):
        b = bytearray(zero); b[i // 8] ^= 0x80 >> (i % 8); out.append(sp.crc8(bytes(b)) ^ base)
    return np.array(out, dtype=np.int64)

def undetected_by_weight(nchars=22, rng=None, samples=400000):
    """Fraction of body-only w-bit error patterns whose syndrome is 0 (=undetected by CRC-8): exact w<=3, exact w=4 via pair counts, sampled w>=4."""
    s = syndromes(nchars); n = len(s); res = {}
    res[1] = float(np.mean(s == 0))
    # exact w=2: pairs i<j with s_i == s_j
    cnt = np.bincount(s, minlength=256)
    res[2] = float(sum(c * (c - 1) // 2 for c in cnt) / (n * (n - 1) / 2))
    # w=3: triple with s_i^s_j^s_k == 0 -> for each pair look up the third; count triples (each counted 3 times)
    iu = np.triu_indices(n, 1); ps = s[iu[0]] ^ s[iu[1]]
    cnt_s = np.bincount(s, minlength=256)
    trip3 = int(np.sum(cnt_s[ps]))                                    # includes k==i or k==j cases (only if s==0) and repeats
    # remove degenerate: k in {i,j} requires s_k == s_i^s_j  (i.e. s_j==0 or s_i==0); none exist when no zero syndromes
    zero_pos = int(np.sum(s == 0))
    res[3] = float(trip3 / 3 / (n * (n - 1) * (n - 2) / 6)) if zero_pos == 0 else float("nan")
    # w=4 and above: sampled (odd weights are all detected because x+1 divides the polynomial)
    for w in (4, 5, 6):
        hit = 0
        for _ in range(samples):
            idx = rng.choice(n, w, replace=False); x = 0
            for i in idx: x ^= int(s[i])
            hit += (x == 0)
        res[w] = hit / samples
    return res, s

def burst_check(nchars=22):
    """Every burst error of length <= 8 bits anywhere in the body changes the CRC (CRC-8 guarantee)."""
    s = syndromes(nchars); miss = 0
    for start in range(nchars * 8 - 7):
        for pat in range(1, 256):
            x = 0
            for j in range(8):
                if pat >> j & 1: x ^= int(s[start + j])
            miss += (x == 0)
    return miss

def whole_line_flips(rng, nsamp=60000):
    """Real parser on the whole line (body + tag + framing): all 1- and 2-bit flips of one line exactly, 3- and 4-bit by sampling."""
    line = sp.encode(4242, 7, 1, 0, -61); raw = line.encode(); nb = len(raw) * 8
    ref = content(sp.parse(line)); out = {}
    def accepted_wrong(bits):
        b = bytearray(raw)
        for i in bits: b[i // 8] ^= 1 << (i % 8)
        try: d = sp.parse(bytes(b).decode("latin-1"))
        except Exception: return None
        return d is not None and content(d) != ref
    for w in (1, 2):
        tot = bad = 0
        for bits in itertools.combinations(range(nb), w):
            tot += 1; bad += bool(accepted_wrong(bits))
        out[w] = (bad, tot)
    for w in (3, 4):
        bad = 0
        for _ in range(nsamp):
            bits = rng.choice(nb, w, replace=False); bad += bool(accepted_wrong(bits))
        out[w] = (bad, nsamp)
    return out

def period_pairs(nlines=300, seed=21):
    """CRC-8/0x07 has period 127 (x^127 = 1 mod g): two flips exactly 127 (or 254) bits apart in the body leave the CRC unchanged.
    Our lines have 130-150 body bits, so such pairs exist. Count how many produce an ACCEPTED line with different content."""
    rng = np.random.default_rng(seed); tried = bad = 0; ex = None
    for line in seed_lines(nlines, rng):
        raw = line.encode(); ref = content(sp.parse(line)); nbody = (line.rindex("*") - 1) * 8
        for dist in (127, 254):
            for i in range(8, nbody - dist + 8):                      # bit index counted from the start of the line, body starts at byte 1
                j = i + dist
                if j >= 8 + nbody: break
                b = bytearray(raw); b[i // 8] ^= 1 << (i % 8); b[j // 8] ^= 1 << (j % 8); tried += 1
                d = sp.parse(bytes(b).decode("latin-1"))
                if d is not None and content(d) != ref:
                    bad += 1; ex = ex or (line.strip(), bytes(b).decode("latin-1").strip(), content(d))
    return dict(tried=tried, accepted_wrong=bad, example=ex)

def run(fast=False):
    rng = np.random.default_rng(1)
    n = 20000 if fast else 120000
    st, ex = fuzz(n)
    rt = roundtrip(500 if fast else 3000)
    cov = coverage_fuzz(3000 if fast else 15000)
    und, syn = undetected_by_weight(22, rng, 40000 if fast else 300000)
    bur = burst_check(22)
    wl = whole_line_flips(rng, 5000 if fast else 60000)
    pp = period_pairs(100 if fast else 300)
    return dict(n=n, stats=st, examples={f"{k[0]}:{k[1]}": v for k, v in ex.items()}, roundtrip_bad=rt,
                coverage=dict(lines=cov[0], total=cov[1], kept=cov[2], hist=cov[3]), undetected=und, burst_miss=bur, whole_line=wl, period_pairs=pp)

def main():
    r = run()
    print("fuzz inputs:", r["n"])
    for name in ("orig", "strict"): print(name, r["stats"][name])
    for k, v in r["examples"].items(): print("  example", k, repr(v)[:110])
    print("roundtrip failures:", r["roundtrip_bad"], "| coverage:", r["coverage"]["lines"], "of", r["coverage"]["total"], "lines, corpus kept", r["coverage"]["kept"])
    print("undetected body-only error fraction by weight (22-char body):", {w: f"{v:.5f}" for w, v in r["undetected"].items()}, "| 1/256 =", f"{1/256:.5f}")
    print("bursts <=8 bits missed:", r["burst_miss"])
    print("period-127 pair flips (real parser):", r["period_pairs"])
    print("whole-line real parser, accepted-with-wrong-content / tried:", r["whole_line"])
    fig, ax = plt.subplots(1, 2, figsize=(9.5, 3.5))
    props = ["crash", "noncanon", "out_of_range", "silent_corrupt"]
    x = np.arange(len(props)); w = 0.38
    ax[0].bar(x - w / 2, [max(r["stats"]["orig"][p], 0.5) for p in props], w, color=C["verm"], label="original sim/serial_proto.parse")
    ax[0].bar(x + w / 2, [max(r["stats"]["strict"][p], 0.5) for p in props], w, color=C["blue"], label="parse_strict (lab7)")
    ax[0].set_yscale("log"); ax[0].set_xticks(x); ax[0].set_xticklabels(["raises", "non-canonical\naccepted", "out-of-range\naccepted", "silent content\ncorruption"])
    ax[0].set_ylabel(f"violations in {r['n']} fuzz inputs (0 drawn at 0.5)"); ax[0].legend(); ax[0].set_title("property violations")
    ws = sorted(r["undetected"]); vals = [r["undetected"][k] for k in ws]
    ax[1].semilogy(ws, [max(v, 1e-6) for v in vals], "o-", color=C["blue"], label="body-only w-bit patterns")
    ax[1].axhline(1 / 256, color=C["grey"], ls="--", label="1/256")
    ax[1].set_xlabel("flipped bits w"); ax[1].set_ylabel("fraction undetected by CRC-8 (0 drawn at 1e-6)"); ax[1].legend(); ax[1].set_title("CRC-8 poly 0x07")
    save_fig(fig, "b12_fuzz.png"); save_json("b12_fuzz.json", r)
    o, s = r["stats"]["orig"], r["stats"]["strict"]
    key("B12", f"{r['n']} fuzz inputs: original parser accepted {o['noncanon']} non-canonical and {o['out_of_range']} out-of-range lines (strict parser: {s['noncanon']}/{s['out_of_range']}), crashes {o['crash']}; CRC-8: 0 missed bursts <=8 bits and 0 missed odd-weight errors, but {r['undetected'][2]*100:.2f}% of 2-bit body errors (127 bits apart, period of the polynomial) are CRC-invisible ({r['period_pairs']['accepted_wrong']}/{r['period_pairs']['tried']} gave an accepted line); weight-4 miss {r['undetected'][4]:.4f} vs 1/256={1/256:.4f}")
if __name__ == "__main__":
    main()
