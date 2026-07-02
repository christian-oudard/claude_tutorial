import math

from post_opt.physics import deflection as D


def test_first_order_cantilever():
    F, h, E, I = 10.0, 2.0, 200e9, 1e-8
    assert math.isclose(D.first_order_deflection(F, h, E, I), F * h**3 / (3 * E * I))


def test_second_order_amplifies_by_AF():
    F, h, E, I = 10.0, 2.0, 200e9, 1e-8
    delta0 = D.first_order_deflection(F, h, E, I)
    res = D.second_order(F, h, E, I, N=0.0, amplification=2.0, iters=4)
    assert math.isclose(res.delta0, delta0)
    assert math.isclose(res.delta, 2.0 * delta0)


def test_second_order_moment_includes_pdelta():
    # N > 0 pushes the base moment above the first-order F h
    F, h, E, I = 10.0, 2.0, 200e9, 1e-8
    res = D.second_order(F, h, E, I, N=500.0, amplification=1.5, iters=6)
    assert res.moment2 > F * h


def test_unstable_amplification_gives_inf():
    res = D.second_order(10.0, 2.0, 200e9, 1e-8, N=0.0, amplification=math.inf)
    assert res.delta == math.inf
    assert res.moment2 == math.inf
