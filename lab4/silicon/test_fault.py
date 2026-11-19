import numpy as np
from faultsim import *
import refsim

def test_no_fault_no_desync_ctr_zero_bits():
    rng = np.random.default_rng(1)
    # 'out' fault under TMR is fully masked
    r = campaign("tmr", "out", 1, 50, 1)
    assert r["p_desync"] == 0 and r["mean_excess_lost"] == 0

def test_single_counter_flip_baseline_recovers_via_beacon():
    r = campaign("none", "ctr", 1, 200, 2)
    assert r["p_desync"] > 0.95 and r["p_unrecovered"] == 0 and r["mean_rec"] < 70

def test_key_fault_needs_watchdog():
    a = campaign("none_nowd", "key", 1, 60, 3); b = campaign("none", "key", 1, 60, 3)
    assert a["p_unrecovered"] > 0.9 and b["p_unrecovered"] == 0

def test_tmr_masks_single_faults():
    for site, w in (("ctr", 1), ("key", 1), ("fsm", 1), ("out", 1)):
        r = campaign("tmr", site, w, 200, 4)
        assert r["p_desync"] == 0, (site, r)

def test_tmr_multibit_residual_nonzero():
    r = campaign("tmr", "ctr", 4, 400, 5)
    assert 0 < r["p_desync"] < 0.3   # ~12 % expected: 4 random flips over 96 bits, pairs hitting same bit index in 2 copies

def test_dcp_corrects_single_bit_and_detects_some_multi():
    r1 = campaign("dcp", "key", 1, 200, 6); assert r1["p_desync"] == 0
    r2 = campaign("dcp", "key", 2, 400, 7)
    assert r2["p_desync"] < 0.6 and r2["mean_rec"] < 20     # detection -> fast key reload

def test_parity_semantics_even_weight_silent_in_one_copy_detected_by_compare():
    # force: 2 flips in same parity group of copy A only -> parity OK in A, A!=B -> compare mismatch, B parity ok too -> detected
    class R:  # deterministic rng stub
        def choice(self, n, w, replace=False): return np.array([0, 1])   # bits 0,1 of copy A key
    k, c, det, ob = inject("dcp", "key", 2, 0xABCDEF, 5, R())
    assert det is True

def test_fault_free_pdr_matches_link_sim():
    ls = refsim.load("link_sim")
    mine = fault_free_pdr()
    theory = (1 / 13) * 0.05 + (12 / 13) * 0.99
    assert abs(mine - theory) < 0.01
    if ls is not None:
        ref = ls.run("static", slots=20000, hop=True, k=1)["pdr"]
        assert abs(mine - ref) < 0.015, (mine, ref)
