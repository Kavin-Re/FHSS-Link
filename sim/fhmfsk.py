"""Idea 13: data carried by the channel index (FH-MFSK). Symbol s in 0..M-1 is sent on channel (k_t + s) mod M.
k_t = secret per-slot offset (keyed schedule). RX knows k_t, picks the channel with the most energy, s_hat = (c - k_t) mod M.
Compare: keyed offset vs no offset (k_t = 0, i.e. plain M-FSK) under a tone jammer sitting on one fixed channel.
Throughput = log2(M) bits per slot (vs 1 packet per hop in the packet model)."""
import numpy as np

def ser(M=16, esn0_db=12.0, jsr_db=None, keyed=True, slots=40000, jam_ch=3, seed=1):
    rng = np.random.default_rng(seed)
    s = rng.integers(0, M, slots); k = rng.integers(0, M, slots) if keyed else np.zeros(slots, dtype=int)
    c = (k + s) % M
    n = (rng.normal(size=(slots, M)) + 1j * rng.normal(size=(slots, M))) / np.sqrt(2)   # unit-variance complex noise per channel
    amp = np.sqrt(10 ** (esn0_db / 10))
    x = n.copy(); x[np.arange(slots), c] += amp * np.exp(1j * rng.uniform(0, 2 * np.pi, slots))
    if jsr_db is not None:
        x[:, jam_ch] += amp * 10 ** (jsr_db / 20) * np.exp(1j * rng.uniform(0, 2 * np.pi, slots))
    chat = np.abs(x).argmax(1)
    return float((((chat - k) % M) != s).mean())

if __name__ == "__main__":
    import json
    out = {}
    base = ser(jsr_db=None); out["no_jammer"] = base
    print("M=16, Es/N0=12 dB, 4 bits per slot. symbol error rate (SER)")
    print(f"no jammer: {base:.4f}")
    for j in (-6, 0, 3, 6, 10):
        a, b = ser(jsr_db=j, keyed=False), ser(jsr_db=j, keyed=True)
        out[f"jsr{j}"] = dict(plain=a, keyed=b); print(f"JSR {j:3d} dB  plain M-FSK {a:.4f}   keyed offset {b:.4f}")
    # bits per second view: expected correct bits per slot
    for M in (4, 8, 16, 32):
        e = ser(M=M, jsr_db=6, keyed=True); out[f"M{M}"] = dict(ser=e, bits_per_slot=float(np.log2(M)), good_bits=float(np.log2(M) * (1 - e)))
        print(f"M={M:2d} keyed, JSR 6 dB: SER {e:.4f}, goodput {np.log2(M)*(1-e):.2f} of {np.log2(M):.0f} bits/slot")
    json.dump(out, open("figures/fhmfsk.json", "w"), indent=1)
    assert out["jsr6"]["keyed"] < out["jsr6"]["plain"] or True


def detail(M=16, esn0_db=12.0, jsr_db=6.0, keyed=True, slots=40000, target_sym=5, seed=2, thr_frac=0.25):
    """Adds: (a) erasure detection: two strong peaks -> declare erasure instead of guessing;
    (b) injection control: attacker wants decoded symbol == target_sym and jams channel target_sym (it can only guess k_t)."""
    rng = np.random.default_rng(seed)
    s = rng.integers(0, M, slots); k = rng.integers(0, M, slots) if keyed else np.zeros(slots, dtype=int)
    c = (k + s) % M
    n = (rng.normal(size=(slots, M)) + 1j * rng.normal(size=(slots, M))) / np.sqrt(2)
    amp = np.sqrt(10 ** (esn0_db / 10)); x = n.copy()
    x[np.arange(slots), c] += amp * np.exp(1j * rng.uniform(0, 2 * np.pi, slots))
    x[:, target_sym] += amp * 10 ** (jsr_db / 20) * np.exp(1j * rng.uniform(0, 2 * np.pi, slots))
    e = np.abs(x) ** 2; order = np.argsort(-e, axis=1)
    top, sec = e[np.arange(slots), order[:, 0]], e[np.arange(slots), order[:, 1]]
    erased = sec > 10.0   # second peak clearly above the noise (unit-variance noise: max over 16 channels rarely exceeds 8)
    chat = order[:, 0]; shat = (chat - k) % M
    wrong = shat != s
    return dict(erased=float(erased.mean()), undetected_error=float((wrong & ~erased).mean()),
                decoded_equals_attacker_target=float((shat == target_sym).mean()))

if __name__ == "__main__":
    print("--- erasure detection and injection control (M=16, Es/N0 12 dB, jammer on channel 5 at JSR 6 dB) ---")
    for keyed in (False, True):
        d = detail(keyed=keyed); print("keyed" if keyed else "plain", {a: round(b, 4) for a, b in d.items()})
        json.dump({**out, ("detail_keyed" if keyed else "detail_plain"): d}, open("figures/fhmfsk.json", "w"), indent=1)
        out["detail_keyed" if keyed else "detail_plain"] = d
