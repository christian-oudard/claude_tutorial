"""Run all experiments and print a measured report.

    python -m declpkg.experiments.run

Every experiment asserts its own invariants, so this doubles as a test:
a nonzero exit means a claim failed to hold.
"""

from __future__ import annotations

import copy
import random

from .coordination import simulate_round, sweep
from .resolve import DesiredManifest, resolve_view, satisfies
from .store import Store, StoreKey


def hr(title: str) -> None:
    print("\n" + "=" * 72 + f"\n{title}\n" + "=" * 72)


# --------------------------------------------------------------------------
def exp_a_store_is_conflict_free() -> None:
    hr("A. Store is grow-only & conflict-free under concurrent, out-of-order adds")
    # Five 'agents' concurrently add packages, including CONFLICTING versions
    # of the same package (numpy 1.26 vs 2.0) and DUPLICATE adds.
    adds = [
        StoreKey("pip", "numpy", "1.26.4"),
        StoreKey("pip", "numpy", "2.0.1"),      # conflicts with 1.26 in a venv...
        StoreKey("pip", "numpy", "1.26.4"),      # duplicate of the first
        StoreKey("pip", "requests", "2.31.0"),
        StoreKey("npm", "left-pad", "1.3.0"),
        StoreKey("cargo", "serde", "1.0.197"),
        StoreKey("pip", "numpy", "2.0.1"),       # another duplicate
    ]

    # Apply in three different shuffles on three separate store replicas,
    # then merge them (the G-Set union). Result must be identical & deduped.
    rng = random.Random(1)
    replicas = []
    for _ in range(3):
        order = adds[:]
        rng.shuffle(order)
        s = Store()
        for k in order:
            s.add(k)
        replicas.append(s)

    merged = Store()
    for s in replicas:
        merged.merge(s)

    versions = merged.available_versions("pip", "numpy")
    print(f"  distinct store entries: {len(merged)}  (from {len(adds)} adds)")
    print(f"  numpy versions coexisting in store: {versions}")
    for s in replicas:
        print(f"  replica size after its shuffle: {len(s)}")

    # invariants
    assert len(merged) == 5, "duplicates must dedupe to 5 distinct entries"
    assert versions == ["1.26.4", "2.0.1"], "conflicting versions coexist, no merge"
    assert all(len(s) == 5 for s in replicas), "order-independent (commutative)"
    # merging is idempotent
    before = len(merged)
    merged.merge(replicas[0])
    assert len(merged) == before, "merge is idempotent"
    print("  OK: union is commutative, idempotent, deduped; versions coexist.")


# --------------------------------------------------------------------------
def exp_b_views_solve_venv() -> None:
    hr("B. Per-agent views isolate CONFLICTING versions (the venv problem)")
    store = Store()
    # The store offers several numpy versions (grow-only superset).
    for v in ["1.24.0", "1.26.4", "2.0.1", "2.1.0"]:
        store.add(StoreKey("pip", "numpy", v))
    store.add(StoreKey("pip", "requests", "2.31.0"))

    # Three agents want mutually-incompatible numpy, plus a shared requests.
    legacy = DesiredManifest("legacy-proj")
    legacy.want("pip", "numpy", ">=1.24,<2")
    legacy.want("pip", "requests", ">=2.30")

    modern = DesiredManifest("modern-proj")
    modern.want("pip", "numpy", ">=2.0")
    modern.want("pip", "requests", ">=2.30")

    twin = DesiredManifest("legacy-twin")
    twin.want("pip", "numpy", ">=1.24,<2")   # same constraint as `legacy`

    views = [resolve_view(m, store) for m in (legacy, modern, twin)]
    for v in views:
        print(f"  {v.agent_id:<12} -> {v.path_map()}")

    legacy_np = views[0].selections[("pip", "numpy")]
    modern_np = views[1].selections[("pip", "numpy")]
    twin_np = views[2].selections[("pip", "numpy")]

    # invariants: conflicting views coexist; identical needs SHARE a store path
    assert legacy_np.version == "1.26.4" and modern_np.version == "2.1.0", \
        "each view picked the highest version satisfying its own constraint"
    assert legacy_np.content_path() != modern_np.content_path(), \
        "conflicting versions live at different store paths -- isolation"
    assert legacy_np.content_path() == twin_np.content_path(), \
        "identical requirement resolves to the SAME store path -- sharing"
    assert store.refcount(legacy_np) == 2, "shared numpy 1.26 has refcount 2"
    assert store.refcount(modern_np) == 1
    print(f"  numpy 1.26.4 shared by 2 views (refcount={store.refcount(legacy_np)}); "
          f"numpy 2.1.0 used by 1.")
    print("  OK: conflicting versions isolated per view AND deduplicated when equal.")


# --------------------------------------------------------------------------
def exp_c_coordination_cost() -> None:
    hr("C. Coordination cost: G-Set vs OCC vs Lock, as contention rises")
    print("  16 agents, one read-modify-write each, 400 randomized interleavings.")
    print(f"  {'keys':>4} {'agents/key':>11} {'G-Set':>7} {'OCC retries':>12} {'Lock waits':>11}")
    rows = sweep(n_agents=16, key_counts=[64, 16, 4, 1], trials=400)
    for r in rows:
        print(f"  {r['keys']:>4} {r['contention']:>11} {r['gset_cost']:>7.1f} "
              f"{r['occ_retries']:>12} {r['lock_waits']:>11}")

    lo, hi = rows[0], rows[-1]  # K=64 (low contention) vs K=1 (single shared cell)
    assert lo["gset_cost"] == hi["gset_cost"] == 0.0, "G-Set never coordinates"
    assert hi["occ_retries"] > lo["occ_retries"], "OCC cost grows with contention"
    assert hi["lock_waits"] > lo["lock_waits"], "Lock serialization grows too"
    print("\n  Reading it:")
    print("  * Grow-only store  -> writes commute -> G-Set pays 0 at every level.")
    print("    The OCC/Lock columns there are PURE OVERHEAD you avoid by unioning.")
    print("  * Single shared cell (keys=1) -> a real last-writer conflict union")
    print("    can't help with. THAT is the rare case worth OCC (lighter) or a lock.")


# --------------------------------------------------------------------------
def exp_d_gc_needs_coordination() -> None:
    hr("D. GC is the one hot-path op that DOES need coordination")
    # A referenced by numpy 1.26; agent B is mid-resolve, about to acquire it.
    store = Store()
    np126 = StoreKey("pip", "numpy", "1.26.4")

    # --- naive concurrent GC (no coordination) ---
    store_bad = copy.deepcopy(store)
    store_bad.add(np126)                      # present, refcount 0 (just added)
    #   B's resolve SELECTS this path but hasn't materialized (acquired) it yet;
    #   GC scans, sees rc==0, and collects it out from under B.
    b_selection = np126.content_path()        # recorded in B's pending view
    collected = store_bad.gc()                # GC runs before B materializes
    dangling = b_selection in collected and not store_bad.contains(np126)
    print(f"  naive GC:  B selected {b_selection}")
    print(f"             GC collected={collected}")
    print(f"             B's pending view now points at a gone path -> dangling = {dangling}")
    assert dangling, "demonstrates the race: unsynchronized GC drops a selected-but-unmaterialized path"

    # --- single-writer GC (acquire-before-scan; the fix) ---
    store_ok = Store()
    store_ok.acquire(np126)                  # B acquires FIRST (refcount 1)
    collected2 = store_ok.gc()               # GC now sees rc==1 -> keeps it
    print(f"  ordered:   B acquires first, then GC -> collected={collected2}, "
          f"kept refcount={store_ok.refcount(np126)}")
    assert collected2 == [], "with acquire-before-GC, the live path survives"
    print("  OK: adds/acquires are conflict-free, but GC vs acquire is a real race.")
    print("      -> run GC single-writer (or under a lock). This is the ONLY place")
    print("         the earlier 'reserve locking for a critical section' applies.")


def main() -> None:
    exp_a_store_is_conflict_free()
    exp_b_views_solve_venv()
    exp_c_coordination_cost()
    exp_d_gc_needs_coordination()
    hr("Summary")
    print("  * Store = grow-only content-addressed G-Set: conflict-free, the only")
    print("    CRDT you need, and the trivial one (union).")
    print("  * Per-agent desired manifest -> view: single-writer, no coordination;")
    print("    content-addressing makes the venv/conflicting-version problem vanish")
    print("    (different versions are different store paths; equal needs share).")
    print("  * Full CRDT machinery (dots, MVRegister, add-wins) was solving a")
    print("    problem the data model removed. Coordinate only for GC / global")
    print("    policy, and there OCC is lighter than locking.")


if __name__ == "__main__":
    main()
