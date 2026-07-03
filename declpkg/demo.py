"""End-to-end walkthrough. Run: python -m declpkg.demo

Tells the whole story: one manifest across five ecosystems, deterministic
native-file generation, declarative reconciliation, and -- the point of the
CRDT -- two machines editing offline and merging, with a version conflict
surfaced instead of silently resolved, plus add-wins on membership.
"""

from __future__ import annotations

import copy

from .generate import generate
from .manifest import Replica
from .reconcile import apply, plan


def rule(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def seed(replica_id: str) -> Replica:
    r = Replica(replica_id)
    r.install("requests", "pip", version=">=2.31,<3")
    r.install("numpy", "pip")
    r.install("left-pad", "npm", version="1.3.0")
    r.install("serde", "cargo", version="1.0")
    r.install("mathlib", "lake",
              source="https://github.com/leanprover-community/mathlib4",
              version="v4.7.0")
    r.install("aeson", "cabal", version=">=2.2 && <2.3")
    return r


def main() -> None:
    rule("1. One declarative manifest, five ecosystems")
    laptop = seed("laptop")
    for p in laptop.resolved().values():
        print(f"  {p.name:<16} {p.ecosystem:<7} {p.version or '*'}")

    rule("2. Generate each ecosystem's NATIVE file (deterministic)")
    for filename, contents in generate(laptop).items():
        print(f"\n----- {filename} -----")
        print(contents.rstrip())

    rule("3. Declarative reconcile: converge the world to the manifest")
    applied = "/tmp/declpkg-demo-applied.json"
    import os
    if os.path.exists(applied):
        os.remove(applied)
    print(plan(laptop, applied).render())
    print("\n-- apply (dry run) then re-plan --")
    apply(laptop, applied, execute=False)
    print(plan(laptop, applied).render())

    rule("4. Two machines diverge OFFLINE, then merge")
    # Fork the shared state onto a second machine.
    server = Replica.from_json(copy.deepcopy(laptop.to_json()))
    server.replica_id = "server"

    print("laptop:  bump requests -> >=2.32,<3   (security update)")
    laptop.set_version("requests", ">=2.32,<3")
    print("server:  pin  requests -> ==2.31.4    (reproducibility freeze)")
    server.set_version("requests", "==2.31.4")

    print("laptop:  uninstall left-pad")
    laptop.uninstall("left-pad")
    print("server:  (concurrently) re-install left-pad @ 1.3.1")
    server.install("left-pad", "npm", version="1.3.1")  # a genuine concurrent ADD

    print("\n-- laptop merges in server's state --")
    laptop.merge(server)

    print("\nresolved manifest after merge:")
    for p in laptop.resolved().values():
        ver = ("CONFLICT[" + " | ".join(p.version_candidates) + "]"
               if p.conflicted else (p.version or "*"))
        print(f"  {p.name:<16} {p.ecosystem:<7} {ver}")

    print("\nNote: left-pad survives (ADD-WINS) even though laptop removed it,")
    print("because server's concurrent re-install minted a dot the removal")
    print("never observed. A pure version edit would NOT win -- add-wins is a")
    print("property of membership, not of field writes.")

    rule("5. Version conflict blocks apply until resolved")
    print("conflicts:", laptop.conflicts())
    p = plan(laptop, applied)
    print(p.render())

    rule("6. Explicit resolution, then a clean apply")
    laptop.resolve_version("requests", ">=2.32,<3")
    print("resolved requests -> >=2.32,<3")
    print(plan(laptop, applied).render())

    print("\nDone. The conflict was surfaced for a human, never silently lost.")


if __name__ == "__main__":
    main()
