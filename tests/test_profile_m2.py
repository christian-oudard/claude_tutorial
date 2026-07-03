"""M2 acceptance: free-profile optimizer recovers the analytic shape limits."""

from __future__ import annotations

import numpy as np
import pytest

from post_opt import PostConfig
from post_opt.config import Loads, Profile, Soil
from post_opt.profile_optimize import ProfileOptimizer


def test_cube_root_taper_interior_within_3pct():
    # P = 0, deflection & buckling disabled, overturning slack -> yield governs
    # the shaft shape, which must be the cube-root taper r^3 ∝ F (H - z).
    cfg = PostConfig(
        loads=Loads(F=1.0), buckling=False, deflection=False,
        soil=Soil(q_allow=1e10), profile=Profile(n_control=20, nel=40),
    )
    ev = ProfileOptimizer(cfg).optimize().evaluation
    r, xi, H = ev.radii, ev.xi, ev.H
    pred = H * (1.0 - xi)
    mask = (xi > 0.1) & (xi < 0.9)  # interior nodes (tip cusp excluded)
    scale = np.mean(r[mask] ** 3 / pred[mask])
    r_pred = (scale * pred) ** (1.0 / 3.0)
    err = np.abs(r[mask] - r_pred[mask]) / r_pred[mask]
    assert err.max() < 0.03
    assert ev.sigma_max == pytest.approx(1.0, abs=0.02)  # fully stressed


def test_constant_radius_axial_dominated():
    # F = 0, P > 0 (axial dominant) -> uniform radius.
    cfg = PostConfig(
        loads=Loads(F=0.0, P=2000.0), buckling=False, deflection=False,
        soil=Soil(q_allow=1e10), profile=Profile(n_control=20, nel=40),
    )
    ev = ProfileOptimizer(cfg).optimize().evaluation
    r = ev.radii
    assert r.std() / r.mean() < 0.02  # < 2% variation


def test_optimize_feasible_with_buckling_and_deflection():
    # Realistic run: all constraints on; result must be fully feasible with a
    # hard per-node yield check, and deflection at or under the limit.
    cfg = PostConfig(
        loads=Loads(F=1.0), buckling=True, deflection=True,
        profile=Profile(n_control=16, nel=32),
    )
    res = ProfileOptimizer(cfg).optimize()
    assert res.success
    ev = res.evaluation
    assert ev.sigma_max <= 1.0 + 1e-2
    assert (ev.delta_tip / ev.H) <= cfg.safety.defl_ratio + 1e-6
    assert ev.lam_buckle >= cfg.safety.buckling_SF - 1e-6
    assert ev.min_margin() >= -cfg.solver.feas_tol


def test_high_F_second_order_moment_regression():
    # Regression: with buckling+deflection on, the second-order moment can dip
    # slightly negative near the tip; the FSD radius solve must size on the
    # magnitude and not fail its root bracket.
    cfg = PostConfig(
        loads=Loads(F=10.0), buckling=True, deflection=True,
        profile=Profile(n_control=16, nel=32),
    )
    res = ProfileOptimizer(cfg).optimize()
    assert res.success
    assert res.evaluation.sigma_max <= 1.0 + 1e-2


def test_taller_than_two_cylinder_equal_mass():
    # A shaped profile should stand at least as tall as the crude two-cylinder
    # at equal mass and load (same constraints).
    from post_opt import PostOptimizer

    loads = Loads(F=1.0)
    cyl = PostOptimizer(PostConfig(loads=loads)).optimize().H
    prof = ProfileOptimizer(
        PostConfig(loads=loads, profile=Profile(n_control=16, nel=32))
    ).optimize().H
    assert prof >= cyl * 0.98
