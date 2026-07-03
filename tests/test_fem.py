"""FEM engine checks against analytic beam-column results."""

from __future__ import annotations

import math

import numpy as np
import pytest

from post_opt import fem


def _uniform(r):
    return lambda z: r * np.ones_like(np.asarray(z, dtype=float))


def test_greenhill_self_weight_buckling_within_1pct():
    E, r, rho_g = 200e9, 0.01, 7850 * 9.81
    I = math.pi * r**4 / 4
    w = rho_g * math.pi * r**2
    H = 1.0
    mesh = fem.build_mesh(H, _uniform(r), E, rho_g, 40)
    K, KG, _ = fem.assemble(mesh, 0.0)
    lam = fem.buckling_factor(K, KG, 40)
    analytic = fem.GREENHILL * E * I / (w * H**3) if False else 7.8373 * E * I / (w * H**3)
    assert abs(lam - analytic) / analytic < 0.01


def test_euler_tip_load_exact():
    E, r = 200e9, 0.01
    I = math.pi * r**4 / 4
    H = 2.0
    mesh = fem.build_mesh(H, _uniform(r), E, 0.0, 60)  # no self weight
    K, KG, _ = fem.assemble(mesh, 1.0)  # unit tip load
    lam = fem.buckling_factor(K, KG, 60)
    P_cr = math.pi**2 * E * I / (4 * H**2)
    assert lam == pytest.approx(P_cr, rel=1e-3)


def test_moment_first_order_is_tip_cantilever():
    mesh = fem.build_mesh(3.0, _uniform(0.01), 200e9, 0.0, 20)
    M = fem.bending_moment(mesh, np.zeros(21), F=5.0, P=0.0)
    expected = 5.0 * (3.0 - mesh.z_nodes)
    assert np.allclose(M, expected)


def test_cantilever_tip_deflection_first_order():
    # (K - K_G) with no axial load -> ordinary cantilever F h^3 / (3 E I)
    E, r, F, H = 200e9, 0.02, 10.0, 2.0
    I = math.pi * r**4 / 4
    mesh = fem.build_mesh(H, _uniform(r), E, 0.0, 60)
    K, KG, _ = fem.assemble(mesh, 0.0)
    w = fem.deflection(K, KG, mesh, F)
    analytic = F * H**3 / (3 * E * I)
    assert abs(w[-1]) == pytest.approx(analytic, rel=1e-3)
