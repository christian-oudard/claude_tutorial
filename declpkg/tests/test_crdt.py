"""CRDT property + semantics tests."""

import copy

import pytest

from declpkg.crdt import LWWRegister, MVRegister, ORSWOT, VersionVector


def test_orswot_add_remove_readd():
    s = ORSWOT()
    s.add("flask", "a")
    assert s.contains("flask")
    s.remove("flask")
    assert not s.contains("flask")
    # re-add after remove must work (no 2P-Set tombstone trap)
    s.add("flask", "a")
    assert s.contains("flask")


def test_orswot_add_wins_on_concurrent_add_remove():
    # Shared history: both know about flask.
    base = ORSWOT()
    base.add("flask", "a")

    laptop = ORSWOT.from_json(copy.deepcopy(base.to_json()))
    server = ORSWOT.from_json(copy.deepcopy(base.to_json()))

    laptop.remove("flask")            # laptop uninstalls
    server.add("flask", "server")     # server concurrently (re)adds

    merged = laptop.merge(server)
    assert merged.contains("flask"), "add must win over a concurrent remove"


def test_orswot_merge_commutative_and_idempotent():
    a = ORSWOT(); a.add("x", "a"); a.add("y", "a")
    b = ORSWOT(); b.add("y", "b"); b.add("z", "b")
    ab = a.merge(b)
    ba = b.merge(a)
    assert ab.elements() == ba.elements() == {"x", "y", "z"}
    # idempotent
    assert ab.merge(ab).elements() == ab.elements()


def test_mvregister_concurrent_writes_conflict():
    laptop = MVRegister()
    server = MVRegister()
    ctx_a = VersionVector()
    ctx_b = VersionVector()
    laptop.write(">=2.32", ctx_a, "a")
    server.write("==2.31.4", ctx_b, "b")

    merged = laptop.merge(server)
    assert merged.is_conflicted()
    assert set(merged.values()) == {">=2.32", "==2.31.4"}


def test_mvregister_sequential_write_no_conflict():
    ctx = VersionVector()
    reg = MVRegister()
    reg.write("1.0", ctx, "a")
    reg.write("2.0", ctx, "a")  # causally after the first
    assert not reg.is_conflicted()
    assert reg.values() == ["2.0"]


def test_mvregister_resolve_collapses_conflict():
    a, b = MVRegister(), MVRegister()
    a.write("x", VersionVector(), "a")
    b.write("y", VersionVector(), "b")
    merged = a.merge(b)
    assert merged.is_conflicted()
    ctx = VersionVector()
    ctx.clocks.update({"a": 1, "b": 1})  # observed both writes
    merged.resolve("x", ctx, "a")
    assert merged.values() == ["x"]


def test_mvregister_merge_commutative():
    a, b = MVRegister(), MVRegister()
    a.write("x", VersionVector(), "a")
    b.write("y", VersionVector(), "b")
    assert set(a.merge(b).values()) == set(b.merge(a).values())


def test_lww_last_writer_wins():
    reg = LWWRegister()
    reg.write("old", 1, "a")
    reg.write("new", 2, "b")
    assert reg.value == "new"
    # lower timestamp ignored
    reg.write("stale", 1, "z")
    assert reg.value == "new"


def test_lww_merge_deterministic_tiebreak():
    a = LWWRegister("a", 5, "aaa")
    b = LWWRegister("b", 5, "bbb")  # same ts, replica breaks tie
    assert a.merge(b).value == b.merge(a).value == "b"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
