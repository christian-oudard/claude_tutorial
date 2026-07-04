"""A grow-only, content-addressed, refcounted package store (the Nix insight).

Keyed by (ecosystem, name, version, platform), so numpy 1.26 and numpy 2.0
are *different entries that coexist permanently*. Adding one when the other
exists is not a conflict -- it's a union. That makes the store the one place
a CRDT is actually justified, and the trivial one: a G-Set (grow-only set).
``merge`` is literally dict union; ``add`` is idempotent.

Refcounts track which store paths are still referenced by some agent's view,
so unreferenced paths can be garbage-collected later -- the only operation
that genuinely needs coordination (see experiments/coordination.py).
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class StoreKey:
    ecosystem: str
    name: str
    version: str
    platform: str = "any"

    def __str__(self) -> str:
        return f"{self.ecosystem}:{self.name}@{self.version}:{self.platform}"

    def content_path(self) -> str:
        """Content-addressed path -- interchangeable iff keys are equal."""
        digest = hashlib.sha1(str(self).encode()).hexdigest()[:12]
        return f"/store/{self.name}-{self.version}-{digest}"


class Store:
    def __init__(self) -> None:
        self._paths: dict[str, StoreKey] = {}   # content_path -> key
        self._rc: Counter[str] = Counter()       # content_path -> refcount

    # -- grow-only union (the G-Set) ------------------------------------
    def add(self, key: StoreKey) -> str:
        """Insert (idempotent). Returns the content path. Never conflicts."""
        path = key.content_path()
        self._paths.setdefault(path, key)
        return path

    def merge(self, other: "Store") -> None:
        """Union with another replica of the store. Commutative, idempotent."""
        for path, key in other._paths.items():
            self._paths.setdefault(path, key)

    def contains(self, key: StoreKey) -> bool:
        return key.content_path() in self._paths

    def keys(self) -> list[StoreKey]:
        return list(self._paths.values())

    def available_versions(self, ecosystem: str, name: str) -> list[str]:
        return sorted(
            k.version for k in self._paths.values()
            if k.ecosystem == ecosystem and k.name == name
        )

    # -- refcounting (for GC) -------------------------------------------
    def acquire(self, key: StoreKey) -> str:
        path = self.add(key)
        self._rc[path] += 1
        return path

    def release(self, key: StoreKey) -> None:
        path = key.content_path()
        if self._rc[path] > 0:
            self._rc[path] -= 1

    def refcount(self, key: StoreKey) -> int:
        return self._rc[key.content_path()]

    def gc(self) -> list[str]:
        """Remove entries no view references. Returns collected paths."""
        dead = [p for p in self._paths if self._rc[p] == 0]
        for p in dead:
            del self._paths[p]
            self._rc.pop(p, None)
        return sorted(dead)

    def __len__(self) -> int:
        return len(self._paths)
