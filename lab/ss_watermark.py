"""Spread-spectrum image watermark in the 8x8 block-DCT mid-frequency band (numpy only).

Model / assumptions
-------------------
* Host: synthetic 256x256 greyscale image (gradient + circles/rectangles + smooth
  texture + a sinusoid), seeded, no external files. 8x8 orthonormal DCT-II built from a numpy matrix.
* Embedding: every block's mid-frequency coefficients (BAND: 3 <= u+v <= 8, 37 per block,
  32*32 blocks -> M = 37888 "chips") get  c' = c + alpha * w,  w = +-1 key-seeded pattern.
  The watermarked image is rounded to 8-bit and clipped, then PSNR is measured.
* Detection is BLIND (the original is not available): z = <c, w> / (std(c) * sqrt(M)),
  where c are the received band coefficients. Normalised correlation rho = <c,w>/(|c||w|)
  is also reported. Under a wrong key z is ~N(0,1); under the true key
  z ~ alpha*sqrt(M)/std(c_host) -> the sqrt(M) is the processing gain: each chip carries
  only a tiny fraction of the signal, but M of them add coherently while host+attack noise
  adds incoherently. That is why a mark well below the host's own coefficient size survives
  noise/JPEG/blur: robustness ~ alpha*sqrt(M) / (host+attack noise std).
* Multi-bit: 16 bits; the band positions are split into 16 key-permuted disjoint subsets
  (M/16 = 2368 chips each); bit i embeds pattern pair (w_i0 or w_i1) at strength ALPHA_MSG,
  decoded by comparing the correlation with each member of the pair.
* Attacks: additive Gaussian noise, JPEG-like quantisation (standard luminance table scaled by
  quality), crop+zero-pad (border, block-aligned), shift-crop (5,3)px with an 8x8 grid search
  in the detector, Gaussian blur, 2x down (box) / 2x up (bilinear) scaling.
* ROC-like table: 20 host images x (true key + 200 wrong keys).
"""
import numpy as np

B = 8
IMG = 256
NB = IMG // B
BAND = [(u, v) for u in range(B) for v in range(B) if 3 <= u + v <= 8]
MB = len(BAND)
M = NB * NB * MB
ALPHA = 3.0
ALPHA_MSG = 4.0
_bu = np.array([u for u, v in BAND]); _bv = np.array([v for u, v in BAND])


def dct_matrix(n=B):
    k = np.arange(n)[:, None]; i = np.arange(n)[None, :]
    D = np.sqrt(2.0 / n) * np.cos(np.pi * (2 * i + 1) * k / (2 * n))
    D[0] /= np.sqrt(2)
    return D
D = dct_matrix()


def blocks_dct(img, off=(0, 0), nb=NB):
    """Block DCT of nb x nb blocks starting at pixel offset -> [nb, nb, 8, 8]."""
    oy, ox = off
    sub = img[oy:oy + nb * B, ox:ox + nb * B].reshape(nb, B, nb, B).transpose(0, 2, 1, 3)
    return D @ sub @ D.T


def blocks_idct(C):
    nb = C.shape[0]
    return (D.T @ C @ D).transpose(0, 2, 1, 3).reshape(nb * B, nb * B)


def make_image(seed=0):
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:IMG, 0:IMG] / IMG
    a, b = rng.uniform(40, 120, 2)
    img = a * x + b * y + 40
    for _ in range(6):
        cy, cx = rng.uniform(0.1, 0.9, 2); r = rng.uniform(0.05, 0.2)
        img[(y - cy) ** 2 + (x - cx) ** 2 < r ** 2] += rng.uniform(-60, 60)
    for _ in range(5):
        y0, x0 = rng.integers(0, 200, 2); h, w = rng.integers(15, 60, 2)
        img[y0:y0 + h, x0:x0 + w] += rng.uniform(-50, 50)
    n = rng.standard_normal((IMG, IMG))
    k = np.exp(-np.arange(-4, 5) ** 2 / (2 * 1.5 ** 2)); k /= k.sum()
    n = np.apply_along_axis(lambda r_: np.convolve(r_, k, 'same'), 1, n)
    n = np.apply_along_axis(lambda r_: np.convolve(r_, k, 'same'), 0, n)
    img += 36 * n / n.std()
    img += 8 * np.sin(2 * np.pi * (rng.integers(8, 30) * x + rng.integers(8, 30) * y))
    return np.clip(img, 0, 255)


def pattern(key, shape=(NB, NB, MB)):
    return np.random.default_rng(key).choice([-1.0, 1.0], size=shape)


def embed(img, key, alpha=ALPHA):
    C = blocks_dct(img - 128)
    w = pattern(key)
    C[:, :, _bu, _bv] += alpha * w
    return np.clip(np.round(blocks_idct(C) + 128), 0, 255)


def psnr(a, b):
    return 10 * np.log10(255 ** 2 / np.mean((a - b) ** 2))


def band_coefs(img, off=(0, 0), nb=NB):
    return blocks_dct(img - 128, off, nb)[:, :, _bu, _bv]


class Detector:
    def __init__(self, keys):
        self.keys = list(keys)
        self.K = np.stack([pattern(k).ravel() for k in self.keys]).astype(np.float32)   # [nk, M]
        self.K31 = {}
        for sy in (0, 1):
            for sx in (0, 1):
                P = self.K.reshape(len(keys), NB, NB, MB)[:, sy:sy + NB - 1, sx:sx + NB - 1]
                self.K31[(sy, sx)] = np.ascontiguousarray(P.reshape(len(keys), -1))

    def z(self, img, search=False):
        """(z-scores, rho) of all keys. search=True: max over the 64 8x8 grid offsets (shift-crop attack)."""
        if not search:
            c = band_coefs(img).ravel().astype(np.float32)
            kc = self.K @ c
            return kc / (c.std() * np.sqrt(M)), kc / (np.linalg.norm(c) * np.sqrt(M))
        best = None
        for oy in range(B):
            for ox in range(B):
                c = band_coefs(img, (oy, ox), NB - 1).ravel().astype(np.float32)
                Kc = self.K31[(int(oy > 0), int(ox > 0))]
                z = (Kc @ c) / (c.std() * np.sqrt(c.size))
                best = z if best is None else np.maximum(best, z)
        return best, None


# ---------------- attacks ----------------
JPEG_T = np.array([[16, 11, 10, 16, 24, 40, 51, 61], [12, 12, 14, 19, 26, 58, 60, 55],
                   [14, 13, 16, 24, 40, 57, 69, 56], [14, 17, 22, 29, 51, 87, 80, 62],
                   [18, 22, 37, 56, 68, 109, 103, 77], [24, 35, 55, 64, 81, 104, 113, 92],
                   [49, 64, 78, 87, 103, 121, 120, 101], [72, 92, 95, 98, 112, 100, 103, 99]], float)


def a_noise(img, s, rng): return np.clip(np.round(img + rng.normal(0, s, img.shape)), 0, 255)


def a_jpeg(img, q, rng=None):
    s = 5000 / q if q < 50 else 200 - 2 * q
    T = np.clip(np.floor((JPEG_T * s + 50) / 100), 1, 255)
    C = blocks_dct(img - 128)
    return np.clip(np.round(blocks_idct(np.round(C / T) * T) + 128), 0, 255)


def a_croppad(img, b=32, rng=None):
    out = np.zeros_like(img) + img.mean(); out[b:-b, b:-b] = img[b:-b, b:-b]; return out


def a_shift(img, rng=None, dy=5, dx=3):
    out = np.zeros_like(img) + img.mean(); out[:IMG - dy, :IMG - dx] = img[dy:, dx:]; return out


def _gk(s):
    r = int(np.ceil(3 * s)); k = np.exp(-np.arange(-r, r + 1) ** 2 / (2 * s * s)); return k / k.sum()


def a_blur(img, s, rng=None):
    k = _gk(s); r = len(k) // 2
    p = np.pad(img, r, mode='reflect')
    p = np.apply_along_axis(lambda v: np.convolve(v, k, 'valid'), 1, p)
    return np.apply_along_axis(lambda v: np.convolve(v, k, 'valid'), 0, p)


def a_scale(img, rng=None):
    small = img.reshape(IMG // 2, 2, IMG // 2, 2).mean((1, 3))
    xs = (np.arange(IMG) + 0.5) / 2 - 0.5
    f = lambda v: np.interp(xs, np.arange(IMG // 2), v)
    up = np.apply_along_axis(f, 1, small)
    return np.apply_along_axis(f, 0, up)


ATTACKS = [("none", lambda im, r: im, False)] + \
          [(f"noise s={s}", (lambda s: lambda im, r: a_noise(im, s, r))(s), False) for s in (5, 10, 20, 40)] + \
          [(f"JPEG Q={q}", (lambda q: lambda im, r: a_jpeg(im, q))(q), False) for q in (90, 70, 50, 30, 10)] + \
          [("crop+pad 32px", lambda im, r: a_croppad(im), False),
           ("shift-crop (5,3)+grid search", lambda im, r: a_shift(im), True)] + \
          [(f"blur s={s}", (lambda s: lambda im, r: a_blur(im, s))(s), False) for s in (0.7, 1.0, 1.5)] + \
          [("scale 2x down/up", lambda im, r: a_scale(im), False)]


def auc(pos, neg):
    neg = np.sort(neg)
    return float(np.mean([np.searchsorted(neg, p) / len(neg) for p in pos]))


def roc_table(n_img=20, n_wrong=200, key=1234, alpha=ALPHA, verbose=True):
    keys = [key] + list(range(10000, 10000 + n_wrong))
    det = Detector(keys)
    rng = np.random.default_rng(0)
    imgs = [make_image(s) for s in range(n_img)]
    wms = [embed(im, key, alpha) for im in imgs]
    ps = np.array([psnr(a, b) for a, b in zip(imgs, wms)])
    if verbose:
        print(f"alpha={alpha}: M={M} chips, PSNR watermarked vs original: mean {ps.mean():.2f} dB (min {ps.min():.2f})")
    rows = []
    for name, fn, search in ATTACKS:
        zt, zw, rho_t = [], [], []
        for w in wms:
            z, rho = det.z(fn(w, rng), search)
            zt.append(z[0]); zw.extend(z[1:])
            if rho is not None: rho_t.append(rho[0])
        zt, zw = np.array(zt), np.array(zw)
        thr = np.quantile(zw, 0.999)
        rows.append(dict(name=name, zt=zt.mean(), zt_min=zt.min(), zw_mean=zw.mean(), zw_std=zw.std(), zw_max=zw.max(),
                         auc=auc(zt, zw), pd4=float(np.mean(zt > 4)), pfa4=float(np.mean(zw > 4)),
                         pd_pfa1e3=float(np.mean(zt > thr)), thr=thr, rho=np.mean(rho_t) if rho_t else float('nan')))
        if verbose:
            r = rows[-1]
            print(f"{name:30s} z_true mean {r['zt']:7.2f} (min {r['zt_min']:6.2f}) | wrong {r['zw_mean']:+.2f}+-{r['zw_std']:.2f} max {r['zw_max']:.2f} | "
                  f"AUC {r['auc']:.3f} | Pd(z>4) {r['pd4']:.2f} Pfa(z>4) {r['pfa4']:.4f} | Pd@Pfa1e-3 {r['pd_pfa1e3']:.2f} | rho {r['rho']:.4f}")
    return rows, det, imgs, wms


# ---------------- multi-bit ----------------
def msg_patterns(key, nbits=16):
    rng = np.random.default_rng(key)
    perm = rng.permutation(NB * NB * MB).reshape(nbits, -1)
    pairs = rng.choice([-1.0, 1.0], size=(nbits, 2, perm.shape[1]))
    return perm, pairs


def embed_msg(img, key, bits, alpha=ALPHA_MSG):
    C = blocks_dct(img - 128)
    flat = C[:, :, _bu, _bv].ravel()
    perm, pairs = msg_patterns(key, len(bits))
    for i, b in enumerate(bits):
        flat[perm[i]] += alpha * pairs[i, b]
    C[:, :, _bu, _bv] = flat.reshape(NB, NB, MB)
    return np.clip(np.round(blocks_idct(C) + 128), 0, 255)


def decode_msg(img, key, nbits=16):
    c = band_coefs(img).ravel()
    perm, pairs = msg_patterns(key, nbits)
    return np.array([int(c[perm[i]] @ pairs[i, 1] > c[perm[i]] @ pairs[i, 0]) for i in range(nbits)])


def ber_table(trials=20, verbose=True):
    rng = np.random.default_rng(5)
    out = []
    ps = []
    data = []
    for t in range(trials):
        im = make_image(100 + t); bits = rng.integers(0, 2, 16); key = 500 + t
        wm = embed_msg(im, key, bits); ps.append(psnr(im, wm)); data.append((wm, bits, key))
    if verbose:
        print(f"multi-bit: 16 bits, alpha={ALPHA_MSG}, {M // 16} chips/bit, PSNR mean {np.mean(ps):.2f} dB")
    for name, fn, search in ATTACKS:
        if search:     # message decoder has no grid search; skipped honestly
            continue
        err = 0
        for wm, bits, key in data:
            err += int(np.sum(decode_msg(fn(wm, rng), key) != bits))
        ber = err / (16 * trials)
        out.append((name, ber))
        if verbose: print(f"  {name:30s} BER {ber:.4f}  ({err}/{16 * trials} bit errors)")
    err = 0
    for wm, bits, key in data:
        err += int(np.sum(decode_msg(wm, key + 7777) != bits))
    if verbose: print(f"  decoding with WRONG key, no attack: BER {err / (16 * trials):.3f} (expect ~0.5)")
    return out, ps


def main():
    print(f"band: {MB} coefficients/block, u+v in [3,8]; M={M}; sqrt(M)={np.sqrt(M):.0f} (processing gain {10*np.log10(M):.1f} dB)")
    rows, det, imgs, wms = roc_table()
    print("\nalpha sweep (JPEG Q=50, 20 images, 200 wrong keys):")
    for a in (1, 2, 3, 4, 6):
        r, _, _, _ = roc_table(alpha=a, verbose=False)
        jr = [x for x in r if x['name'] == 'JPEG Q=50'][0]
        im0 = make_image(0)
        print(f"  alpha {a}: PSNR {psnr(im0, embed(im0, 1234, a)):.2f} dB, JPEG50 z_true {jr['zt']:.2f}, AUC {jr['auc']:.3f}, Pd(z>4) {jr['pd4']:.2f}")
    print()
    ber, _ = ber_table()

    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 3, figsize=(15, 9))
    ax[0, 0].imshow(imgs[0], cmap='gray', vmin=0, vmax=255); ax[0, 0].set_title("host (seed 0)")
    ax[0, 1].imshow(wms[0], cmap='gray', vmin=0, vmax=255); ax[0, 1].set_title(f"watermarked, alpha={ALPHA}, PSNR {psnr(imgs[0], wms[0]):.1f} dB")
    ax[0, 2].imshow((wms[0] - imgs[0]) * 10 + 128, cmap='gray', vmin=0, vmax=255); ax[0, 2].set_title("difference x10")
    names = [r['name'] for r in rows]
    ax[1, 0].barh(range(len(rows)), [r['zt'] for r in rows], label="true key (mean z)")
    ax[1, 0].barh(range(len(rows)), [r['zw_max'] for r in rows], height=0.3, color='C3', label="max wrong key")
    ax[1, 0].axvline(4, color='k', ls='--'); ax[1, 0].set_yticks(range(len(rows))); ax[1, 0].set_yticklabels(names, fontsize=7)
    ax[1, 0].invert_yaxis(); ax[1, 0].legend(fontsize=7); ax[1, 0].set_title("detection statistic z per attack")
    z, _ = det.z(a_jpeg(wms[0], 50))
    ax[1, 1].hist(z[1:], bins=25, color='C3', alpha=.7, label="200 wrong keys"); ax[1, 1].axvline(z[0], color='C0', label=f"true key z={z[0]:.1f}")
    ax[1, 1].set_title("JPEG Q=50, image 0"); ax[1, 1].legend(); ax[1, 1].set_xlabel("z")
    ax[1, 2].barh(range(len(ber)), [b for _, b in ber]); ax[1, 2].set_yticks(range(len(ber))); ax[1, 2].set_yticklabels([n for n, _ in ber], fontsize=7)
    ax[1, 2].invert_yaxis(); ax[1, 2].set_title("16-bit message BER per attack"); ax[1, 2].axvline(0.5, color='k', ls=':')
    fig.tight_layout(); fig.savefig("figures/ss_watermark.png", dpi=100)
    print("saved figures/ss_watermark.png")


if __name__ == "__main__":
    main()
