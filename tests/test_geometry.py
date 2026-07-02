import math

from post_opt.physics import geometry as G


def test_section_properties():
    g = G.TwoCylinder(r=0.01, h=1.0, D=0.4, t=0.002)
    assert math.isclose(g.area, math.pi * 0.01**2)
    assert math.isclose(g.I, math.pi * 0.01**4 / 4)
    assert math.isclose(g.J, math.pi * 0.01**4 / 2)
    assert math.isclose(g.section_modulus, math.pi * 0.01**3 / 4)
    assert g.plate_radius == 0.2


def test_volumes_and_weight():
    g = G.TwoCylinder(r=0.01, h=1.0, D=0.4, t=0.002)
    shaft = math.pi * 0.01**2 * 1.0
    plate = math.pi * 0.2**2 * 0.002
    assert math.isclose(g.shaft_volume, shaft)
    assert math.isclose(g.plate_volume, plate)
    assert math.isclose(g.volume, shaft + plate)
    rho, gg = 7850.0, 9.81
    assert math.isclose(G.total_weight(g, rho, gg), rho * gg * (shaft + plate))
    assert math.isclose(G.weight_per_length(g, rho, gg), rho * gg * g.area)
