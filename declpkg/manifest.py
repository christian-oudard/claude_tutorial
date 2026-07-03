"""The concrete manifest format and the CRDT-backed replica that holds it.

A manifest is a set of packages, each declared as::

    [packages.<name>]
    ecosystem = "pip" | "npm" | "cargo" | "lake" | "cabal" | ...
    version   = ">=2.31,<3"        # optional; a version or constraint
    source    = "https://..."      # optional; e.g. a git/flake ref

Underneath, the manifest is not a plain dict -- it is a composition of the
CRDTs in ``crdt.py`` so two machines can each edit it offline and merge:

  * membership  -> ORSWOT   (installed set, add-wins)
  * version     -> MVRegister (concurrent edits surface as a conflict)
  * source      -> LWWRegister
  * ecosystem   -> LWWRegister (effectively immutable per package)

A ``Replica`` is one machine's copy. It owns a replica id and a Lamport
clock, exposes intent-level operations (install / uninstall / set_version /
set_source), and can ``merge`` another replica's state.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .crdt import LWWRegister, MVRegister, ORSWOT, VersionVector

CONFLICT = "<<CONFLICT>>"


@dataclass
class ResolvedPackage:
    """A flattened, human-facing view of one package after CRDT resolution."""

    name: str
    ecosystem: str
    version: str | None            # None if unset; set only when unambiguous
    version_candidates: list[str]  # >1 means an unresolved version conflict
    source: str | None
    installed: bool

    @property
    def conflicted(self) -> bool:
        return len(self.version_candidates) > 1


class Replica:
    def __init__(self, replica_id: str) -> None:
        self.replica_id = replica_id
        self.lamport = 0
        self.members = ORSWOT()
        self.version: dict[str, MVRegister] = {}
        self.source: dict[str, LWWRegister] = {}
        self.ecosystem: dict[str, LWWRegister] = {}

    # -- clock -----------------------------------------------------------
    def _tick(self) -> int:
        self.lamport += 1
        return self.lamport

    # -- intent-level operations ----------------------------------------
    def install(self, name: str, ecosystem: str,
                version: str | None = None, source: str | None = None) -> None:
        self.members.add(name, self.replica_id)
        self.ecosystem.setdefault(name, LWWRegister()).write(
            ecosystem, self._tick(), self.replica_id)
        if version is not None:
            self.set_version(name, version)
        if source is not None:
            self.set_source(name, source)

    def uninstall(self, name: str) -> None:
        self.members.remove(name)

    def set_version(self, name: str, version: str) -> None:
        reg = self.version.setdefault(name, MVRegister())
        reg.write(version, self.members.context, self.replica_id)

    def resolve_version(self, name: str, version: str) -> None:
        reg = self.version.setdefault(name, MVRegister())
        reg.resolve(version, self.members.context, self.replica_id)

    def set_source(self, name: str, source: str) -> None:
        self.source.setdefault(name, LWWRegister()).write(
            source, self._tick(), self.replica_id)

    # -- resolved view ---------------------------------------------------
    def resolved(self) -> dict[str, ResolvedPackage]:
        out: dict[str, ResolvedPackage] = {}
        for name in sorted(self.members.elements()):
            vreg = self.version.get(name)
            candidates = vreg.values() if vreg else []
            eco = self.ecosystem.get(name)
            src = self.source.get(name)
            out[name] = ResolvedPackage(
                name=name,
                ecosystem=eco.value if eco and eco.value else "unknown",
                version=(candidates[0] if len(candidates) == 1 else None),
                version_candidates=candidates,
                source=src.value if src else None,
                installed=True,
            )
        return out

    def conflicts(self) -> dict[str, list[str]]:
        return {n: p.version_candidates for n, p in self.resolved().items() if p.conflicted}

    # -- merge -----------------------------------------------------------
    def merge(self, other: "Replica") -> None:
        self.members = self.members.merge(other.members)
        self.lamport = max(self.lamport, other.lamport)
        for name, reg in other.version.items():
            self.version[name] = self.version.get(name, MVRegister()).merge(reg)
        for name, reg in other.source.items():
            self.source[name] = self.source.get(name, LWWRegister()).merge(reg)
        for name, reg in other.ecosystem.items():
            self.ecosystem[name] = self.ecosystem.get(name, LWWRegister()).merge(reg)

    # -- persistence -----------------------------------------------------
    def to_json(self) -> dict[str, Any]:
        return {
            "replica_id": self.replica_id,
            "lamport": self.lamport,
            "members": self.members.to_json(),
            "version": {k: v.to_json() for k, v in self.version.items()},
            "source": {k: v.to_json() for k, v in self.source.items()},
            "ecosystem": {k: v.to_json() for k, v in self.ecosystem.items()},
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Replica":
        r = cls(data["replica_id"])
        r.lamport = int(data.get("lamport", 0))
        r.members = ORSWOT.from_json(data["members"])
        r.version = {k: MVRegister.from_json(v) for k, v in data.get("version", {}).items()}
        r.source = {k: LWWRegister.from_json(v) for k, v in data.get("source", {}).items()}
        r.ecosystem = {k: LWWRegister.from_json(v) for k, v in data.get("ecosystem", {}).items()}
        return r

    def save(self, path: str) -> None:
        with open(path, "w") as fh:
            json.dump(self.to_json(), fh, indent=2, sort_keys=True)

    @classmethod
    def load(cls, path: str) -> "Replica":
        with open(path) as fh:
            return cls.from_json(json.load(fh))


def load_toml_manifest(path: str, replica: Replica) -> Replica:
    """Import a declarative ``manifest.toml`` into ``replica`` (installs all)."""
    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:  # pragma: no cover
        raise RuntimeError("tomllib not available; needs Python 3.11+")
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    for name, spec in (data.get("packages") or {}).items():
        replica.install(
            name,
            ecosystem=spec["ecosystem"],
            version=spec.get("version"),
            source=spec.get("source"),
        )
    return replica
