"""The experiments assert their own invariants; run them as tests."""

import random

import pytest

from declpkg.experiments.coordination import sweep
from declpkg.experiments.resolve import DesiredManifest, resolve_view, satisfies
from declpkg.experiments.run import (
    exp_a_store_is_conflict_free,
    exp_b_views_solve_venv,
    exp_c_coordination_cost,
    exp_d_gc_needs_coordination,
)
from declpkg.experiments.store import Store, StoreKey


def test_experiment_a():
    exp_a_store_is_conflict_free()


def test_experiment_b():
    exp_b_views_solve_venv()


def test_experiment_c():
    exp_c_coordination_cost()


def test_experiment_d():
    exp_d_gc_needs_coordination()


def test_store_union_order_independent():
    keys = [StoreKey("pip", "numpy", v) for v in ("1.0", "2.0", "1.0", "3.0")]
    rng = random.Random(0)
    sizes = set()
    for _ in range(20):
        order = keys[:]
        rng.shuffle(order)
        s = Store()
        for k in order:
            s.add(k)
        sizes.add(len(s))
    assert sizes == {3}, "union is commutative + idempotent regardless of order"


def test_conflicting_versions_get_distinct_paths():
    a = StoreKey("pip", "numpy", "1.26.4")
    b = StoreKey("pip", "numpy", "2.0.1")
    assert a.content_path() != b.content_path()
    # identical keys are interchangeable -> same path
    assert a.content_path() == StoreKey("pip", "numpy", "1.26.4").content_path()


def test_satisfies_constraints():
    assert satisfies("1.26.4", ">=1.24,<2")
    assert not satisfies("2.0.1", ">=1.24,<2")
    assert satisfies("2.1.0", ">=2.0")
    assert satisfies("2.31.0", "2.31")          # bare prefix match
    assert not satisfies("2.30.0", "==2.31.0")


def test_gset_pays_zero_coordination_at_every_contention():
    rows = sweep(n_agents=12, key_counts=[48, 12, 1], trials=100)
    assert all(r["gset_cost"] == 0.0 for r in rows)
    # OCC cost strictly increases as keys shrink (contention rises)
    occ = [r["occ_retries"] for r in rows]
    assert occ[0] < occ[-1]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
