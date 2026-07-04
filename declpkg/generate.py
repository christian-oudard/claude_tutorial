"""Deterministic generation of each ecosystem's native spec file.

This is the declarative, Nix-like half: the manifest is the single source
of truth, and every ecosystem's native file is a pure function of it. The
generated files diff cleanly in git even though the CRDT state itself
(binary-ish, causal metadata) does not -- so you commit the *generated*
artifacts for review and let the merge happen in the CRDT layer.
"""

from __future__ import annotations

import os
from collections import defaultdict

from .backends import Package, get_backend
from .manifest import Replica


def resolved_packages(replica: Replica, *, skip_conflicted: bool = True) -> list[Package]:
    pkgs: list[Package] = []
    for p in replica.resolved().values():
        if p.conflicted and skip_conflicted:
            continue
        pkgs.append(Package(p.name, p.ecosystem, p.version, p.source))
    return pkgs


def generate(replica: Replica) -> dict[str, str]:
    """Return ``{native_file: contents}`` for every ecosystem in use."""
    by_eco: dict[str, list[Package]] = defaultdict(list)
    for pkg in resolved_packages(replica):
        by_eco[pkg.ecosystem].append(pkg)

    out: dict[str, str] = {}
    for eco, pkgs in by_eco.items():
        backend = get_backend(eco)
        out[backend.native_file] = backend.render_native(pkgs)
    return out


def write_generated(replica: Replica, out_dir: str) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    written: list[str] = []
    for filename, contents in generate(replica).items():
        path = os.path.join(out_dir, filename)
        with open(path, "w") as fh:
            fh.write(contents)
        written.append(path)
    return sorted(written)
