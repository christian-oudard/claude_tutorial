import math

from post_opt.physics import buckling as B


def test_greenhill_height_and_lambda_consistent():
    E, I, w = 200e9, math.pi * 0.01**4 / 4, 7850 * 9.81 * math.pi * 0.01**2
    h_cr = B.greenhill_height(E, I, w, SF=1.0)
    # at the critical height the self-weight load factor is exactly 1
    assert math.isclose(B.greenhill_lambda(E, I, w, h_cr), 1.0, rel_tol=1e-9)


def test_greenhill_matches_analytic_form():
    E, I, w = 1.0, 1.0, 1.0
    assert math.isclose(B.greenhill_height(E, I, w), B.GREENHILL ** (1 / 3))


def test_euler_tip_cantilever():
    E, I, h = 200e9, 1e-8, 2.0
    P_cr = math.pi**2 * E * I / (4 * h**2)
    assert math.isclose(B.euler_tip_lambda(E, I, P_cr, h), 1.0)
    assert B.euler_tip_lambda(E, I, 0.0, h) == math.inf


def test_combined_reduces_to_limits():
    E, I, w, h = 200e9, 1e-8, 5.0, 2.0
    # P = 0 -> pure Greenhill
    assert math.isclose(
        B.combined_lambda(E, I, w, 0.0, h), B.greenhill_lambda(E, I, w, h)
    )
    # w = 0 -> pure Euler
    assert math.isclose(
        B.combined_lambda(E, I, 0.0, 100.0, h), B.euler_tip_lambda(E, I, 100.0, h)
    )


def test_dunkerley_is_conservative():
    E, I, w, P, h = 200e9, 1e-8, 5.0, 100.0, 2.0
    lam = B.combined_lambda(E, I, w, P, h)
    ls = B.greenhill_lambda(E, I, w, h)
    le = B.euler_tip_lambda(E, I, P, h)
    assert lam <= min(ls, le) + 1e-12


def test_amplification_factor():
    assert math.isclose(B.amplification_factor(2.0), 2.0)
    assert math.isclose(B.amplification_factor(3.0), 1.5)
    assert B.amplification_factor(1.0) == math.inf
    assert B.amplification_factor(0.5) == math.inf
