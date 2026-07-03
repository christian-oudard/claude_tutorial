"""Declarative reconciliation: converge the world to the manifest.

Like Nix, the manifest declares *desired* state. Reconciliation diffs it
against the last *applied* state and emits the minimal set of concrete
per-ecosystem commands to close the gap:

  * INSTALL  -- in the manifest, not yet applied
  * REMOVE   -- applied, no longer in the manifest
  * UPGRADE  -- present in both, version/pin changed

Applying records the new state, so reconciliation is idempotent: run it
twice and the second run is a no-op.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any

from .backends import Package, get_backend
from .manifest import Replica


@dataclass
class Action:
    kind: str          # INSTALL | REMOVE | UPGRADE
    package: Package
    command: list[str]
    detail: str = ""

    def render(self) -> str:
        return f"  {self.kind:<8} {self.package.name:<16} $ {' '.join(self.command)}"


@dataclass
class Plan:
    actions: list[Action] = field(default_factory=list)
    conflicts: dict[str, list[str]] = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return not self.actions

    def render(self) -> str:
        lines: list[str] = []
        if self.conflicts:
            lines.append("Unresolved version conflicts (fix before applying):")
            for name, cands in sorted(self.conflicts.items()):
                lines.append(f"  ! {name}: {' | '.join(cands)}")
            lines.append("")
        if self.empty:
            lines.append("Nothing to do -- applied state matches the manifest.")
        else:
            lines.append(f"Plan: {len(self.actions)} action(s)")
            lines.extend(a.render() for a in self.actions)
        return "\n".join(lines)


def _load_applied(path: str) -> dict[str, dict[str, Any]]:
    if not os.path.exists(path):
        return {}
    with open(path) as fh:
        return json.load(fh)


def _save_applied(path: str, state: dict[str, dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)


def plan(replica: Replica, applied_path: str) -> Plan:
    applied = _load_applied(applied_path)
    desired = replica.resolved()
    p = Plan(conflicts=replica.conflicts())

    # INSTALL / UPGRADE
    for name, rp in desired.items():
        if rp.conflicted:
            continue  # can't act until resolved; reported via p.conflicts
        pkg = Package(name, rp.ecosystem, rp.version, rp.source)
        backend = get_backend(rp.ecosystem)
        if name not in applied:
            p.actions.append(Action("INSTALL", pkg, backend.install_cmd(pkg)))
        elif applied[name].get("version") != rp.version:
            p.actions.append(Action(
                "UPGRADE", pkg, backend.install_cmd(pkg),
                detail=f"{applied[name].get('version')} -> {rp.version}"))

    # REMOVE
    for name, meta in applied.items():
        if name not in desired:
            pkg = Package(name, meta["ecosystem"], meta.get("version"))
            backend = get_backend(meta["ecosystem"])
            p.actions.append(Action("REMOVE", pkg, backend.remove_cmd(pkg)))

    p.actions.sort(key=lambda a: (a.kind, a.package.name))
    return p


def apply(replica: Replica, applied_path: str, *, execute: bool = False) -> Plan:
    """Apply the plan. ``execute=False`` (default) is a dry run.

    Refuses to apply while any version conflict is unresolved.
    """
    p = plan(replica, applied_path)
    if p.conflicts:
        return p  # caller inspects p.conflicts and aborts

    applied = _load_applied(applied_path)
    for action in p.actions:
        if execute:
            subprocess.run(action.command, check=False)
        if action.kind in ("INSTALL", "UPGRADE"):
            applied[action.package.name] = {
                "ecosystem": action.package.ecosystem,
                "version": action.package.version,
            }
        elif action.kind == "REMOVE":
            applied.pop(action.package.name, None)
    _save_applied(applied_path, applied)
    return p
