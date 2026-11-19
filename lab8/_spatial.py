"""Deterministic (mean path-loss, no fading) delivery along a patrol path; shared by e12 and e13.
Geometry: fixed transmitter(s) (base, optional relay) send to a MOBILE receiver walking the path. A jammer (or swarm) raises the
interference at the mobile receiver on the jammed channels. Per slot the hop channel is jammed with probability q = k/13
(jammer occupies k of 13 channels, blind to the hop), identically for the base and relay copies (same slot, same channel).
Packet is delivered if the base copy OR the relay copy decodes (selection diversity at packet level)."""
import numpy as np
from _common import *

PT_DBM = 15.0         # transmitter power of base and relay
K_JAM, Q_JAM = 3, 3 / 13

def tx_signal_mw(tx, path, n=None):
    """tx (T,2) -> (T, m) mean received signal power"""
    return rx_mw(PT_DBM, dist(np.atleast_2d(tx), path), n)

def delivery_points(sig_mw, interf_mw, q=Q_JAM):
    """sig_mw (T, m) ; interf_mw broadcastable to (..., m) -> delivery per path point (..., m)"""
    pc = prr_from_mw(sig_mw, 0.0)                                    # (T, m) clean channel
    pj = prr_from_mw(sig_mw[(slice(None),) + (None,) * (np.ndim(interf_mw) - 1)] , np.asarray(interf_mw)[None])  # (T, ..., m)
    clean = 1 - np.prod(1 - pc, axis=0)
    jam = 1 - np.prod(1 - pj, axis=0)
    return (1 - q) * clean + q * jam

def interference_mw(jam_pos, pj_dbm, path, n=None):
    """sum of power from jammers jam_pos (J,2) each at pj_dbm (scalar or (J,)) -> (m,)"""
    d = dist(np.atleast_2d(jam_pos), path)
    return rx_mw(np.asarray(pj_dbm, dtype=float).reshape(-1, 1) if np.ndim(pj_dbm) else pj_dbm, d, n).sum(0)

def mean_delivery(tx, jam_pos, pj_dbm, path, n=None, q=Q_JAM):
    S = tx_signal_mw(tx, path, n)
    I = interference_mw(jam_pos, pj_dbm, path, n)
    return float(delivery_points(S, I, q).mean())
