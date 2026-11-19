"""Tamper-evident decision log: SHA-256 hash chain + Merkle root per block of 16 records, optional HMAC variant.

WHAT THIS PROVES (and what it does not)
- INTEGRITY: if one record of a finished log is edited, deleted, inserted or reordered, `verify` flags the record index
  where the chain first breaks (tests below check every single position). The Merkle root per block of 16 records gives a
  second, block-level check and allows short inclusion proofs for one record.
- NOT AUTHENTICITY: in the plain 'sha256' mode anybody can recompute the whole chain after editing (nothing is secret), and
  the verifier will then say OK. Detecting that needs either (a) the head hash / record count anchored somewhere the attacker
  cannot change (printed, mailed, stored on the other board), or (b) the 'hmac-sha256' mode, where every chain hash and block
  hash is an HMAC under a key the attacker does not hold. HMAC gives authenticity only towards holders of the same key
  (symmetric): it cannot prove to a third party WHO wrote the log; a signature scheme (e.g. Ed25519) would be needed for that
  and is not implemented here (no extra libraries allowed).
- Truncation at the END of the log (dropping the newest records) is invisible to a chain on its own; only an anchored head hash
  or count catches it (`verify(..., head=..., count=...)`).
- This is a software model; no timestamps are trusted (they are just data in the records).

File format (JSON lines): header line {"t":"hdr",...}; record lines {"t":"rec","i":idx,"rec":{...},"prev":hex,"hash":hex};
block lines {"t":"blk","b":n,"first":i0,"last":i1,"root":hex,"prev":hex,"hash":hex} written after every 16 records (and on close for a
partial last block).
  record hash  = H(prev_hash_hex | canonical_json({"i":idx,"rec":rec}))   H = SHA-256, or HMAC-SHA256(key, .) in hmac mode
  merkle leaf  = SHA256(0x00 | record_hash_bytes), node = SHA256(0x01 | left | right); an odd last node is promoted unchanged
  block hash   = H("blk" | prev_block_hash | root | first | last)
"""
import os, sys, json, hashlib, hmac

BLOCK = 16
GENESIS = "00" * 32


def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _h(mode, key, data: bytes) -> str:
    if mode == "hmac-sha256": return hmac.new(key, data, hashlib.sha256).hexdigest()
    return hashlib.sha256(data).hexdigest()


def rec_hash(mode, key, prev_hex, idx, rec):
    return _h(mode, key, prev_hex.encode() + b"|" + canon({"i": idx, "rec": rec}))


def merkle_root(hashes_hex):
    level = [hashlib.sha256(b"\x00" + bytes.fromhex(h)).digest() for h in hashes_hex]
    if not level: return hashlib.sha256(b"").hexdigest()
    while len(level) > 1:
        nxt = [hashlib.sha256(b"\x01" + level[i] + level[i + 1]).digest() for i in range(0, len(level) - 1, 2)]
        if len(level) % 2: nxt.append(level[-1])
        level = nxt
    return level[0].hex()


def merkle_proof(hashes_hex, k):
    """Inclusion proof for leaf k: list of (side, sibling_hex); side 'L' = sibling is on the left."""
    level = [hashlib.sha256(b"\x00" + bytes.fromhex(h)).digest() for h in hashes_hex]; proof = []
    while len(level) > 1:
        if k % 2 == 1: proof.append(("L", level[k - 1].hex()))
        elif k + 1 < len(level): proof.append(("R", level[k + 1].hex()))
        nxt = [hashlib.sha256(b"\x01" + level[i] + level[i + 1]).digest() for i in range(0, len(level) - 1, 2)]
        if len(level) % 2: nxt.append(level[-1])
        level, k = nxt, k // 2
    return proof


def merkle_verify(rec_hash_hex, proof, root_hex):
    cur = hashlib.sha256(b"\x00" + bytes.fromhex(rec_hash_hex)).digest()
    for side, sib in proof:
        s = bytes.fromhex(sib); cur = hashlib.sha256(b"\x01" + (s + cur if side == "L" else cur + s)).digest()
    return cur.hex() == root_hex


def build_lines(records, mode="sha256", key=None, block=BLOCK):
    """records: list of dicts. Returns list of JSON-able dicts (header, records, block seals)."""
    if mode == "hmac-sha256" and not key: raise ValueError("hmac mode needs a key")
    lines = [{"t": "hdr", "v": 1, "mode": mode, "block": block, "genesis": GENESIS}]
    prev = GENESIS; pending = []; prev_blk = GENESIS; b = 0
    def seal():
        nonlocal prev_blk, b, pending
        if not pending: return
        first, last = pending[0][0], pending[-1][0]; root = merkle_root([h for _, h in pending])
        bh = _h(mode, key, b"blk|" + prev_blk.encode() + b"|" + root.encode() + b"|" + f"{first}|{last}".encode())
        lines.append({"t": "blk", "b": b, "first": first, "last": last, "root": root, "prev": prev_blk, "hash": bh}); prev_blk = bh; b += 1; pending = []
    for i, rec in enumerate(records):
        h = rec_hash(mode, key, prev, i, rec); lines.append({"t": "rec", "i": i, "rec": rec, "prev": prev, "hash": h}); prev = h; pending.append((i, h))
        if len(pending) == block: seal()
    seal()
    return lines


def write_log(path, records, mode="sha256", key=None, block=BLOCK):
    lines = build_lines(records, mode, key, block)
    with open(path, "w") as f:
        for l in lines: f.write(json.dumps(l, sort_keys=True) + "\n")
    return lines


def read_lines(path):
    out = []
    with open(path) as f:
        for n, line in enumerate(f):
            if line.strip(): out.append(json.loads(line))
    return out


def verify(lines, key=None, head=None, count=None):
    """Verify a list of parsed lines. Returns dict(ok, first_bad, problems=[(record_index_or_None, text)], n_records, n_blocks, head).
    'first_bad' is the INDEX THE VERIFIER EXPECTED where it first saw a problem (the index of the edited/missing/inserted/misplaced record)."""
    probs = []; hdr = lines[0] if lines and lines[0].get("t") == "hdr" else None
    if hdr is None: return dict(ok=False, first_bad=None, problems=[(None, "missing header")], n_records=0, n_blocks=0, head=None)
    mode = hdr["mode"]; block = hdr["block"]
    if mode == "hmac-sha256" and not key: return dict(ok=False, first_bad=None, problems=[(None, "log is hmac-sha256 but no key was given")], n_records=0, n_blocks=0, head=None)
    exp = 0; prev = hdr["genesis"]; seen = []; prev_blk = hdr["genesis"]; nb = 0; nrec = 0; pending = []
    def bad(i, txt): probs.append((i, txt))
    for ln in lines[1:]:
        t = ln.get("t")
        if t == "rec":
            nrec += 1; i = ln.get("i")
            if i != exp: bad(exp, f"expected record {exp} here but found index {i} (deleted, inserted or reordered)")
            if ln.get("prev") != prev: bad(exp, f"record at position {exp}: prev-hash does not match the chain")
            h = rec_hash(mode, key, prev, i if isinstance(i, int) else -1, ln.get("rec"))
            if h != ln.get("hash"): bad(exp, f"record at position {exp}: stored hash != recomputed hash (content edited or key wrong)")
            prev = ln.get("hash") if isinstance(ln.get("hash"), str) else h      # continue from the stored value: one local fault does not cascade
            pending.append(h); seen.append(h); exp += 1
        elif t == "blk":
            first, last = ln.get("first"), ln.get("last")
            n_here = len(pending); bfirst = exp - n_here; blast = exp - 1
            if (first, last) != (bfirst, blast):
                at = (min(blast, last) + 1) if isinstance(last, int) else bfirst      # first index that is missing or surplus
                bad(at, f"block {ln.get('b')} claims records {first}..{last} but {bfirst}..{blast} precede it (records missing or surplus)")
            root = merkle_root(pending)
            if root != ln.get("root"): bad(bfirst, f"block {ln.get('b')}: Merkle root mismatch (some record in {bfirst}..{blast} differs from what was sealed)")
            if ln.get("b") != nb: bad(bfirst, f"block number {ln.get('b')} expected {nb}")
            if ln.get("prev") != prev_blk: bad(bfirst, f"block {ln.get('b')}: prev-block hash mismatch")
            bh = _h(mode, key, b"blk|" + prev_blk.encode() + b"|" + str(ln.get("root")).encode() + b"|" + f"{first}|{last}".encode())
            if bh != ln.get("hash"): bad(bfirst, f"block {ln.get('b')}: block hash mismatch")
            prev_blk = ln.get("hash") if isinstance(ln.get("hash"), str) else bh; nb += 1; pending = []
        else: bad(exp, f"unknown line type {t!r} at position {exp}")
    if head is not None and prev != head: bad(exp - 1 if exp else None, "chain head differs from the anchored head hash (tail truncated, replaced or rewritten)")
    if count is not None and nrec != count: bad(min(nrec, count), f"record count {nrec} differs from anchored count {count}")
    first_bad = probs[0][0] if probs else None
    return dict(ok=not probs, first_bad=first_bad, problems=probs, n_records=nrec, n_blocks=nb, head=prev, unsealed=len(pending))


# ------------------------------------------------------------------ feeding it from the existing simulators
def sim_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim")


def decision_records(ladder_seed=1):
    """Decisions from sim/ladder.py (mode switches with reason text) and sim/safety.py Guard (allow/deny/token/kill)."""
    sys.path.insert(0, sim_path())
    import ladder, safety
    recs = []
    for seed in (ladder_seed, ladder_seed + 1, ladder_seed + 2):       # three simulated 10,000-slot ladder runs
        llog = []; ladder.run("LADDER", seed=seed, log=llog)
        for s in llog:
            slot = int(s.split()[1].rstrip(":")); recs.append({"src": "ladder", "run_seed": seed, "slot": slot, "text": s.split(": ", 1)[1]})
    key = b"owner-key"; g = safety.Guard(key, allowed_channels={3, 4}); g.accept_token(0.0, 1, b"12345678")
    g.accept_token(0.1, *safety.Guard.make_token(key, 1)); g.request(0.2, 3, 0); g.request(0.3, 7, 0); g.request(0.4, 3, 2)
    for i in range(15): g.request(0.5 + 0.1 * i, 3, 0)
    g.accept_token(2.5, *safety.Guard.make_token(key, 1)); g.accept_token(2.6, *safety.Guard.make_token(key, 2))
    for i in range(30): g.request(2.7 + 0.3 * i, 3 if i % 5 else 4, 0 if i % 7 else 2)
    g.kill(12.0); g.request(12.1, 3, 0)
    for t, kind, detail in g.log: recs.append({"src": "guard", "t": round(float(t), 3), "event": kind, "detail": detail})
    return recs


# ------------------------------------------------------------------ attack experiments
def tamper(lines, kind, i):
    """Return a modified copy of lines where record i is edited / deleted / inserted before / swapped with i+1, WITHOUT recomputing hashes."""
    L = json.loads(json.dumps(lines)); pos = [k for k, l in enumerate(L) if l.get("t") == "rec"]
    p = pos[i]
    if kind == "edit":
        r = L[p]["rec"]; key = sorted(r)[0]; r[key] = "tampered" if r[key] != "tampered" else "x"
    elif kind == "delete": del L[p]
    elif kind == "insert": L.insert(p, {"t": "rec", "i": i, "rec": {"src": "forged", "text": "inserted"}, "prev": L[p]["prev"], "hash": "ab" * 32})
    elif kind == "reorder": L[p], L[pos[i + 1]] = L[pos[i + 1]], L[p]
    return L


def rewrite_from(lines, i, mode, key, newrec):
    """Strong attacker: edits record i and recomputes every later chain hash and block hash (all that is possible without a key in plain mode)."""
    recs = [l["rec"] for l in lines if l["t"] == "rec"]; recs[i] = newrec
    return build_lines(recs, mode, key if mode == "hmac-sha256" else None, lines[0]["block"])


def main():
    here = os.path.dirname(os.path.abspath(__file__)); recs = decision_records()
    print(f"decisions collected: {len(recs)} records ({sum(r['src']=='ladder' for r in recs)} from sim/ladder.py, {sum(r['src']=='guard' for r in recs)} from sim/safety.py Guard)")
    lines = write_log(os.path.join(here, "sample_log.jsonl"), recs)
    key = b"demo-key-NOT-SECRET"; lines_h = write_log(os.path.join(here, "sample_log_hmac.jsonl"), recs, "hmac-sha256", key)
    r = verify(lines); rh = verify(lines_h, key=key)
    print(f"sample_log.jsonl: ok={r['ok']} records={r['n_records']} blocks={r['n_blocks']} head={r['head'][:16]}...")
    print(f"sample_log_hmac.jsonl (demo key {key.decode()}): ok={rh['ok']} ; wrong key -> ok={verify(lines_h, key=b'wrong')['ok']}")
    n = r["n_records"]; print(f"\n== single-record tamper, every position, no recomputation by the attacker (N={n}) ==")
    print(f"{'attack':8s} {'positions':>9s} {'detected':>9s} {'flagged==i':>10s}  example(first problem for i=20)")
    summary = {}
    for kind in ("edit", "delete", "insert", "reorder"):
        rng = range(n - 1) if kind == "reorder" else range(n); det = exact = 0
        for i in rng:
            v = verify(tamper(lines, kind, i)); det += not v["ok"]; exact += (not v["ok"] and v["first_bad"] == i)
        summary[kind] = (len(rng), det, exact); ex = verify(tamper(lines, kind, 20))["problems"][0]
        print(f"{kind:8s} {len(rng):9d} {det:9d} {exact:10d}  {ex[1][:90]}")
    print("\n== limits ==")
    v = verify(lines[:-3]); print(f"tail truncation (drop last block seal + last 2 records) without anchor: ok={v['ok']} ; with anchored head: ok={verify(lines[:-3], head=r['head'])['ok']}")
    cut = [l for l in lines if not (l.get('t') == 'rec' and l['i'] >= n - 3)]
    print(f"drop last 3 records (and keep block seal): ok={verify(cut)['ok']} first_bad={verify(cut)['first_bad']}")
    cb = 32; cut2 = [l for l in lines if not (l.get('t') == 'rec' and l['i'] >= cb or l.get('t') == 'blk' and l['b'] >= cb // 16)]
    print(f"clean truncation at a block boundary (records >={cb} and their seals removed): plain ok={verify(cut2)['ok']} ; with anchored count={n}: ok={verify(cut2, count=n)['ok']} ; with anchored head: ok={verify(cut2, head=r['head'])['ok']}")
    newrec = {"src": "guard", "t": 9.9, "event": "allow", "detail": "forged"}
    rw = rewrite_from(lines, 20, "sha256", None, newrec)
    print(f"strong attacker rewrites record 20 and recomputes the whole chain: PLAIN verifier ok={verify(rw)['ok']} (integrity alone cannot catch it) ; with anchored head: ok={verify(rw, head=r['head'])['ok']}")
    rwh = rewrite_from(lines_h, 20, "hmac-sha256", b"attacker-guess", newrec)
    print(f"same attack against HMAC log, attacker lacks the key: verifier(key) ok={verify(rwh, key=key)['ok']} first_bad={verify(rwh, key=key)['first_bad']}")
    hs = [l["hash"] for l in lines if l["t"] == "rec"][:16]; root = merkle_root(hs); pf = merkle_proof(hs, 5)
    print(f"Merkle inclusion proof for record 5 of block 0: {len(pf)} hashes ({32*len(pf)} bytes), verifies={merkle_verify(hs[5], pf, root)}; against wrong record verifies={merkle_verify(hs[6], pf, root)}")
    import time; big = [{"src": "x", "i": i, "v": i * 7 % 13} for i in range(20000)]; t0 = time.time(); bl = build_lines(big); t1 = time.time(); verify(bl); t2 = time.time()
    print(f"speed: 20000 records written in {t1-t0:.2f} s, verified in {t2-t1:.2f} s")


if __name__ == "__main__":
    main()
