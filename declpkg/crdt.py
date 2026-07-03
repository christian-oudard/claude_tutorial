"""State-based CRDTs for a cross-ecosystem package manifest.

This module hand-rolls the exact CRDT semantics the manifest needs so the
proof of concept runs with **zero dependencies**:

  * ``ORSWOT``     -- an observed-remove set with *add-wins* semantics, used
                      for package membership ("is this package installed").
                      Concurrent add/remove resolves to *present*, and a
                      package that was removed can always be re-added
                      (no 2P-Set tombstone trap).
  * ``MVRegister`` -- a multi-value register used for ``version``/``pin``.
                      Concurrent writes are *both* retained so the conflict
                      can be surfaced and resolved explicitly, instead of a
                      LWW "latest timestamp wins" that could silently
                      downgrade a pin nobody meant to touch.
  * ``LWWRegister`` -- last-writer-wins register (Lamport clock + replica
                      tiebreak) for fields that are rarely edited
                      concurrently, e.g. ``source``/``ecosystem``.

In production you would swap this file for Automerge, which implements a
JSON CRDT with exactly these semantics (its ``getConflicts`` surfaces the
MVRegister multi-value case) and manages the causal metadata for you. We
implement it directly here to make the semantics legible and testable.

Every CRDT here is a *state-based* (CvRDT) type: ``merge`` is commutative,
associative and idempotent, so replicas converge regardless of message
order or duplication. See ``tests/test_crdt.py`` for property checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

# A dot uniquely tags an event: (replica_id, per-replica counter).
Dot = tuple[str, int]


class VersionVector:
    """Per-replica high-water mark of observed counters.

    Used as the causal *context* for the ORSWOT and MVRegister: it records,
    for each replica, the highest counter this state has observed.
    """

    def __init__(self, clocks: dict[str, int] | None = None) -> None:
        self.clocks: dict[str, int] = dict(clocks or {})

    def next(self, replica: str) -> Dot:
        """Advance ``replica``'s counter and return the fresh dot."""
        self.clocks[replica] = self.clocks.get(replica, 0) + 1
        return (replica, self.clocks[replica])

    def saw(self, dot: Dot) -> bool:
        """Has this context already observed ``dot``?"""
        replica, counter = dot
        return self.clocks.get(replica, 0) >= counter

    def merged(self, other: "VersionVector") -> "VersionVector":
        out = dict(self.clocks)
        for r, c in other.clocks.items():
            out[r] = max(out.get(r, 0), c)
        return VersionVector(out)

    def to_json(self) -> dict[str, int]:
        return dict(self.clocks)

    @classmethod
    def from_json(cls, data: dict[str, int]) -> "VersionVector":
        return cls({k: int(v) for k, v in data.items()})

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"VV({self.clocks})"


class ORSWOT:
    """Observed-Remove Set Without Tombstones (add-wins).

    State is a map ``element -> {dots}`` plus a ``context`` version vector.
    Adding an element mints a fresh dot; removing drops the element's dots
    but leaves the context intact, so a concurrent add (whose dot the
    remover never saw) survives the merge -> *add wins*.
    """

    def __init__(
        self,
        entries: dict[str, set[Dot]] | None = None,
        context: VersionVector | None = None,
    ) -> None:
        self.entries: dict[str, set[Dot]] = {k: set(v) for k, v in (entries or {}).items()}
        self.context: VersionVector = context or VersionVector()

    def add(self, element: str, replica: str) -> None:
        dot = self.context.next(replica)
        # A fresh add supersedes this element's prior dots; the new dot alone
        # keeps membership compact without changing semantics.
        self.entries[element] = {dot}

    def remove(self, element: str) -> None:
        # Drop the dots we currently observe. The context keeps them "seen",
        # so merge won't resurrect *these* dots -- but a concurrent add's
        # unseen dot will survive.
        self.entries.pop(element, None)

    def contains(self, element: str) -> bool:
        return element in self.entries

    def elements(self) -> set[str]:
        return set(self.entries)

    def merge(self, other: "ORSWOT") -> "ORSWOT":
        merged: dict[str, set[Dot]] = {}
        for element in set(self.entries) | set(other.entries):
            a = self.entries.get(element, set())
            b = other.entries.get(element, set())
            keep = (a & b)  # dots both replicas still hold
            keep |= {d for d in a if not other.context.saw(d)}  # unseen by B -> concurrent add
            keep |= {d for d in b if not self.context.saw(d)}   # unseen by A -> concurrent add
            if keep:
                merged[element] = keep
        return ORSWOT(merged, self.context.merged(other.context))

    def to_json(self) -> dict[str, Any]:
        return {
            "entries": {k: sorted(list(v)) for k, v in self.entries.items()},
            "context": self.context.to_json(),
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "ORSWOT":
        entries = {k: {(d[0], int(d[1])) for d in v} for k, v in data["entries"].items()}
        return cls(entries, VersionVector.from_json(data["context"]))


@dataclass(frozen=True)
class MVEntry:
    value: str
    context: tuple[tuple[str, int], ...]  # frozen version vector snapshot at write time

    def vv(self) -> VersionVector:
        return VersionVector({r: c for r, c in self.context})


class MVRegister:
    """Multi-Value Register: keeps all causally-concurrent writes.

    A write records the value together with a snapshot of the causal
    context it observed. On merge, an entry is dropped only if some *other*
    entry's context strictly dominates it; genuinely concurrent writes both
    survive, yielding ``len(values()) > 1`` -- a conflict to surface.
    """

    def __init__(self, entries: Iterable[MVEntry] | None = None) -> None:
        self.entries: set[MVEntry] = set(entries or ())

    def write(self, value: str, ctx: VersionVector, replica: str) -> None:
        dot = ctx.next(replica)
        snapshot = VersionVector(ctx.clocks)  # includes the dot just minted
        snapshot.clocks[dot[0]] = dot[1]
        self.entries = {MVEntry(value, tuple(sorted(snapshot.clocks.items())))}

    def values(self) -> list[str]:
        return sorted({e.value for e in self.entries})

    def is_conflicted(self) -> bool:
        return len(self.values()) > 1

    def resolve(self, value: str, ctx: VersionVector, replica: str) -> None:
        """Collapse a conflict to a single explicitly-chosen value."""
        self.write(value, ctx, replica)

    @staticmethod
    def _dominates(a: MVEntry, b: MVEntry) -> bool:
        """Does a.context strictly dominate b.context (a is causally newer)?"""
        av, bv = a.vv().clocks, b.vv().clocks
        if av == bv:
            return False
        for r, c in bv.items():
            if av.get(r, 0) < c:
                return False
        return True

    def merge(self, other: "MVRegister") -> "MVRegister":
        candidates = self.entries | other.entries
        kept = {
            e for e in candidates
            if not any(o is not e and self._dominates(o, e) for o in candidates)
        }
        return MVRegister(kept)

    def to_json(self) -> list[dict[str, Any]]:
        return [{"value": e.value, "context": [list(c) for c in e.context]} for e in self.entries]

    @classmethod
    def from_json(cls, data: list[dict[str, Any]]) -> "MVRegister":
        return cls(
            MVEntry(e["value"], tuple((c[0], int(c[1])) for c in e["context"]))
            for e in data
        )


@dataclass
class LWWRegister:
    """Last-Writer-Wins register: (Lamport ts, replica) breaks ties."""

    value: str | None = None
    ts: int = 0
    replica: str = ""

    def write(self, value: str, ts: int, replica: str) -> None:
        if (ts, replica) >= (self.ts, self.replica):
            self.value, self.ts, self.replica = value, ts, replica

    def merge(self, other: "LWWRegister") -> "LWWRegister":
        if (other.ts, other.replica) > (self.ts, self.replica):
            return LWWRegister(other.value, other.ts, other.replica)
        return LWWRegister(self.value, self.ts, self.replica)

    def to_json(self) -> dict[str, Any]:
        return {"value": self.value, "ts": self.ts, "replica": self.replica}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "LWWRegister":
        return cls(data.get("value"), int(data.get("ts", 0)), data.get("replica", ""))
