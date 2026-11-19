"""Generate test vectors for the RTL testbenches into vectors/ (deterministic). Run from anywhere."""
import os, sys, hashlib
sys.path.insert(0, os.path.dirname(__file__))
from hop_model import *
V = os.path.join(os.path.dirname(__file__), "..", "vectors"); os.makedirs(V, exist_ok=True)
NDIG = 1000
def key_from(tag): return int.from_bytes(hashlib.sha256(tag.encode()).digest()[:16], "little")
KEYS = [int.from_bytes(bytes(range(16)), "little"), key_from("fhss-link-key-2"), key_from("fhss-link-key-3")]
STARTS = [0, 0x00ABCDEF12345600, (1 << 56) - 10000]      # third run crosses the 2^56 slot-counter wrap

CONFIGS = {   # tag: (M, RW, NCH, nkeys, nslots)
    "m13":      (13, 32, 2, 3, 20000),   # default configuration
    "m13_rw8":  (13, 8, 1, 1, 20000),    # forces retries (reject prob 9/256 per digest)
    "m13_rw8n4": (13, 8, 4, 1, 20000),   # forces the chunk-shift (second..fourth attempt) path
    "m37":      (37, 32, 2, 1, 3000),
    "m16":      (16, 32, 2, 1, 3000),    # power of two
}
if __name__ == "__main__":
    selftest()
    for tag, (M, RW, NCH, nk, ns) in CONFIGS.items():
        cv, dg, ks, ss = [], [], [], []
        nret = 0
        for k in range(nk):
            ks.append("%032x" % KEYS[k]); ss.append("%014x" % STARTS[k])
            for i in range(ns):
                c, r, d = hop(KEYS[k], (STARTS[k] + i) & ((1 << 56) - 1), M, RW, NCH)
                cv.append("%02x%02x" % (r, c)); nret += (r > 0)
                if i < NDIG: dg.append("%016x" % d)
        for name, rows in (("vec_", cv), ("dig_", dg), ("keys_", ks), ("starts_", ss)):
            open(f"{V}/{name}{tag}.mem", "w").write("\n".join(rows) + "\n")
        print(f"{tag}: M={M} RW={RW} NCH={NCH} keys={nk} slots/key={ns} hops_with_retry={nret}")
    # LFSR vectors
    seeds = [0xACE1, 0x1234, 0x0000, 0xFFFF]
    rows = []
    for s in seeds: rows += ["%02x" % c for c in lfsr_schedule(20000, 13, s)]
    open(f"{V}/vec_lfsr.mem", "w").write("\n".join(rows) + "\n")
    open(f"{V}/seeds_lfsr.mem", "w").write("\n".join("%04x" % s for s in seeds) + "\n")
    print("lfsr: seeds", [hex(s) for s in seeds], "x 20000")
