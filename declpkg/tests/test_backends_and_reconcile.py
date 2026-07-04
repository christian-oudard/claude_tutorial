"""Backend command/native rendering + declarative reconciliation."""

import os
import tempfile

import pytest

from declpkg.backends import Package, get_backend, known_ecosystems
from declpkg.generate import generate
from declpkg.manifest import Replica
from declpkg.reconcile import apply, plan


def test_all_ecosystems_registered():
    assert set(known_ecosystems()) == {"pip", "npm", "cargo", "lake", "cabal"}


def test_pip_spec_rendering():
    b = get_backend("pip")
    assert b.install_cmd(Package("requests", "pip", ">=2.31,<3")) == \
        ["pip", "install", "requests>=2.31,<3"]
    # bare version -> exact pin
    assert b.install_cmd(Package("flask", "pip", "3.0.0")) == \
        ["pip", "install", "flask==3.0.0"]
    assert b.install_cmd(Package("numpy", "pip")) == ["pip", "install", "numpy"]


def test_npm_and_cargo_and_cabal_cmds():
    assert get_backend("npm").install_cmd(Package("left-pad", "npm", "1.3.0")) == \
        ["npm", "install", "left-pad@1.3.0"]
    assert get_backend("cargo").remove_cmd(Package("serde", "cargo")) == \
        ["cargo", "remove", "serde"]
    assert get_backend("cabal").install_cmd(Package("aeson", "cabal", "2.2")) == \
        ["cabal", "install", "--lib", "aeson-2.2"]


def test_lake_git_source_native():
    text = get_backend("lake").render_native(
        [Package("mathlib", "lake", "v4.7.0", "https://git/mathlib4")])
    assert "[[require]]" in text
    assert 'git = "https://git/mathlib4"' in text
    assert 'rev = "v4.7.0"' in text


def test_generate_is_deterministic_and_covers_ecosystems():
    r = Replica("a")
    r.install("requests", "pip", version=">=2.31")
    r.install("left-pad", "npm", version="1.3.0")
    r.install("serde", "cargo", version="1.0")
    files1 = generate(r)
    files2 = generate(r)
    assert files1 == files2  # deterministic
    assert set(files1) == {"requirements.txt", "package.json", "Cargo.toml"}


def test_generate_skips_conflicted_package():
    import copy
    base = Replica("a")
    base.install("requests", "pip", version=">=2.31")
    laptop = Replica.from_json(copy.deepcopy(base.to_json())); laptop.replica_id = "l"
    server = Replica.from_json(copy.deepcopy(base.to_json())); server.replica_id = "s"
    laptop.set_version("requests", ">=2.32")
    server.set_version("requests", "==2.31.4")
    laptop.merge(server)
    # conflicted requests is the only pip pkg, so no requirements.txt at all --
    # a half-resolved spec must never leak into generated output.
    assert "requirements.txt" not in generate(laptop)


def test_reconcile_install_upgrade_remove_cycle():
    with tempfile.TemporaryDirectory() as d:
        applied = os.path.join(d, "applied.json")
        r = Replica("a")
        r.install("requests", "pip", version=">=2.31")

        p = plan(r, applied)
        assert [a.kind for a in p.actions] == ["INSTALL"]
        apply(r, applied)                       # record state
        assert plan(r, applied).empty           # idempotent

        r.set_version("requests", ">=2.32")     # change -> upgrade
        assert [a.kind for a in plan(r, applied).actions] == ["UPGRADE"]
        apply(r, applied)

        r.uninstall("requests")                 # gone -> remove
        assert [a.kind for a in plan(r, applied).actions] == ["REMOVE"]
        apply(r, applied)
        assert plan(r, applied).empty


def test_reconcile_refuses_apply_while_conflicted():
    import copy
    with tempfile.TemporaryDirectory() as d:
        applied = os.path.join(d, "applied.json")
        base = Replica("a")
        base.install("requests", "pip", version=">=2.31")
        laptop = Replica.from_json(copy.deepcopy(base.to_json())); laptop.replica_id = "l"
        server = Replica.from_json(copy.deepcopy(base.to_json())); server.replica_id = "s"
        laptop.set_version("requests", ">=2.32")
        server.set_version("requests", "==2.31.4")
        laptop.merge(server)

        p = apply(laptop, applied)
        assert p.conflicts                       # aborted
        assert not os.path.exists(applied)       # nothing written


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
