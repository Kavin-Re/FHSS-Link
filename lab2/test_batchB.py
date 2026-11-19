"""Tests for lab2 batch B modules (numpy only). Run: python3 lab2/test_batchB.py   (also collectable by pytest)."""
import os, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "sim"))

import netcontrol as nc
import clock_kalman as ck
import fingerprint as fp
import game_lp as gl
import capacity as cap
import cs_sensing as cs
import evolve as ev


# ---------------- 1. netcontrol ----------------
def test_dlqr_satisfies_riccati():
    A, B = nc.pendulum(0.05)
    Q, R = np.diag([10.0, 1.0]), np.array([[1.0]])
    K, P = nc.dlqr(A, B, Q, R)
    res = Q + A.T @ P @ A - A.T @ P @ B @ np.linalg.solve(R + B.T @ P @ B, B.T @ P @ A) - P
    assert np.max(np.abs(res)) < 1e-8
    assert max(abs(np.linalg.eigvals(A - B @ K))) < 1
    assert max(abs(np.linalg.eigvals(A))) > 1


def test_scalar_bound_matches_theory():
    for a in (1.2, 1.5, 2.0):
        A, B, K = np.array([[a]]), np.array([[1.0]]), np.array([[a]])
        pc = nc.bisect_pc(lambda p: nc.rho_iid(A, B, K, "zero", p))
        assert abs(pc - (1 - 1 / a ** 2)) < 1e-6


def test_pendulum_policy_order_and_predictor_hits_bound():
    A, B = nc.pendulum(0.05); K, _ = nc.dlqr(A, B, np.diag([10.0, 1.0]), np.array([[1.0]]))
    pcs = {pl: nc.bisect_pc(lambda p, pl=pl: nc.rho_iid(A, B, K, pl, p)) for pl in ("zero", "hold", "pred")}
    assert pcs["pred"] < pcs["hold"] < pcs["zero"]
    a = max(abs(np.linalg.eigvals(A)))
    assert abs(pcs["pred"] - (1 - 1 / a ** 2)) < 2e-3


def test_ge_with_dwell_one_equals_iid():
    A, B = nc.pendulum(0.05); K, _ = nc.dlqr(A, B, np.diag([10.0, 1.0]), np.array([[1.0]]))
    q = 0.2; mean = nc.ge_chain(q, 1)[1]
    for pl in ("zero", "hold", "pred"):
        assert abs(nc.rho_ge(A, B, K, pl, q, 1) - nc.rho_iid(A, B, K, pl, mean)) < 1e-9


def test_burstiness_hurts_at_equal_mean():
    A, B = nc.pendulum(0.05); K, _ = nc.dlqr(A, B, np.diag([10.0, 1.0]), np.array([[1.0]]))
    r1 = nc.rho_ge(A, B, K, "zero", 1 / 13, 1); r5 = nc.rho_ge(A, B, K, "zero", 1 / 13, 5)
    assert r5 > r1 and r5 > 1 > r1


def test_monte_carlo_matches_second_moment_theory():
    A, B = nc.pendulum(0.05); K, _ = nc.dlqr(A, B, np.diag([10.0, 1.0]), np.array([[1.0]]))
    w = np.array([0.002, 0.02]); rng = np.random.default_rng(0)
    for pl in ("zero", "hold", "pred"):
        _, th2, _f = nc.simulate(pl, A, B, K, nc.deliv_iid(3000, 250, 0.9, rng), w, rng)
        assert abs(np.mean(th2[120:]) / nc.stationary_ms(A, B, K, pl, 0.9, w) - 1) < 0.1


# ---------------- 2. clock_kalman ----------------
def test_kalman_beats_naive_and_naive_matches_formula():
    en, ek = ck.run(5, cycles=40, R=120, seed=3)
    assert ck.guard_for(ek) < ck.guard_for(en) / 4
    pred = np.sqrt(ck.PAR["sig_v"] ** 2 + (ck.PAR["s0"] ** 2 / 3) * 5 ** 2 / 3)
    assert abs(np.sqrt(np.mean(en ** 2)) / pred - 1) < 0.2


def test_kalman_guard_reasonable_and_holdout_reception():
    en, ek = ck.run(2, cycles=60, R=150, seed=0); hn, hk = ck.run(2, cycles=60, R=150, seed=1)
    g = ck.guard_for(ek)
    assert 0.995 < np.mean(np.abs(hk) <= g) <= 1.0


# ---------------- 3. fingerprint ----------------
def test_fingerprint_identification_and_detection():
    rng = np.random.default_rng(1); ms, mg = fp.enroll(rng)
    assert np.max(np.abs(ms - fp.SKEW)) < 0.3e-6
    n = 200; nodes = np.repeat(np.arange(6), 100)
    sh, gh = fp.genuine(nodes, n, rng)
    D = np.stack([fp.d2(sh, gh, ms[j], mg[j], n) for j in range(6)], axis=1)
    assert np.mean(D.argmin(axis=1) == nodes) > 0.98
    nodesA = rng.integers(0, 6, 3000); sh, gh = fp.genuine(nodesA, n, rng)
    th = np.quantile(fp.d2(sh, gh, ms[nodesA], mg[nodesA], n), 0.99)
    cl = rng.integers(0, 6, 3000)
    sh, gh = fp.impostor("random", cl, n, rng); assert np.mean(fp.d2(sh, gh, ms[cl], mg[cl], n) > th) > 0.95
    sh, gh = fp.impostor("clone", cl, n, rng); assert np.mean(fp.d2(sh, gh, ms[cl], mg[cl], n) > th) < 0.05


# ---------------- 4. game_lp ----------------
def test_simplex_known_games():
    v, x, y, _ = gl.solve_matrix_game(np.array([[3.0, -1.0], [-2.0, 1.0]]))
    assert abs(v - 1 / 7) < 1e-12 and gl.gap(np.array([[3.0, -1.0], [-2.0, 1.0]]), x, y) < 1e-12
    rps = np.array([[0, -1, 1], [1, 0, -1], [-1, 1, 0.0]])
    v, x, y, _ = gl.solve_matrix_game(rps)
    assert abs(v) < 1e-12 and np.allclose(x, 1 / 3) and np.allclose(y, 1 / 3)


def test_value_matches_analytic_and_gap_zero():
    for (M, k, a, b) in ((8, 2, 0.05, 0.99), (13, 1, 0.05, 0.99), (10, 3, 0.4, 0.9)):
        A, _ = gl.payoff_matrix(M, k, a, b)
        v, x, y, _ = gl.solve_matrix_game(A)
        assert abs(v - gl.v_analytic(M, k, a, b)) < 1e-9
        assert gl.gap(A, x, y) < 1e-9 and np.allclose(x, 1 / M, atol=1e-9)


def test_hetero_k1_closed_form_and_cost_threshold():
    q = np.array([.99] * 5 + [.95] * 3 + [.8] * 3 + [.5, .3])
    A, _ = gl.payoff_matrix(13, 1, None, None, q=q, r=0.05)
    v, x, y, _ = gl.solve_matrix_game(A)
    assert abs(v - gl.v_hetero_k1(q, 0.05)[0]) < 1e-9 and x[-2:].sum() < 1e-9 and gl.gap(A, x, y) < 1e-9
    Delta = 0.94
    for c, jam in ((0.05, True), (0.1, False)):
        A, S = gl.payoff_matrix(13, 3, 0.05, 0.99, cost=c, sizes=range(0, 4))
        v = gl.solve_matrix_game(A)[0]
        assert abs(v - (0.99 - 3 * max(0.0, Delta / 13 - c))) < 1e-9


def test_hedge_gap_within_proven_bound():
    q = np.array([.99] * 5 + [.95] * 3 + [.8] * 3 + [.5, .3])
    A, _ = gl.payoff_matrix(13, 1, None, None, q=q, r=0.05)
    xb, yb, g, bd = gl.hedge(A, 3000)
    assert 0 <= g + 1e-12 and g <= bd


# ---------------- 5. capacity ----------------
def test_capacity_formulas():
    assert abs(cap.c_bsc(0.11002786) - 0.5) < 1e-5
    assert abs(cap.p_for_capacity(0.5) - 0.11003) < 1e-4
    assert abs(10 * np.log10((2 ** 1 - 1) / 1) - 0.0) < 1e-12  # R=1/2 Shannon limit is 0 dB
    assert abs(cap.ebn0_hard_from_p(1e-3, 1.0) - 6.79) < 0.02
    assert 0.1 < cap.ebn0_bpsk_soft(0.5) < 0.3
    from game_lp import payoff_matrix, solve_matrix_game
    A, _ = payoff_matrix(13, 3, 1 - cap.EJ, 1 - cap.EC)
    assert abs(solve_matrix_game(A)[0] - cap.c_hop(13, 3)) < 1e-9
    assert cap.c_hop(13, 3, shared=False) < 0.06


def test_mds_formula_vs_real_codec():
    import fec
    rng = np.random.default_rng(0); n, k, eps = 6, 4, 0.3; fails = 0; T = 600
    for _ in range(T):
        data = [rng.integers(0, 256, 3).astype(np.uint8) for _ in range(k)]
        pk = fec.erasure_encode(data, n); keep = rng.random(n) >= eps
        dec = fec.erasure_decode({i: pk[i] for i in range(n) if keep[i]}, n, k)
        if dec is None or not all((a == b).all() for a, b in zip(dec, data)): fails += 1
    pf = cap.mds_fail(n, k, eps)
    assert abs(fails / T - pf) < 4 * np.sqrt(pf * (1 - pf) / T)
    assert cap.best_k(255, 0.2) / 255 < 0.8 and cap.best_k(255, 0.2) > cap.best_k(32, 0.2) * 255 / 32 * 0.99  # rate rises with n


def test_hamming_corrects_single_errors():
    import fec
    rng = np.random.default_rng(0); b = rng.integers(0, 2, 400).astype(np.uint8); c = fec.ham_encode(b); c[3::7] ^= 1
    assert (fec.ham_decode(c)[:400] == b).all()


# ---------------- 6. cs_sensing ----------------
def test_omp_noise_free_exact():
    rng = np.random.default_rng(0); N = cs.N
    x = np.zeros(N, complex); idx = [7, 100, 201]; x[idx] = [1, 1.5j, -2]
    Phi = cs.make_phi("sample", 60, rng); est, coef = cs.omp(Phi, Phi @ x, 3)
    assert est == sorted(idx) and np.allclose(np.sort(np.abs(coef)), [1, 1.5, 2], atol=1e-9)


def test_phase_transition():
    hi = cs.prob("sample", 77, 5, 1e-4, 60, 1)[0]; lo = cs.prob("sample", 10, 5, 1e-4, 60, 2)[0]
    assert hi > 0.9 and lo < 0.1
    assert cs.prob("sample", 77, 5, 10 ** (-0.5), 40, 3)[0] < 0.3  # SNR 5 dB: fails (noise folding)


# ---------------- 7. evolve ----------------
def test_play_payoff_and_popgame():
    rng = np.random.default_rng(0)
    d = [np.full((1, 1, 13), -1e9), np.zeros((1, 1, 2), int)]; d[0][0, 0, 3] = 0
    j = [np.full((1, 1, 13), -1e9), np.zeros((1, 1, 13), int)]; j[0][0, 0, 3] = 0
    A, use = ev.play(d, j, rng, 50); assert abs(A[0, 0] - 0.05) < 1e-12 and use[0, 3] == 50
    j[0][0, 0, 3] = -1e9; j[0][0, 0, 4] = 0
    A, _ = ev.play(d, j, rng, 50); assert abs(A[0, 0] - 0.99) < 1e-12
    r = ev.popgame(1, N=500, gens=300)
    ta = ev.entropy_bits(np.array(r["upop"])[-150:].mean(axis=0))
    assert ta > 3.5 and 0.87 < np.mean(r["deliv"][-150:]) < 0.93
    r = ev.popgame(1, W=range(5), N=500, gens=300)
    assert np.mean(r["deliv"][-150:]) > 0.95 and np.array(r["upop"])[-150:, :5].sum(axis=1).mean() < 0.1


if __name__ == "__main__":
    t0 = time.time(); fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            t = time.time()
            try:
                fn(); print(f"PASS {name} ({time.time()-t:.1f}s)", flush=True)
            except Exception as e:
                fails += 1; print(f"FAIL {name}: {type(e).__name__}: {e}", flush=True)
    print(f"{'ALL PASSED' if not fails else str(fails) + ' FAILED'} in {time.time()-t0:.1f}s")
    sys.exit(1 if fails else 0)
