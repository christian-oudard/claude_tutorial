"""Manifest replica: merge, conflict surfacing, persistence."""

import copy

import pytest

from declpkg.manifest import Replica


def _fork(r: Replica, new_id: str) -> Replica:
    other = Replica.from_json(copy.deepcopy(r.to_json()))
    other.replica_id = new_id
    return other


def test_install_and_resolved_view():
    r = Replica("a")
    r.install("requests", "pip", version=">=2.31")
    r.install("serde", "cargo", version="1.0", source=None)
    view = r.resolved()
    assert view["requests"].ecosystem == "pip"
    assert view["requests"].version == ">=2.31"
    assert view["serde"].ecosystem == "cargo"


def test_concurrent_version_edit_surfaces_conflict():
    base = Replica("a")
    base.install("requests", "pip", version=">=2.31")
    laptop = _fork(base, "laptop")
    server = _fork(base, "server")

    laptop.set_version("requests", ">=2.32")
    server.set_version("requests", "==2.31.4")
    laptop.merge(server)

    assert laptop.conflicts() == {"requests": ["==2.31.4", ">=2.32"]}
    assert laptop.resolved()["requests"].version is None  # ambiguous


def test_resolve_clears_conflict():
    base = Replica("a")
    base.install("requests", "pip", version=">=2.31")
    laptop, server = _fork(base, "laptop"), _fork(base, "server")
    laptop.set_version("requests", ">=2.32")
    server.set_version("requests", "==2.31.4")
    laptop.merge(server)

    laptop.resolve_version("requests", ">=2.32")
    assert laptop.conflicts() == {}
    assert laptop.resolved()["requests"].version == ">=2.32"


def test_uninstall_add_wins_on_merge():
    base = Replica("a")
    base.install("left-pad", "npm", version="1.3.0")
    laptop, server = _fork(base, "laptop"), _fork(base, "server")

    laptop.uninstall("left-pad")
    server.set_version("left-pad", "1.3.1")  # concurrent edit implies keep
    server.members.add("left-pad", "server")  # server re-touches membership
    laptop.merge(server)

    assert "left-pad" in laptop.resolved()  # add wins


def test_merge_is_symmetric():
    a = Replica("a"); a.install("x", "pip", version="1")
    b = Replica("b"); b.install("y", "npm", version="2")
    a2, b2 = _fork(a, "a"), _fork(b, "b")
    a.merge(b)
    b2.merge(a2)
    assert set(a.resolved()) == set(b2.resolved()) == {"x", "y"}


def test_roundtrip_serialization():
    r = Replica("a")
    r.install("requests", "pip", version=">=2.31")
    r.install("mathlib", "lake", source="https://example/git", version="v1")
    clone = Replica.from_json(r.to_json())
    assert clone.resolved().keys() == r.resolved().keys()
    assert clone.resolved()["mathlib"].source == "https://example/git"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
