"""Frequency hopping over sound (numpy + stdlib wave/hmac only).

Model / assumptions
-------------------
* fs = 44.1 kHz, 16-bit mono WAV. Symbol (= hop) duration 20 ms = 882 samples.
* 8 hop channels, centres 1000, 1500, ..., 4500 Hz (500 Hz apart). Inside a channel the data is
  BFSK: bit 0 -> centre-100 Hz, bit 1 -> centre+100 Hz. So ONE bit per hop (1 symbol/hop,
  BFSK on top). All tone frequencies are multiples of 50 Hz = integer cycles per symbol, so
  the Goertzel bins are orthogonal and a tone at any other 50 Hz multiple leaks nothing.
* Hop sequence: channel[n] = HMAC-SHA256(key, n as 8-byte big-endian)[0] mod 8 (256 % 8 == 0,
  so no modulo bias). Receiver knows key and symbol timing (perfect sync assumed, no acoustic
  channel/ reverberation modelled).
* Baseline "fixed": same BFSK but always channel 3 (2500 Hz centre: tones 2400/2600 Hz).
* Decoder: Goertzel energy at the two BFSK tones of the expected channel, larger wins.
* Conditions: clean; white Gaussian noise at a stated full-band SNR (signal power A^2/2 vs total
  noise variance); fixed-tone jammer sitting ON the bit-0 tone of fixed channel 3 (2400 Hz), amplitude
  relative to the signal tone given as J/S; sweeping jammer: linear chirp 1000->4500 Hz repeating every
  0.5 s, J/S given the same way. The jammer does not know the key (it hits channel 3 / sweeps).
* Stats are computed on 4000-symbol runs held in memory; the WAVs hold a 300-symbol (6 s) message
  and are decoded back FROM the 16-bit file (so quantisation is included).
"""
import hmac, hashlib, os, wave
import numpy as np

FS = 44100
SYM = 882
CH = np.arange(1000, 4501, 500.0)
DEV = 100.0
FIXED_CH = 3
KEY = b"fhss-link-audio-demo"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio")


def hop_sequence(key, n, start=0):
    return np.array([hmac.new(key, (start + i).to_bytes(8, "big"), hashlib.sha256).digest()[0] % 8 for i in range(n)])


def modulate(bits, chans, A=1.0):
    t = np.arange(SYM) / FS
    out = np.empty(len(bits) * SYM)
    for i, (b, c) in enumerate(zip(bits, chans)):
        f = CH[c] + (DEV if b else -DEV)
        out[i * SYM:(i + 1) * SYM] = A * np.sin(2 * np.pi * f * t)
    return out


def noise(n, snr_db, rng, A=1.0):
    return rng.normal(0, np.sqrt(A ** 2 / 2 / 10 ** (snr_db / 10)), n)


def fixed_jam(n, js_db, f=CH[FIXED_CH] - DEV, A=1.0, rng=None):
    ph = rng.uniform(0, 2 * np.pi) if rng is not None else 0
    return A * 10 ** (js_db / 20) * np.sin(2 * np.pi * f * np.arange(n) / FS + ph)


def sweep_jam(n, js_db, f0=1000.0, f1=4500.0, T=0.5, A=1.0):
    t = np.arange(n) / FS % T
    ph = 2 * np.pi * (f0 * t + 0.5 * (f1 - f0) / T * t ** 2)
    return A * 10 ** (js_db / 20) * np.sin(ph)


def goertzel(frames, freq):
    """Goertzel energy of each row of frames at frequency freq (scalar or per-row array)."""
    freq = np.broadcast_to(np.asarray(freq, float), (frames.shape[0],))
    coeff = 2 * np.cos(2 * np.pi * freq / FS)
    s1 = np.zeros(frames.shape[0]); s2 = np.zeros(frames.shape[0])
    for k in range(frames.shape[1]):
        s0 = frames[:, k] + coeff * s1 - s2
        s2, s1 = s1, s0
    return s1 ** 2 + s2 ** 2 - coeff * s1 * s2


def demodulate(x, chans):
    n = len(chans)
    fr = x[:n * SYM].reshape(n, SYM)
    c = CH[np.asarray(chans)]
    return (goertzel(fr, c + DEV) > goertzel(fr, c - DEV)).astype(int)


def ser(bits, x, chans):
    return float(np.mean(demodulate(x, chans) != bits))


def scenario(scheme, cond, level, n=4000, seed=0):
    rng = np.random.default_rng(seed)
    bits = rng.integers(0, 2, n)
    chans = hop_sequence(KEY, n) if scheme == "hop" else np.full(n, FIXED_CH)
    x = modulate(bits, chans)
    if cond == "noise": x = x + noise(len(x), level, rng)
    elif cond == "fixedjam": x = x + fixed_jam(len(x), level, rng=rng)
    elif cond == "sweepjam": x = x + sweep_jam(len(x), level)
    return bits, chans, x


def wav_write(path, x, peak=0.89):
    x = x / np.max(np.abs(x)) * peak
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(FS)
        w.writeframes((np.round(x * 32767)).astype("<i2").tobytes())


def wav_read(path):
    with wave.open(path, "rb") as w:
        assert w.getframerate() == FS and w.getnchannels() == 1 and w.getsampwidth() == 2
        return np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(float) / 32767


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = []
    print(f"channels {CH.astype(int).tolist()} Hz, BFSK +-{DEV:.0f} Hz, {SYM} samples/symbol ({1000*SYM/FS:.0f} ms), fixed channel idx {FIXED_CH} (2400/2600 Hz)")
    print("hop sequence first 16 channels:", hop_sequence(KEY, 16).tolist(),
          "| channel histogram over 4000 hops:", np.bincount(hop_sequence(KEY, 4000), minlength=8).tolist())
    conds = [("clean", None)] + [("noise", s) for s in (0, -10, -20, -24, -27)] + \
            [("fixedjam", j) for j in (-6, 0, 6, 12)] + [("sweepjam", j) for j in (0, 6, 12)]
    print(f"\nSER over 4000 symbols x 3 seeds (levels: noise = full-band SNR dB; jam = J/S dB):")
    print(f"{'condition':22s} {'fixed':>8s} {'hop':>8s}")
    res = []
    for cond, lv in conds:
        r = {}
        for sch in ("fixed", "hop"):
            e = []
            for sd in range(3):
                b, c, x = scenario(sch, cond, lv, seed=sd)
                e.append(ser(b, x, c))
            r[sch] = float(np.mean(e))
        res.append((cond, lv, r["fixed"], r["hop"]))
        print(f"{cond + ('' if lv is None else f' {lv:+d} dB'):22s} {r['fixed']:8.4f} {r['hop']:8.4f}")
    # wavs
    n = 300
    rng = np.random.default_rng(42)
    bits = rng.integers(0, 2, n)
    files = {}
    for sch in ("hop", "fixed"):
        ch = hop_sequence(KEY, n) if sch == "hop" else np.full(n, FIXED_CH)
        clean = modulate(bits, ch)
        r2 = np.random.default_rng(7)
        variants = {"clean": clean, "noise": clean + noise(len(clean), -6, r2),
                    "fixedjam": clean + fixed_jam(len(clean), 6, rng=r2), "sweepjam": clean + sweep_jam(len(clean), 6)}
        for name, x in variants.items():
            p = os.path.join(OUT, f"{sch}_{name}.wav")
            wav_write(p, x)
            y = wav_read(p)
            files[p] = (sch, name, ser(bits, y, ch), np.max(np.abs(y)))
    print("\nWAV files (6 s, 300 bits; decoded back from the 16-bit file):")
    tot = 0
    for p, (sch, name, e, pk) in files.items():
        sz = os.path.getsize(p); tot += sz
        print(f"  {os.path.basename(p):22s} {sz/1e3:7.1f} kB  peak {pk:.3f} FS  SER {e:.4f}")
    print(f"  total {tot/1e6:.2f} MB; noise file = -6 dB full-band SNR, jam files = J/S +6 dB")
    # figure
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 3, figsize=(16, 4.8))
    labs = [f"{c}\n{'' if l is None else f'{l:+d}'}" for c, l, _, _ in res]
    xs = np.arange(len(res))
    ax[0].bar(xs - .2, [r[2] for r in res], .4, label="fixed freq"); ax[0].bar(xs + .2, [r[3] for r in res], .4, label="hopping")
    ax[0].set_xticks(xs); ax[0].set_xticklabels(labs, fontsize=6); ax[0].set_ylabel("symbol error rate"); ax[0].legend(); ax[0].set_title("SER by condition")
    for k, (sch, nm) in enumerate((("hop", "hop_clean"), ("hop", "hop_fixedjam"))):
        y = wav_read(os.path.join(OUT, nm + ".wav"))[:FS * 2]
        fr = np.lib.stride_tricks.sliding_window_view(y, 882)[::441] * np.hanning(882)
        S = 20 * np.log10(np.abs(np.fft.rfft(fr, 4096, axis=1)) + 1e-6)
        ax[1 + k].imshow(S.T[:372], origin="lower", aspect="auto", extent=[0, 2, 0, 372 * FS / 4096], vmin=S.max() - 60)
        ax[1 + k].set(title=nm + " spectrogram (first 2 s)", xlabel="s", ylabel="Hz")
    fig.tight_layout(); fig.savefig(os.path.join(os.path.dirname(OUT), "figures", "audio_fh.png"), dpi=100)
    print("saved figures/audio_fh.png")


if __name__ == "__main__":
    main()
