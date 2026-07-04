"""Per-agent desired manifests -> resolved views over the shared store.

A ``DesiredManifest`` is owned by exactly one agent (single writer -> no
concurrency at this level). ``resolve_view`` picks one concrete version per
package from what the store offers, realizes it (acquire -> refcount), and
returns a ``View``. Two agents can hold conflicting versions in their views
with no conflict, because a view is per-agent isolation, not a global merge.

The version solve is deliberately tiny -- in production you delegate this to
uv / poetry / cargo, which already do it well. The point of the experiment
is the *architecture*, not the SAT solver.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .store import Store, StoreKey


def parse_version(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)) or (0,)


def _satisfies_clause(version: str, clause: str) -> bool:
    clause = clause.strip()
    m = re.match(r"^(>=|<=|==|!=|>|<)\s*(.+)$", clause)
    if not m:  # bare version -> prefix match (e.g. "1.0" matches "1.0.3")
        want = parse_version(clause)
        got = parse_version(version)
        return got[: len(want)] == want
    op, rhs = m.group(1), m.group(2)
    a, b = parse_version(version), parse_version(rhs)
    n = max(len(a), len(b))
    a += (0,) * (n - len(a))
    b += (0,) * (n - len(b))
    return {
        ">=": a >= b, "<=": a <= b, "==": a == b,
        "!=": a != b, ">": a > b, "<": a < b,
    }[op]


def satisfies(version: str, spec: str) -> bool:
    # spec is a comma- or &&-separated conjunction of clauses
    clauses = re.split(r",|&&", spec)
    return all(_satisfies_clause(version, c) for c in clauses if c.strip())


@dataclass(frozen=True)
class Requirement:
    ecosystem: str
    name: str
    spec: str = "*"           # "*" = any version
    platform: str = "any"


@dataclass
class DesiredManifest:
    agent_id: str
    requirements: list[Requirement] = field(default_factory=list)

    def want(self, ecosystem: str, name: str, spec: str = "*", platform: str = "any") -> None:
        self.requirements.append(Requirement(ecosystem, name, spec, platform))


@dataclass
class View:
    agent_id: str
    selections: dict[tuple[str, str], StoreKey] = field(default_factory=dict)
    unresolved: list[Requirement] = field(default_factory=list)

    def path_map(self) -> dict[str, str]:
        return {f"{eco}:{name}": key.content_path()
                for (eco, name), key in sorted(self.selections.items())}


def resolve_view(desired: DesiredManifest, store: Store) -> View:
    """Pick one version per package from the store; realize into refcounts."""
    view = View(desired.agent_id)
    for req in desired.requirements:
        candidates = store.available_versions(req.ecosystem, req.name)
        if req.spec == "*":
            picks = candidates
        else:
            picks = [v for v in candidates if satisfies(v, req.spec)]
        if not picks:
            view.unresolved.append(req)
            continue
        best = max(picks, key=parse_version)   # highest satisfying version
        key = StoreKey(req.ecosystem, req.name, best, req.platform)
        store.acquire(key)
        view.selections[(req.ecosystem, req.name)] = key
    return view
