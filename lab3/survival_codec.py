"""Survival-mode telemetry codec: a status message in as few bytes as possible.

MODEL / ASSUMPTIONS (everything below is simulated, no real GPS or radio data)
- Position lives in a 10 km x 10 km box (origin lat0/lon0 below); it is carried as metres (x east, y north) and
  converted to lat/lon with a flat-earth approximation (fine inside 10 km). Resolution is `ps` metres (1 m default).
- Fields: x, y, battery 0-100 %, 4 status flags, heading 0-359 deg, speed 0-32 m/s, stop flag, sequence number.
- Message = KEYFRAME (all fields absolute, fixed width) or DELTA (each field coded as difference against the decoder's
  previous reconstructed state, with a per-field canonical Huffman code built from simulated patrol trajectories).
  Optional dead-reckoning predictor: position delta is taken against previous position + previous delta.
- Quantisation is on a grid, so the encoder's delta equals the decoder's delta: no drift builds up (closed loop).
- A delta that falls outside the Huffman alphabet forces a keyframe instead of an escape code.
- Every message ends with CRC-8 (poly 0x07, same as sim/serial_proto.py) over the payload bits zero-padded to a byte;
  the whole message is then padded to a byte boundary. Message length is assumed to be given by the lower framing layer.
- Sequence number is 4 bits (mod 16): a gap of 1..15 lost messages is detectable, 16 consecutive losses are not.
- Trajectories: random-waypoint patrol, mostly walking (~1.4 m/s) with some vehicle legs, pauses at waypoints, GPS jitter
  0.7 m sigma, 1 message per second. A different patrol style would give different Huffman tables and different bytes.
Run: python3 survival_codec.py
"""
import os, sys, math, heapq, json
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
from serial_proto import crc8

LAT0, LON0, BOX = 23.0, 72.5, 10000.0   # arbitrary box origin (degrees) and side (m)
M_PER_DEG_LAT = 111320.0


def xy_to_latlon(x, y):
    return LAT0 + y / M_PER_DEG_LAT, LON0 + x / (M_PER_DEG_LAT * math.cos(math.radians(LAT0)))


def latlon_to_xy(lat, lon):
    return (lon - LON0) * M_PER_DEG_LAT * math.cos(math.radians(LAT0)), (lat - LAT0) * M_PER_DEG_LAT


# ---------------------------------------------------------------- trajectories
def patrol(rng, n, dt=1.0, gps_sigma=0.7, vmax=32.0):
    """Random-waypoint patrol. Returns list of message dicts (true, un-quantised values)."""
    pos = rng.uniform(500, BOX - 500, 2); batt = rng.uniform(60, 100); flags = int(rng.integers(0, 16))
    heading = rng.uniform(0, 360); out = []; pause = 0; wp = None; speed_nom = 1.4; t = 0
    while len(out) < n:
        if pause > 0:
            pause -= 1; moving = False; v = 0.0
        else:
            if wp is None or np.hypot(*(wp - pos)) < 3:
                wp = np.clip(pos + rng.normal(0, 600, 2), 50, BOX - 50)
                speed_nom = float(rng.choice([1.4, 1.4, 1.4, 7.0], p=[.4, .3, .1, .2]) * rng.uniform(0.8, 1.2))
                if rng.random() < 0.3: pause = int(rng.integers(5, 25)); continue
            d = wp - pos; dist = np.hypot(*d); v = min(speed_nom + rng.normal(0, 0.15 * speed_nom), dist / dt, vmax - 1)
            v = max(v, 0.0); moving = True
            hd = (math.degrees(math.atan2(d[0], d[1])) + rng.normal(0, 3)) % 360   # compass: 0 = north, clockwise
            heading = hd; pos = pos + d / max(dist, 1e-9) * v * dt
        batt = min(100.0, max(0.0, batt - abs(rng.normal(0.03, 0.02)) + (rng.random() < 0.002) * 3))
        for b in range(4):
            if rng.random() < 0.002: flags ^= 1 << b
        meas = np.clip(pos + rng.normal(0, gps_sigma, 2), 0, BOX - 1e-6)
        out.append(dict(x=float(meas[0]), y=float(meas[1]), batt=float(batt), flags=flags, heading=float(heading), speed=float(v), stop=int(not moving)))
        t += 1
    for i, m in enumerate(out): m["seq"] = i
    return out


# ---------------------------------------------------------------- bits and Huffman
class BitW:
    def __init__(self): self.b = []
    def put(self, v, n): self.b.extend((v >> (n - 1 - i)) & 1 for i in range(n))
    def bits(self): return len(self.b)
    def bytes_padded(self):
        b = self.b + [0] * (-len(self.b) % 8)
        return bytes(int("".join(map(str, b[i:i + 8])), 2) for i in range(0, len(b), 8))


class BitR:
    def __init__(self, data): self.b = [(c >> (7 - i)) & 1 for c in data for i in range(8)]; self.i = 0
    def get(self, n):
        if self.i + n > len(self.b): raise ValueError("short")
        v = 0
        for _ in range(n): v = (v << 1) | self.b[self.i]; self.i += 1
        return v


def canonical_huffman(counts):
    """counts: dict sym->count (all >0). Returns dict sym->(code, length) (canonical: sorted by length then symbol)."""
    syms = sorted(counts)
    if len(syms) == 1: return {syms[0]: (0, 1)}
    heap = [(c, i, [s]) for i, (s, c) in enumerate((s, counts[s]) for s in syms)]; heapq.heapify(heap); ln = {s: 0 for s in syms}; k = len(heap)
    while len(heap) > 1:
        c1, _, s1 = heapq.heappop(heap); c2, _, s2 = heapq.heappop(heap)
        for s in s1 + s2: ln[s] += 1
        heapq.heappush(heap, (c1 + c2, k, s1 + s2)); k += 1
    code, prev, table = 0, 0, {}
    for s in sorted(syms, key=lambda s: (ln[s], s)):
        code <<= (ln[s] - prev); prev = ln[s]; table[s] = (code, ln[s]); code += 1
    return table


class Huff:
    def __init__(self, counts):
        self.enc = canonical_huffman(counts); self.dec = {(l, c): s for s, (c, l) in self.enc.items()}; self.lo, self.hi = min(counts), max(counts)
    def put(self, w, s): c, l = self.enc[s]; w.put(c, l)
    def get(self, r):
        c = 0
        for l in range(1, 64):
            c = (c << 1) | r.get(1)
            if (l, c) in self.dec: return self.dec[(l, c)]
        raise ValueError("bad code")
    def has(self, s): return s in self.enc


# ---------------------------------------------------------------- codec
FIELDS = ("dx", "dy", "dh", "dv", "db")


class Codec:
    """ps: position step (m), hs: heading step (deg), vs: speed step (m/s), bs: battery step (%)."""
    def __init__(self, ps=1.0, hs=5.0, vs=0.5, bs=1.0, predict=False, keyint=20):
        self.ps, self.hs, self.vs, self.bs, self.predict, self.keyint = ps, hs, vs, bs, predict, keyint
        self.npos = math.ceil(BOX / ps); self.nh = round(360 / hs); self.nv = math.ceil(32 / vs); self.nb = round(100 / bs) + 1
        self.pb = max(1, math.ceil(math.log2(self.npos))); self.hb = math.ceil(math.log2(self.nh)); self.vb = math.ceil(math.log2(self.nv)); self.bb = math.ceil(math.log2(self.nb))
        self.tables = None

    # quantise a true message to grid indices
    def quant(self, m):
        return dict(x=min(self.npos - 1, max(0, round(m["x"] / self.ps))), y=min(self.npos - 1, max(0, round(m["y"] / self.ps))),
                    h=round(m["heading"] / self.hs) % self.nh, v=min(self.nv - 1, round(m["speed"] / self.vs)),
                    b=min(self.nb - 1, round(m["batt"] / self.bs)), f=m["flags"], s=m["stop"])

    def dequant(self, q):
        return dict(x=q["x"] * self.ps, y=q["y"] * self.ps, heading=q["h"] * self.hs, speed=q["v"] * self.vs, batt=q["b"] * self.bs, flags=q["f"], stop=q["s"])

    def wrap(self, d): return (d + self.nh // 2) % self.nh - self.nh // 2

    def deltas(self, q, prev, pd):
        """symbol dict for a delta message given previous reconstructed idx `prev` and previous position delta pd=(dx,dy)."""
        px = prev["x"] + (pd[0] if self.predict else 0); py = prev["y"] + (pd[1] if self.predict else 0)
        return dict(dx=q["x"] - px, dy=q["y"] - py, dh=self.wrap(q["h"] - prev["h"]), dv=q["v"] - prev["v"], db=q["b"] - prev["b"])

    # -- training the Huffman tables from trajectories (a list of lists of messages)
    def train(self, trajs, dxr=40, dvr=None):
        dvr = dvr or max(8, int(8 / self.vs)); ranges = dict(dx=dxr, dy=dxr, dh=self.nh // 2, dv=dvr, db=8)
        ranges["dx"] = ranges["dy"] = int(math.ceil(dxr / self.ps)) + 2
        cnt = {f: {s: 1 for s in range(-ranges[f], ranges[f] + (0 if f != "dh" else 0) + 1)} for f in FIELDS}   # +1 smoothing
        if True: cnt["dh"] = {s: 1 for s in range(-(self.nh // 2), self.nh - self.nh // 2)}
        for tr in trajs:
            prev = None; pd = (0, 0)
            for m in tr:
                q = self.quant(m)
                if prev is not None:
                    d = self.deltas(q, prev, pd)
                    for f in FIELDS:
                        if d[f] in cnt[f]: cnt[f][d[f]] += 1
                    pd = (q["x"] - prev["x"], q["y"] - prev["y"])
                prev = q
        self.tables = {f: Huff(cnt[f]) for f in FIELDS}
        return self

    # -- encode: returns bytes
    def encode_key(self, m, seq):
        q = self.quant(m); w = BitW(); w.put(1, 1); w.put(seq & 15, 4); w.put(q["x"], self.pb); w.put(q["y"], self.pb); w.put(q["b"], self.bb)
        w.put(q["f"], 4); w.put(q["h"], self.hb); w.put(q["v"], self.vb); w.put(q["s"], 1)
        return self._finish(w), q

    def encode_delta(self, m, seq, prev, pd):
        """returns (bytes, q) or None if a delta is out of alphabet (caller must send keyframe)."""
        q = self.quant(m); d = self.deltas(q, prev, pd)
        if not all(self.tables[f].has(d[f]) for f in FIELDS): return None
        w = BitW(); w.put(0, 1); w.put(seq & 15, 4)
        for f in FIELDS: self.tables[f].put(w, d[f])
        if q["f"] != prev["f"]: w.put(1, 1); w.put(q["f"], 4)
        else: w.put(0, 1)
        w.put(q["s"], 1)
        return self._finish(w), q

    @staticmethod
    def _finish(w):
        payload = w.bytes_padded(); n = w.bits()
        w2 = BitW(); w2.b = list(w.b); w2.put(crc8(payload), 8)
        return w2.bytes_padded()

    # -- decode: returns (kind, seq, q) ; raises ValueError on CRC failure / garbage.
    def decode(self, data, prev=None, pd=(0, 0)):
        r = BitR(data)
        kind = r.get(1); seq = r.get(4)
        if kind == 1:
            q = dict(x=r.get(self.pb), y=r.get(self.pb), b=r.get(self.bb), f=r.get(4), h=r.get(self.hb), v=r.get(self.vb), s=r.get(1))
        else:
            if prev is None: raise ValueError("delta without baseline")
            d = {f: self.tables[f].get(r) for f in FIELDS}
            f_ = r.get(4) if r.get(1) else prev["f"]; s = r.get(1)
            px = prev["x"] + (pd[0] if self.predict else 0); py = prev["y"] + (pd[1] if self.predict else 0)
            q = dict(x=px + d["dx"], y=py + d["dy"], h=(prev["h"] + d["dh"]) % self.nh, v=prev["v"] + d["dv"], b=prev["b"] + d["db"], f=f_, s=s)
        used = r.i; wb = BitW(); wb.b = list(r.b[:used]); crc = r.get(8)
        if crc != crc8(wb.bytes_padded()): raise ValueError("CRC fail")
        if not (0 <= q["x"] < self.npos and 0 <= q["y"] < self.npos and 0 <= q["v"] < self.nv and 0 <= q["b"] < self.nb): raise ValueError("range")
        return kind, seq, q


class Encoder:
    """Stateful encoder with periodic keyframes (every `keyint` messages, and on out-of-alphabet deltas)."""
    def __init__(self, codec): self.c = codec; self.prev = None; self.pd = (0, 0); self.n = 0; self.nkey = 0

    def send(self, m):
        seq = self.n; out = None
        if self.prev is not None and self.n % self.c.keyint != 0: out = self.c.encode_delta(m, seq, self.prev, self.pd)
        if out is None:
            out = self.c.encode_key(m, seq); self.nkey += 1; data, q = out; self.pd = (0, 0)
        else:
            data, q = out; self.pd = (q["x"] - self.prev["x"], q["y"] - self.prev["y"])
        self.prev = q; self.n += 1; return data


class Decoder:
    """strategy 'naive': apply every good-CRC delta even after a gap. 'gap': after a gap or CRC failure the state is
    marked STALE (output held at the last good state) until the next keyframe."""
    def __init__(self, codec, strategy="gap"): self.c, self.strategy = codec, strategy; self.q = None; self.pd = (0, 0); self.last_seq = None; self.stale = True

    def receive(self, data):
        """data=None means the message never arrived. Returns the decoder's current best state (idx dict) and stale flag."""
        if data is None:
            if self.strategy == "gap": self.stale = True
            return self.q, self.stale
        try: kind, seq, q = self.c.decode(data, self.q, self.pd)
        except ValueError:
            self.stale = True; return self.q, self.stale          # CRC fail counts as a loss
        gap = self.last_seq is not None and seq != (self.last_seq + 1) & 15
        self.last_seq = seq
        if kind == 1: self.pd = (0, 0); self.q = q; self.stale = False
        else:
            if gap and self.strategy == "gap": self.stale = True; return self.q, self.stale
            if self.stale and self.strategy == "gap": return self.q, self.stale
            if self.q is not None: self.pd = (q["x"] - self.q["x"], q["y"] - self.q["y"])
            self.q = q
        return self.q, self.stale


# ---------------------------------------------------------------- experiments
LEVELS = [  # (name, ps, hs, vs, bs): quality levels for the rate-distortion sweep
    ("q0 1m/1deg", 1, 1, 0.25, 1), ("q1 1m/5deg", 1, 5, 0.5, 1), ("q2 2m/5deg", 2, 5, 0.5, 2), ("q3 4m/10deg", 4, 10, 1, 2),
    ("q4 8m/10deg", 8, 10, 1, 5), ("q5 16m/20deg", 16, 20, 2, 5), ("q6 32m/45deg", 32, 45, 4, 10)]


def make_trajs(n, length, seed0):
    return [patrol(np.random.default_rng(seed0 + i), length) for i in range(n)]


def evaluate(codec, trajs, p_loss=0.0, strategy="gap", seed=0, thr=5.0):
    """Encode+decode trajs. Returns dict with bits, bytes, errors. Error compares decoder's held/current state to the TRUE message."""
    rng = np.random.default_rng(seed); nb = 0; nbytes = 0; msgs = 0; pe = []; he = []; ve = []; wrong = 0; stale = 0; keys = 0
    for tr in trajs:
        enc = Encoder(codec); dec = Decoder(codec, strategy)
        for m in tr:
            data = enc.send(m); nbytes += len(data); nb += len(data) * 8; msgs += 1
            got = None if rng.random() < p_loss else data
            q, st = dec.receive(got)
            if q is None: pe.append(BOX); wrong += 1; stale += 1; continue
            r = codec.dequant(q); e = math.hypot(r["x"] - m["x"], r["y"] - m["y"]); pe.append(e)
            he.append(abs((r["heading"] - m["heading"] + 180) % 360 - 180)); ve.append(abs(r["speed"] - m["speed"]))
            wrong += e > thr; stale += st
        keys += enc.nkey
    pe = np.array(pe)
    return dict(msgs=msgs, bytes_per_msg=nbytes / msgs, pos_rms=float(np.sqrt(np.mean(pe ** 2))), pos_mean=float(pe.mean()), pos_p95=float(np.percentile(pe, 95)),
                head_mean=float(np.mean(he)), speed_mean=float(np.mean(ve)), frac_wrong=wrong / msgs, frac_stale=stale / msgs, key_share=keys / msgs)


def main():
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    here = os.path.dirname(os.path.abspath(__file__)); train = make_trajs(30, 600, 1000); test = make_trajs(12, 600, 900000)
    print("patrol trajectories: 30 train x 600 msgs, 12 test x 600 msgs, 1 msg/s, keyframe every 20")
    c = Codec(1, 5, 0.5, 1).train(train); k = c.encode_key(test[0][0], 0)[0]
    print(f"keyframe at 1 m / 5 deg / 0.5 m/s / 1 % : {len(k)} bytes (1 type + 4 seq + {c.pb}+{c.pb} position + {c.bb} batt + 4 flags + {c.hb} heading + {c.vb} speed + 1 stop + 8 CRC = {1+4+2*c.pb+c.bb+4+c.hb+c.vb+1+8} bits, padded)")
    print("round trip check (no loss) ...", end=" ")
    r = evaluate(c, test[:3]); print(f"pos RMS {r['pos_rms']:.2f} m (true includes 0.7 m GPS jitter per axis; quantisation only), bytes/msg {r['bytes_per_msg']:.2f}")
    print("\n== rate-distortion (Huffman retrained per level, test trajectories, no loss, keyframe every 20) ==")
    print(f"{'level':14s} {'predict':7s} {'bytes/msg':>9s} {'posRMS m':>9s} {'pos p95':>8s} {'head deg':>8s} {'speed m/s':>9s}")
    rd = {}
    for pred in (False, True):
        pts = []
        for name, ps, hs, vs, bs in LEVELS:
            cc = Codec(ps, hs, vs, bs, predict=pred).train(train); r = evaluate(cc, test)
            pts.append((r["bytes_per_msg"], r["pos_rms"], name)); print(f"{name:14s} {str(pred):7s} {r['bytes_per_msg']:9.2f} {r['pos_rms']:9.2f} {r['pos_p95']:8.2f} {r['head_mean']:8.2f} {r['speed_mean']:9.2f}")
        rd[pred] = pts
    # all-keyframe baseline at 1 m
    ck = Codec(1, 5, 0.5, 1, keyint=1).train(train); rk = evaluate(ck, test)
    print(f"all-keyframe baseline at q1: {rk['bytes_per_msg']:.2f} bytes/msg ; Huffman-delta saves {100*(1-evaluate(Codec(1,5,0.5,1).train(train), test)['bytes_per_msg']/rk['bytes_per_msg']):.0f} %")
    # Huffman tables overview + entropy
    c1 = Codec(1, 5, 0.5, 1).train(train)
    print("code lengths (bits) of the most common symbol per field, q1:", {f: min(l for _, l in c1.tables[f].enc.values()) for f in FIELDS})
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    for pred, col in ((False, "#1f77b4"), (True, "#d62728")):
        ax.plot([p[0] for p in rd[pred]], [p[1] for p in rd[pred]], "o-", color=col, label="delta vs previous" if not pred else "delta vs dead-reckoning prediction")
    for b, e, n in rd[False]: ax.annotate(n.split()[0], (b, e), textcoords="offset points", xytext=(4, 4), fontsize=7)
    ax.axvline(rk["bytes_per_msg"], color="gray", ls="--", label="all keyframes @1 m"); ax.set_yscale("log")
    ax.set_xlabel("bytes per message (incl. CRC-8, byte padded, keyframe every 20)"); ax.set_ylabel("position RMS error vs true (m)"); ax.grid(alpha=.3, which="both"); ax.legend(fontsize=7)
    ax.set_title("Survival codec: rate-distortion (simulated patrols)"); fig.tight_layout(); fig.savefig(os.path.join(here, "figures", "survival_rd.png"), dpi=130); plt.close(fig)

    print("\n== lost messages: keyframe interval K vs loss rate (q1, no predictor), two decoder strategies ==")
    print(f"{'K':>3s} {'loss':>5s} {'strategy':8s} {'bytes/msg':>9s} {'meanErr m':>9s} {'frac>5m':>8s} {'frac stale':>10s}")
    res = {}
    for K in (1, 5, 10, 20, 50):
        cc = Codec(1, 5, 0.5, 1, keyint=K).train(train)
        for p in (0.0, 0.05, 0.2):
            for strat in ("naive", "gap"):
                r = evaluate(cc, test, p_loss=p, strategy=strat, seed=7); res[(K, p, strat)] = r
                print(f"{K:3d} {p:5.2f} {strat:8s} {r['bytes_per_msg']:9.2f} {r['pos_mean']:9.1f} {r['frac_wrong']:8.3f} {r['frac_stale']:10.3f}")
    fig, axs = plt.subplots(1, 2, figsize=(10, 4))
    for strat, ls in (("naive", "--"), ("gap", "-")):
        for p, col in ((0.05, "#1f77b4"), (0.2, "#d62728")):
            axs[0].plot([res[(K, p, strat)]["bytes_per_msg"] for K in (1, 5, 10, 20, 50)], [res[(K, p, strat)]["pos_mean"] for K in (1, 5, 10, 20, 50)], "o" + ls, color=col, label=f"{strat}, loss {p:.0%}")
            axs[1].plot((1, 5, 10, 20, 50), [res[(K, p, strat)]["frac_wrong"] for K in (1, 5, 10, 20, 50)], "o" + ls, color=col, label=f"{strat}, loss {p:.0%}")
    axs[0].set_xlabel("bytes per message"); axs[0].set_ylabel("mean position error (m)"); axs[0].set_yscale("log"); axs[0].legend(fontsize=7); axs[0].grid(alpha=.3, which="both")
    axs[1].set_xlabel("keyframe interval K (messages)"); axs[1].set_ylabel("fraction of messages with error > 5 m"); axs[1].set_xscale("log"); axs[1].grid(alpha=.3); axs[1].legend(fontsize=7)
    fig.suptitle("Effect of lost messages and keyframe interval"); fig.tight_layout(); fig.savefig(os.path.join(here, "figures", "survival_loss.png"), dpi=130); plt.close(fig)
    # CRC detection check: flip EVERY bit position (one at a time) of 60 messages, decode with the correct decoder state
    enc = Encoder(c); prev = None; pd = (0, 0); det = same = bad = n = 0
    for m in test[1][:60]:
        d = enc.send(m); kind, seq, q0 = c.decode(d, prev, pd)
        for bit in range(8 * len(d)):
            b = bytearray(d); b[bit // 8] ^= 1 << (7 - bit % 8); n += 1
            try:
                k2, s2, q2 = c.decode(bytes(b), prev, pd); eq = (q2 == q0 and s2 == seq and k2 == kind); same += eq; bad += not eq
            except ValueError: det += 1
        pd = (q0["x"] - prev["x"], q0["y"] - prev["y"]) if (kind == 0 and prev) else (0, 0); prev = q0
    print(f"\nsingle-bit corruption, all bit positions of 60 messages ({n} flips): {det} detected (CRC/format), {same} hit only unprotected pad bits (decoded identical), {bad} ACCEPTED WITH WRONG CONTENT "
          f"(a flip can change the variable-length parse so the CRC is read from the wrong place: ~1/256 chance of a false accept for such flips)")
    lat, lon = xy_to_latlon(1234.0, 5678.0); x, y = latlon_to_xy(lat, lon); print(f"lat/lon conversion round trip error {abs(x-1234)+abs(y-5678):.2e} m")



if __name__ == "__main__":
    main()
