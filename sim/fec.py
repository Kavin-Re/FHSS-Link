"""Forward error correction for the hopping link.
1. Hamming(7,4): corrects 1 bit error per 7-bit block (+ block interleaver so burst errors on a hop become single errors).
2. Convolutional code K=3 rate 1/2 (generators 7,5 octal) with hard-decision Viterbi.
3. Systematic (n,k) erasure code over GF(256) (Cauchy matrix, MDS): any k of n packets rebuild the data.
   This is the right tool for hop-level loss: a jammed hop is an erasure, not a bit error."""
import numpy as np

# ---------- Hamming(7,4) ----------
G = np.array([[1,0,0,0,1,1,0],[0,1,0,0,1,0,1],[0,0,1,0,0,1,1],[0,0,0,1,1,1,1]], dtype=np.uint8)
Hm = np.array([[1,1,0,1,1,0,0],[1,0,1,1,0,1,0],[0,1,1,1,0,0,1]], dtype=np.uint8)

def ham_encode(bits):
    b = np.asarray(bits, dtype=np.uint8); b = np.pad(b, (0, (-len(b)) % 4)).reshape(-1, 4)
    return (b @ G % 2).astype(np.uint8).ravel()

def ham_decode(code):
    c = np.asarray(code, dtype=np.uint8).reshape(-1, 7).copy()
    syn = c @ Hm.T % 2
    for i, s in enumerate(syn):
        if s.any():
            for pos in range(7):
                if (Hm[:, pos] == s).all():
                    c[i, pos] ^= 1; break
    return c[:, :4].ravel()

def interleave(bits, depth):
    b = np.asarray(bits); b = np.pad(b, (0, (-len(b)) % depth)); return b.reshape(-1, depth).T.ravel()

def deinterleave(bits, depth, n):
    b = np.asarray(bits).reshape(depth, -1).T.ravel(); return b[:n]

# ---------- convolutional K=3, rate 1/2, (7,5) ----------
def conv_encode(bits):
    s, out = 0, []
    for b in list(bits) + [0, 0]:           # flush
        s = ((s << 1) | int(b)) & 7
        out += [bin(s & 7).count("1") & 1, bin(s & 5).count("1") & 1]
    return np.array(out, dtype=np.uint8)

def viterbi_decode(code):
    code = np.asarray(code, dtype=np.uint8).reshape(-1, 2)
    INF = 10**9; pm = {0: 0}; paths = {0: []}
    for sym in code:
        npm, npaths = {}, {}
        for st, m in pm.items():
            for b in (0, 1):
                s = ((st << 1) | b) & 7
                exp = (bin(s & 7).count("1") & 1, bin(s & 5).count("1") & 1)
                d = m + (exp[0] != sym[0]) + (exp[1] != sym[1]); ns = s & 3
                if d < npm.get(ns, INF):
                    npm[ns] = d; npaths[ns] = paths[st] + [b]
        pm, paths = npm, npaths
    best = min(pm, key=pm.get)
    return np.array(paths[best][:-2], dtype=np.uint8)

# ---------- GF(256) erasure code ----------
EXP, LOG = [0] * 512, [0] * 256
_x = 1
for _i in range(255):
    EXP[_i] = _x; LOG[_x] = _i; _x <<= 1
    if _x & 0x100: _x ^= 0x11D
for _i in range(255, 512): EXP[_i] = EXP[_i - 255]
def gmul(a, b): return 0 if a == 0 or b == 0 else EXP[LOG[a] + LOG[b]]
def ginv(a): return EXP[255 - LOG[a]]

def _cauchy(n, k):  # parity rows: element (j,i) = 1/(x_j ^ y_i), x_j = k+j, y_i = i (all distinct)
    return [[ginv((k + j) ^ i) for i in range(k)] for j in range(n - k)]

def erasure_encode(data, n):
    """data: list of k equal-length byte arrays -> list of n packets (first k are the data itself)."""
    k = len(data); L = len(data[0]); C = _cauchy(n, k)
    out = [np.array(d, dtype=np.uint8) for d in data]
    for row in C:
        p = np.zeros(L, dtype=np.uint8)
        for i, c in enumerate(row):
            p ^= np.array([gmul(c, int(v)) for v in data[i]], dtype=np.uint8)
        out.append(p)
    return out

def erasure_decode(received, n, k):
    """received: dict {packet_index: bytes}; needs >= k entries. Returns the k data packets or None."""
    if len(received) < k: return None
    idx = sorted(received)[:k]; C = _cauchy(n, k)
    rows = []
    for j in idx:  # generator-matrix row for packet j
        rows.append([1 if i == j else 0 for i in range(k)] if j < k else C[j - k])
    L = len(received[idx[0]]); A = [r[:] + [0] for r in rows]
    out = [[0] * L for _ in range(k)]
    for pos in range(L):  # solve A x = y per byte position (small k, so plain Gauss-Jordan is fine)
        M = [rows[r][:] + [int(received[idx[r]][pos])] for r in range(k)]
        for c in range(k):
            p = next(r for r in range(c, k) if M[r][c])
            M[c], M[p] = M[p], M[c]
            iv = ginv(M[c][c]); M[c] = [gmul(iv, v) for v in M[c]]
            for r in range(k):
                if r != c and M[r][c]:
                    f = M[r][c]; M[r] = [v ^ gmul(f, w) for v, w in zip(M[r], M[c])]
        for i in range(k): out[i][pos] = M[i][k]
    return [np.array(o, dtype=np.uint8) for o in out]
