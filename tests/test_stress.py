import math

from post_opt.physics import stress as S


def test_normal_stress_pure_bending():
    # N = 0: sigma = M / S with S = pi r^3 / 4
    r = 0.01
    S_mod = math.pi * r**3 / 4
    M = 5.0
    assert math.isclose(S.normal_stress(0.0, M, math.pi * r**2, S_mod), M / S_mod)


def test_normal_stress_axial_plus_bending():
    A, Smod = 2.0, 4.0
    assert math.isclose(S.normal_stress(6.0, 8.0, A, Smod), 6.0 / 2.0 + 8.0 / 4.0)


def test_transverse_shear_solid_circle_factor():
    # peak = 4/3 * V/A for a solid circle
    assert math.isclose(S.transverse_shear_stress(3.0, 2.0), 4.0 * 3.0 / (3.0 * 2.0))


def test_torsion_stress():
    r, J, T = 0.01, math.pi * 0.01**4 / 2, 2.0
    assert math.isclose(S.torsion_stress(T, r, J), T * r / J)
    assert S.torsion_stress(0.0, r, J) == 0.0


def test_shear_yield_von_mises():
    assert math.isclose(S.shear_yield(300.0), 300.0 / math.sqrt(3.0))


def test_punching_shear():
    r, t, V = 0.01, 0.002, 100.0
    assert math.isclose(S.punching_shear_stress(V, r, t), V / (2 * math.pi * r * t))


def test_plate_bending_stress():
    q, a, r, t = 1000.0, 0.2, 0.01, 0.002
    expect = 3.0 * q * (a - r) ** 2 / t**2
    assert math.isclose(S.plate_bending_stress(q, a, r, t), expect)
