"""Idea 14: key from the air (physical-layer key generation).
Alice and Bob measure the same reciprocal fading value h on a channel, each with independent noise. Eve, away from both, sees an
independent fade (spatial decorrelation beyond about half a wavelength: 6 cm at 2.4 GHz).
Pipeline: guard-band quantiser -> publicly agreed index list -> Hamming(7,4) syndrome reconciliation -> 16-bit hash check per 112-bit
segment -> SHA-256 privacy amplification into a 128-bit key. Public discussion = indices, syndromes, hashes (Eve is assumed to hear all)."""
import numpy as np, hashlib
from fec import Hm

def quantise(a, b, alpha=0.4):
    sa, sb = a.std(), b.std(); ma, mb = a.mean(), b.mean()
    ka = np.abs(a - ma) > alpha * sa; kb = np.abs(b - mb) > alpha * sb
    keep = ka & kb                       # indices both sides agree to keep (public)
    return keep, (a[keep] > ma).astype(np.uint8), (b[keep] > mb).astype(np.uint8)

def reconcile(abits, bbits):
    """Blocks of 7: Alice reveals the 3-bit syndrome, Bob corrects one error. Then a 112-bit segment hash check (16 bits revealed)."""
    n = len(abits) // 7 * 7; A = abits[:n].reshape(-1, 7); B = bbits[:n].reshape(-1, 7).copy(); leaked = 0
    for i in range(len(A)):
        sA = A[i] @ Hm.T % 2; sB = B[i] @ Hm.T % 2; syn = sA ^ sB; leaked += 3
        if syn.any():
            for p in range(7):
                if (Hm[:, p] == syn).all(): B[i, p] ^= 1; break
    seg = 16; keysegs = []; agree_ok = 0
    for s in range(0, len(A) - seg + 1, seg):
        ha = hashlib.sha256(A[s:s + seg].tobytes()).digest()[:2]; hb = hashlib.sha256(B[s:s + seg].tobytes()).digest()[:2]; leaked += 16
        if ha == hb: keysegs.append(A[s:s + seg].ravel()); agree_ok += 1
    return keysegs, leaked, len(A) // seg

def key_from(keysegs, leaked_bits_total):
    bits = np.concatenate(keysegs) if keysegs else np.array([], dtype=np.uint8)
    return bits, hashlib.sha256(np.packbits(bits).tobytes()).digest()[:16] if len(bits) else None

def trial(snr_db, N=3000, seed=0, eve_rho=0.0):
    rng = np.random.default_rng(seed); h = rng.normal(size=N); sn = 10 ** (-snr_db / 20)
    a = h + sn * rng.normal(size=N); b = h + sn * rng.normal(size=N)
    he = eve_rho * h + np.sqrt(1 - eve_rho ** 2) * rng.normal(size=N); e = he + sn * rng.normal(size=N)
    keep, qa, qb = quantise(a, b); qe = (e[keep] > e.mean()).astype(np.uint8)
    raw_bdr = float((qa != qb).mean()); eve_bdr = float((qa != qe).mean())
    segs, leaked, nseg = reconcile(qa, qb)
    bits, key = key_from(segs, leaked)
    # Eve tries the same decoding with her own bits and no syndrome help beyond public info: compare agreement on kept segments
    eve_agree = float((qa[:len(bits)] == qe[:len(bits)]).mean()) if len(bits) else float("nan")
    return dict(kept=int(keep.sum()), raw_bdr=raw_bdr, segments=nseg, good_segments=len(segs), key_bits_before_pa=int(len(bits)),
                key_bits_after_leak=int(max(0, len(bits) - leaked * len(bits) / max(1, (len(qa) // 7 * 7)))), eve_agreement=eve_agree)

if __name__ == "__main__":
    import json; res = {}
    print("SNR dB | kept | raw bit disagreement | segments ok/total | key bits (pre-PA) | Eve's agreement on those bits")
    for snr in (5, 10, 15, 20, 25):
        ts = [trial(snr, seed=s) for s in range(20)]
        m = {k: float(np.nanmean([t[k] for t in ts])) for k in ts[0]}; res[str(snr)] = m
        print(f"{snr:6d} | {m['kept']:5.0f} | {m['raw_bdr']:.3f} | {m['good_segments']:.1f}/{m['segments']:.1f} | {m['key_bits_before_pa']:6.0f} | {m['eve_agreement']:.3f}")
    json.dump(res, open("figures/plkg.json", "w"), indent=1)
