import math

from post_opt.physics import overturning as O


def test_kern_capacity():
    assert math.isclose(O.kern_capacity(100.0, 0.4), 100.0 * 0.4 / 8)


def test_segment_area_half_disc():
    a = 0.5
    # chord through the centre -> half disc
    assert math.isclose(O._segment_area(0.0, a), math.pi * a**2 / 2)
    # chord at the rim -> zero area
    assert math.isclose(O._segment_area(a, a), 0.0, abs_tol=1e-12)


def test_partial_uplift_half_disc_centroid():
    # Choose N so the contact area is exactly half the plate: A_c = pi a^2 / 2
    a = 0.5
    D = 2 * a
    q = 1000.0
    N = q * (math.pi * a**2 / 2)
    M_cap, A_c = O.partial_uplift_capacity(N, D, q)
    # centroid distance of a half disc is 4a/(3 pi); M_cap = N * d_c
    d_c = M_cap / N
    assert math.isclose(d_c, 4 * a / (3 * math.pi), rel_tol=1e-6)
    assert math.isclose(A_c, math.pi * a**2 / 2, rel_tol=1e-9)


def test_partial_uplift_exhausted_when_area_too_large():
    a = 0.5
    D = 2 * a
    q = 1000.0
    N = q * math.pi * a**2 * 1.01  # needs more area than the plate has
    M_cap, A_c = O.partial_uplift_capacity(N, D, q)
    assert M_cap == 0.0


def test_partial_uplift_ge_kern_for_light_load():
    # partial-uplift (plastic) capacity exceeds the elastic kern limit
    D, q = 0.4, 150e3
    N = 20.0
    M_pu, _ = O.partial_uplift_capacity(N, D, q)
    M_kern = O.kern_capacity(N, D)
    assert M_pu > M_kern


def test_overturning_selects_model():
    r_pu = O.overturning(50.0, 1.0, 0.4, 150e3, conservative=False)
    r_kern = O.overturning(50.0, 1.0, 0.4, 150e3, conservative=True)
    assert r_pu.model == "partial_uplift"
    assert r_kern.model == "kern"
    assert math.isclose(r_kern.M_cap, 50.0 * 0.4 / 8)
