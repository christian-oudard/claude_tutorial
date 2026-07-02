"""M1 acceptance: v1 two-cylinder regression baseline.

Per the spec, M1 "reproduces v1 numbers when deflection is disabled and kern
mode is on ... tolerance 1%".  Because this repository defines the canonical v1
model, the table below is the locked baseline: every optimum was produced with
``deflection=False`` and ``conservative=True`` (kern overturning).  Any future
milestone (M2+) that changes the two-cylinder result by more than 1% must
update this table deliberately.

Run directly (``python tests/v1_regression.py``) to regenerate the table.
"""

from __future__ import annotations

import pytest

from post_opt import PostConfig, PostOptimizer
from post_opt.config import Loads

# (M, F) -> locked v1 optimum. Numbers frozen from the reference implementation.
CASES = [
    dict(M=0.5, F=0.5, H=0.489718, r=2.361421e-03, D=0.399362,
         active=["overturning"]),
    dict(M=1.0, F=0.1, H=3.121378, r=3.457288e-03, D=0.254547,
         active=["overturning", "buckling"]),
    dict(M=1.0, F=1.0, H=0.617006, r=6.723293e-03, D=0.503165,
         active=["overturning"]),
    dict(M=1.0, F=5.0, H=0.123401, r=1.035203e-02, D=0.503165,
         active=["overturning"]),
    dict(M=2.0, F=1.0, H=1.554757, r=5.015137e-03, D=0.633948,
         active=["overturning"]),
    dict(M=5.0, F=2.0, H=2.637781, r=6.649720e-03, D=0.860399,
         active=["overturning"]),
]

TOL = 0.01  # 1% per the acceptance criterion


def _solve(M: float, F: float):
    cfg = PostConfig(mass=M, loads=Loads(F=F), conservative=True, deflection=False)
    return PostOptimizer(cfg).optimize()


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"M{c['M']}_F{c['F']}")
def test_v1_regression(case):
    res = _solve(case["M"], case["F"])
    assert res.success
    ev = res.evaluation
    assert res.H == pytest.approx(case["H"], rel=TOL)
    assert ev.geom.r == pytest.approx(case["r"], rel=TOL)
    assert ev.geom.D == pytest.approx(case["D"], rel=TOL)
    # overturning (tipping) governs the base size for these light posts
    assert "overturning" in ev.active_set()


def test_volume_budget_is_exact():
    res = _solve(1.0, 1.0)
    ev = res.evaluation
    assert ev.volume == pytest.approx(res.evaluation.geom.volume, rel=1e-9)
    cfg = PostConfig(mass=1.0)
    assert ev.volume == pytest.approx(cfg.volume, rel=1e-6)


if __name__ == "__main__":
    for M, F in [(c["M"], c["F"]) for c in CASES]:
        res = _solve(M, F)
        ev = res.evaluation
        g = ev.geom
        print(
            f"    dict(M={M}, F={F}, H={res.H:.6f}, r={g.r:.6e}, "
            f"D={g.D:.6f}, active={ev.active_set()!r}),"
        )
