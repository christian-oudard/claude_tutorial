"""Regression tests for the known physical regimes the spec calls out."""

from __future__ import annotations

import math

import pytest

from post_opt import PostConfig, PostOptimizer
from post_opt.config import Loads


def test_bearing_inactive_by_orders_at_1kg():
    # "bearing is inactive by ~3 orders of magnitude at M = 1 kg"
    cfg = PostConfig(mass=1.0, loads=Loads(F=1.0))
    ev = PostOptimizer(cfg).optimize().evaluation
    assert ev.margins["bearing"] > 0.99  # far from binding


def test_tipping_governs_base_for_light_post():
    cfg = PostConfig(mass=1.0, loads=Loads(F=2.0))
    ev = PostOptimizer(cfg).optimize().evaluation
    assert "overturning" in ev.active_set()


def test_low_F_is_self_weight_buckling_limited():
    # With no lateral load the height ceiling is self-weight buckling.
    cfg = PostConfig(mass=1.0, loads=Loads(F=0.0))
    ev = PostOptimizer(cfg).optimize().evaluation
    assert "buckling" in ev.active_set()
    assert ev.lam_buckle == pytest.approx(cfg.safety.buckling_SF, rel=1e-3)


def test_high_F_kern_relation():
    # h ~= D * W / (8 F) under the kern model at high F
    F = 20.0
    cfg = PostConfig(mass=1.0, loads=Loads(F=F), conservative=True, deflection=False)
    ev = PostOptimizer(cfg).optimize().evaluation
    W = ev.N_soil  # P = 0
    predicted = ev.geom.D * W / (8 * F)
    assert ev.geom.h == pytest.approx(predicted, rel=0.02)


def test_deflection_shrinks_height():
    # Enabling the P-delta deflection constraint reduces achievable height.
    common = dict(mass=1.0, loads=Loads(F=2.0), conservative=True)
    h_no = PostOptimizer(PostConfig(**common, deflection=False)).optimize().H
    h_yes = PostOptimizer(PostConfig(**common, deflection=True)).optimize().H
    assert h_yes <= h_no + 1e-9


def test_partial_uplift_beats_kern_height():
    # The (correct) partial-uplift model permits a taller post than the
    # conservative kern model at the same mass and load.
    common = dict(mass=1.0, loads=Loads(F=3.0), deflection=False)
    h_kern = PostOptimizer(PostConfig(**common, conservative=True)).optimize().H
    h_pu = PostOptimizer(PostConfig(**common, conservative=False)).optimize().H
    assert h_pu >= h_kern
