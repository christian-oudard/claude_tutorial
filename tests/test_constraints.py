import math

from post_opt import constraints as C


def test_margin_signs():
    assert C.margin_yield(100.0, 200.0) > 0  # safe
    assert C.margin_yield(300.0, 200.0) < 0  # yielded
    assert math.isclose(C.margin_yield(200.0, 200.0), 0.0)  # binding


def test_margin_buckling():
    assert math.isclose(C.margin_buckling(2.0, 2.0), 0.0)
    assert C.margin_buckling(4.0, 2.0) > 0
    assert C.margin_buckling(1.0, 2.0) < 0
    assert C.margin_buckling(math.inf, 2.0) > 0


def test_margin_overturning_collapse():
    assert C.margin_overturning(1.0, 0.0) < 0  # zero capacity -> violated
    assert math.isclose(C.margin_overturning(1.0, 2.0), 0.5)


def test_margin_deflection():
    # delta/H = 0.01, eps = 0.02 -> margin 0.5
    assert math.isclose(C.margin_deflection(0.01, 1.0, 0.02), 0.5)
    assert C.margin_deflection(math.inf, 1.0, 0.02) < 0


def test_margin_bearing_and_shear_and_punching():
    assert math.isclose(C.margin_bearing(75e3, 150e3), 0.5)
    assert math.isclose(C.margin_shear(50.0, 100.0), 0.5)
    assert math.isclose(C.margin_punching(50.0, 100.0), 0.5)
    assert math.isclose(C.margin_plate_bending(50.0, 100.0), 0.5)
