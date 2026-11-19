"""Tests for lab batch A: gps_acq, ss_watermark, audio_fh, amc.
Run:  python3 lab/test_batchA.py   (or pytest lab/test_batchA.py). Takes ~1 minute."""
import os, sys, tempfile
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gps_acq as g
import ss_watermark as w
import audio_fh as a
import amc


# ------------------------------------------------------------------ GPS
def test_gold_codes():
    assert ''.join(map(str, g.ca_bits(1)[:10])) == "1100100000"          # published PRN1 first chips
    assert len(g.ca_bits(1)) == 1023 and set(np.unique(g.ca_code(5))) == {-1.0, 1.0}
    xc = lambda p, q: np.real(np.fft.ifft(np.fft.fft(g.ca_code(p)) * np.conj(np.fft.fft(g.ca_code(q)))))
    ac = xc(3, 3)
    assert abs(ac[0] - 1023) < 1e-6 and np.abs(ac[1:]).max() <= 65 + 1e-6
    for p in range(1, 9):
        for q in range(p + 1, 9):
            assert np.abs(xc(p, q)).max() <= 65 + 1e-6                           # Gold three-valued bound


def test_acquisition_and_prn_id():
    rng = np.random.default_rng(0)
    rx = g.make_signal(4, -10, 2300.0, 777, 1, rng=rng)
    m, i, j = g.metric(g.surface(rx, 4))
    assert j == 777 and abs(g.DOPP[i] - 2300) <= 250 and m > 30
    ms = [g.metric(g.surface(rx, q))[0] for q in range(1, 9)]
    assert int(np.argmax(ms)) + 1 == 4


def test_pd_threshold_and_jammer():
    thr = g.calibrate_threshold(1, trials=400)
    assert g.detect_prob(-14, 1, thr, trials=40) > 0.9
    assert g.detect_prob(-34, 1, thr, trials=40) < 0.2                    # far below sensitivity
    assert g.detect_prob(-10, 1, thr, trials=40, jsr=10) > 0.9            # 10 dB CW jammer tolerated
    assert g.detect_prob(-10, 1, thr, trials=40, jsr=35) < 0.2            # beyond spreading gain: fails


def test_spoof_flag():
    ta, tb = g.calibrate_spoof(1, trials=150)
    rng = np.random.default_rng(3)
    spoof = np.mean([any(g.spoof_flag(g.spoof_case(3, None, -8, 1, rng), 3, ta, tb)) for _ in range(40)])
    both = np.mean([any(g.spoof_flag(g.spoof_case(3, -20, -5, 1, rng), 3, ta, tb)) for _ in range(40)])
    clean = np.mean([any(g.spoof_flag(g.spoof_case(3, rng.uniform(-24, -16), None, 1, rng), 3, ta, tb)) for _ in range(60)])
    assert spoof > 0.9 and both > 0.9 and clean < 0.15


# ------------------------------------------------------------------ watermark
def test_dct_orthonormal_roundtrip():
    assert np.allclose(w.D @ w.D.T, np.eye(8), atol=1e-12)
    im = w.make_image(3)
    assert im.shape == (256, 256) and 0 <= im.min() and im.max() <= 255
    assert np.allclose(w.blocks_idct(w.blocks_dct(im)), im, atol=1e-9)


def test_watermark_detection_and_attacks():
    im = w.make_image(1)
    wm = w.embed(im, 1234)
    assert w.psnr(im, wm) > 38
    det = w.Detector([1234] + list(range(10000, 10050)))
    z, _ = det.z(wm)
    assert z[0] > 15 and np.abs(z[1:]).max() < 4.5
    rng = np.random.default_rng(0)
    for name, fn, search in w.ATTACKS:
        if name in ("noise s=20", "JPEG Q=50", "crop+pad 32px", "blur s=0.7", "scale 2x down/up", "shift-crop (5,3)+grid search"):
            z, _ = det.z(fn(wm, rng), search)
            assert z[0] > 5 and z[0] > z[1:].max() + 1, name
    z, _ = det.z(im)                                                      # unmarked image: true key not detected
    assert abs(z[0]) < 4.5


def test_watermark_message():
    im = w.make_image(7)
    bits = np.random.default_rng(1).integers(0, 2, 16)
    wm = w.embed_msg(im, 42, bits)
    assert np.array_equal(w.decode_msg(wm, 42), bits)
    assert np.array_equal(w.decode_msg(w.a_jpeg(wm, 50), 42), bits)
    assert np.mean(w.decode_msg(wm, 43) != bits) > 0.15                   # wrong key -> ~random


# ------------------------------------------------------------------ audio
def test_hop_sequence():
    s = a.hop_sequence(a.KEY, 4000)
    assert np.array_equal(s, a.hop_sequence(a.KEY, 4000)) and s.min() == 0 and s.max() == 7
    assert np.bincount(s, minlength=8).min() > 400
    assert not np.array_equal(s[:50], a.hop_sequence(b"other key", 50))


def test_audio_ser():
    for sch in ("fixed", "hop"):
        b, c, x = a.scenario(sch, "clean", None, n=500)
        assert a.ser(b, x, c) == 0
    b, c, x = a.scenario("fixed", "fixedjam", 6, n=1500)
    assert a.ser(b, x, c) > 0.35
    b, c, x = a.scenario("hop", "fixedjam", 6, n=1500)
    assert a.ser(b, x, c) < 0.12


def test_wav_roundtrip_and_files():
    b, c, x = a.scenario("hop", "noise", -6, n=100)
    p = os.path.join(tempfile.mkdtemp(), "t.wav")
    a.wav_write(p, x)
    y = a.wav_read(p)
    assert np.max(np.abs(y)) <= 0.9 and a.ser(b, y, c) == 0
    d = a.OUT
    if os.path.isdir(d):                                                   # files produced by audio_fh.main()
        files = [f for f in os.listdir(d) if f.endswith(".wav")]
        assert sum(os.path.getsize(os.path.join(d, f)) for f in files) < 6e6
        for f in files:
            v = a.wav_read(os.path.join(d, f))
            assert 0.5 < np.max(np.abs(v)) < 0.95                          # normalised, not clipped


# ------------------------------------------------------------------ AMC
def test_amc():
    rng = np.random.default_rng(0)
    for k in amc.CLASSES:
        assert np.all(np.isfinite(amc.features(amc.gen(k, 10, rng))))
    Xtr, ytr, _ = amc.dataset([0, 10, 20], 80, seed=1)
    sm = amc.Softmax(it=1500).fit(Xtr, ytr, 5)
    Xte, yte, _ = amc.dataset([10], 40, seed=5)
    assert np.mean(sm.predict(Xte) == yte) > 0.9
    cm = amc.confusion(yte, sm.predict(Xte))
    assert cm.sum() == len(yte) and np.trace(cm) / cm.sum() > 0.9


if __name__ == "__main__":
    import time
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            t = time.time()
            try:
                fn(); print(f"PASS {name} ({time.time() - t:.1f}s)")
            except Exception as e:
                import traceback; traceback.print_exc(); print(f"FAIL {name}: {e!r}"); fails += 1
    print("ALL PASSED" if not fails else f"{fails} FAILED")
    sys.exit(1 if fails else 0)
