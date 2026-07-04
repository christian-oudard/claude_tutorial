# Experiments: store+views vs. a general CRDT

Context: many agents in separate sandboxes concurrently add/update/remove
packages; a resolution procedure maintains shared state; different projects
need conflicting versions of the same package (the venv problem).

Run: `python -m declpkg.experiments.run` (every experiment asserts its own
invariants, so a clean exit *is* the result).

## A — The store is grow-only and conflict-free

Seven adds (including conflicting numpy 1.26.4 vs 2.0.1 and duplicates) applied
in three different shuffles across three replicas, then merged:

```
distinct store entries: 5  (from 7 adds)
numpy versions coexisting in store: ['1.26.4', '2.0.1']
```

Union is commutative, idempotent, and deduplicating. **Conflicting versions
are not a conflict** — they are different content-addressed entries that
coexist. This is a G-Set: the only CRDT the design needs, and the trivial one.

## B — Per-agent views solve the venv problem

Three agents want incompatible numpy from the same store:

```
legacy-proj  -> numpy 1.26.4  (>=1.24,<2)
modern-proj  -> numpy 2.1.0   (>=2.0)
legacy-twin  -> numpy 1.26.4  (>=1.24,<2)   # SAME path as legacy-proj
```

Conflicting versions live at different store paths (isolation); identical
requirements resolve to the *same* path (sharing, refcount 2). You never merge
conflicting versions — you give each agent a view. Isolation **and** dedup,
which plain per-project venvs (dedup=no) and one global env (isolation=no)
each fail to deliver.

## C — Coordination cost: G-Set vs OCC vs Lock

16 agents, one read-modify-write each, 400 randomized interleavings:

```
keys  agents/key   G-Set  OCC retries  Lock waits
  64        0.25     0.0         0.97        1.86
  16         1.0     0.0         3.75        5.71
   4         4.0     0.0        14.99       12.04
   1        16.0     0.0        61.52       15.00
```

For grow-only writes (the store), writes commute, so the G-Set pays **zero**
at every contention level — the OCC/Lock columns there are pure overhead you
avoid by unioning. Coordination only becomes worth its cost for a **single
genuinely-shared value** (keys=1: a real last-writer conflict union can't
help with), and even then OCC (≈62 cheap retries) is lighter-weight to
operate than a distributed lock service — no leases, no blocking.

## D — GC is the one hot-path op that needs coordination

Adds/acquires are conflict-free, but garbage collection races with them:

```
naive GC:  B selected /store/numpy-1.26.4-...
           GC collected=[/store/numpy-1.26.4-...]
           B's pending view now points at a gone path -> dangling = True
ordered:   B acquires first, then GC -> collected=[], kept refcount=1
```

Unsynchronized GC can collect a path a view just selected. Fix: run GC
single-writer (or under a lock). This is the *only* place the earlier
"reserve locking for a critical section" advice actually applies.

## Conclusion

The general CRDT (dots, version vectors, MVRegister, add-wins membership) was
solving a coordination problem that the **data model** removes:

- **Store** = grow-only content-addressed G-Set → conflict-free by construction.
- **Desired manifest → view** = single-writer per agent → no coordination.
- **Conflicting versions** = different store paths → the venv problem dissolves.

Coordinate only for GC and any global *policy* cell, and there prefer OCC over
locking. The heavyweight CRDT on the branch is over-engineered for this
context; keep only the G-Set.
