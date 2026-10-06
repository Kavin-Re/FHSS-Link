"""Baseband Monte Carlo + theory for fixed-frequency, FH-SS and DS-SS BPSK links.

Model (all assumptions are deliberate and listed in docs/RESULTS.md):
- BPSK, real baseband samples, per-chip signal amplitude 1 (power 1).
- AWGN with per-chip variance sigma2 = chips/(2*EbN0), chips = 1 (fixed, FH) or Gp (DS).
- Interferer = continuous-wave tone with random phase, relative power JSR = J/S (per sample).
  Tone amplitude A = sqrt(2*JSR). This is an "interference source on our own test link", not a model of a real jammer.
- Fixed: the link sits on the interfered channel.
- FH: M channels, hop pattern pseudo-random and shared by TX/RX (perfect sync assumed); the interferer occupies
  k channels with its total power split equally (power JSR/k per jammed channel).
- DS: Gp chips per bit with a fresh random +-1 code per bit; the tone covers all chips.
"""
import numpy as np
from math import erfc, sqrt


def qfunc(x):
    return 0.5 * erfc(x / sqrt(2.0))


def ber_awgn_theory(ebn0_db):
    ebn0 = 10 ** (ebn0_db / 10)
    return qfunc(sqrt(2 * ebn0))


def ber_tone_theory(ebn0_db, jsr, n_phase=4000):
    """Exact BPSK error rate for a random-phase tone interferer (fixed link, or the jammed branch of FH)."""
    ebn0 = 10 ** (ebn0_db / 10)
    sigma = sqrt(1.0 / (2 * ebn0))
    if jsr <= 0:
        return qfunc(1.0 / sigma)
    A = sqrt(2 * jsr)
    phi = np.linspace(0, 2 * np.pi, n_phase, endpoint=False)
    z = (1 + A * np.cos(phi)) / sigma
    return float(np.mean([qfunc(v) for v in z]))


def ber_fh_theory(ebn0_db, jsr, M, k=1):
    clean = ber_tone_theory(ebn0_db, 0.0)
    jam = ber_tone_theory(ebn0_db, jsr / k)
    return (k / M) * jam + (1 - k / M) * clean


def ber_ds_theory(ebn0_db, jsr, Gp):
    """Gaussian approximation after despreading (central limit over Gp chips)."""
    ebn0 = 10 ** (ebn0_db / 10)
    sigma2 = Gp / (2 * ebn0)  # per-chip noise variance
    return qfunc(sqrt(Gp) / sqrt(sigma2 + jsr))


def pdr_theory(ebn0_db, jsr, M, k=1, L=256):
    """Packet delivery ratio when one packet is sent per hop on one channel (packet = L bits, no coding)."""
    clean = ber_tone_theory(ebn0_db, 0.0)
    jam = ber_tone_theory(ebn0_db, jsr / k)
    return ((M - k) / M) * (1 - clean) ** L + (k / M) * (1 - jam) ** L


def simulate_ber(scheme, ebn0_db, jsr_db=None, nbits=200_000, M=16, k=1, Gp=16, bits_per_hop=1, seed=1):
    rng = np.random.default_rng(seed)
    ebn0 = 10 ** (ebn0_db / 10)
    jsr = 0.0 if jsr_db is None else 10 ** (jsr_db / 10)
    errors = 0
    if scheme in ("fixed", "fh"):
        sigma = sqrt(1.0 / (2 * ebn0))
        b = rng.choice([-1.0, 1.0], size=nbits)
        r = b + rng.normal(0, sigma, size=nbits)
        if jsr > 0:
            if scheme == "fixed":
                A, active = sqrt(2 * jsr), np.ones(nbits, dtype=bool)
            else:
                nhops = -(-nbits // bits_per_hop)
                hop = np.repeat(rng.integers(0, M, size=nhops), bits_per_hop)[:nbits]
                A, active = sqrt(2 * jsr / k), hop < k
            phi = rng.uniform(0, 2 * np.pi, size=nbits)
            r = r + active * A * np.cos(phi)
        errors = int(np.sum(np.sign(r) != b))
    elif scheme == "ds":
        sigma = sqrt(Gp / (2 * ebn0))
        A = sqrt(2 * jsr)
        w0 = 2 * np.pi * 0.1
        j = np.arange(Gp)
        chunk = 20_000
        done = 0
        while done < nbits:
            n = min(chunk, nbits - done)
            b = rng.choice([-1.0, 1.0], size=n)
            c = rng.choice([-1.0, 1.0], size=(n, Gp))
            r = b[:, None] * c + rng.normal(0, sigma, size=(n, Gp))
            if jsr > 0:
                phi = rng.uniform(0, 2 * np.pi, size=(n, 1))
                r = r + A * np.cos(w0 * j[None, :] + phi)
            z = np.sum(c * r, axis=1)
            errors += int(np.sum(np.sign(z) != b))
            done += n
    else:
        raise ValueError(scheme)
    return errors / nbits
