"""Coordination shootout: G-Set (union) vs Optimistic Concurrency vs Lock.

We simulate N agents each performing one read-modify-write transaction
against a shared resource with K keys, under a randomized interleaving that
preserves each agent's read-before-write order. We measure the *coordination
cost* each strategy pays:

  * G-Set / union   -- 0. Concurrent writes commute; nobody coordinates.
  * OCC (CAS)       -- a "retry" every time another commit lands on the same
                       key between an agent's read and its write.
  * Lock            -- a "wait" every time an agent must block on a key another
                       agent already holds (serialized transactions).

The point: for a *grow-only store* the writes genuinely commute, so OCC's
retries and the lock's waits are pure overhead the G-Set avoids. For a
*single genuinely-shared value* (K=1 policy cell) the conflict is real, union
doesn't apply, and OCC/lock cost is unavoidable -- that's the rare case where
you actually coordinate.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


def _random_interleaving(n_agents: int, rng: random.Random) -> list[tuple[int, str]]:
    """Random merge of per-agent [read, write] preserving order within agent."""
    remaining = {a: ["r", "w"] for a in range(n_agents)}
    schedule: list[tuple[int, str]] = []
    while remaining:
        a = rng.choice(list(remaining))
        schedule.append((a, remaining[a].pop(0)))
        if not remaining[a]:
            del remaining[a]
    return schedule


@dataclass
class RoundResult:
    occ_retries: int
    lock_waits: int
    gset_cost: int = 0  # always 0; kept for a symmetric report


def simulate_round(n_agents: int, n_keys: int, rng: random.Random) -> RoundResult:
    keys = [rng.randrange(n_keys) for _ in range(n_agents)]  # each agent's target key
    schedule = _random_interleaving(n_agents, rng)

    # index of each agent's read and write positions in the schedule
    r_pos = {a: i for i, (a, ph) in enumerate(schedule) if ph == "r"}
    w_pos = {a: i for i, (a, ph) in enumerate(schedule) if ph == "w"}

    # --- OCC: a commit to key k invalidates any open read on k that hasn't
    # yet committed. Count, per agent, the commits on its key between its
    # read and its write. Each is one forced retry.
    occ_retries = 0
    for a in range(n_agents):
        for b in range(n_agents):
            if b == a or keys[b] != keys[a]:
                continue
            if r_pos[a] < w_pos[b] < w_pos[a]:
                occ_retries += 1

    # --- Lock: transactions on the same key serialize. Any agent that shares
    # a key with an earlier-committing agent must wait behind it.
    lock_waits = 0
    for k in range(n_keys):
        holders = sorted((w_pos[a] for a in range(n_agents) if keys[a] == k))
        lock_waits += max(0, len(holders) - 1)  # all but the first must wait

    return RoundResult(occ_retries=occ_retries, lock_waits=lock_waits)


def sweep(n_agents: int, key_counts: list[int], trials: int, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for k in key_counts:
        occ = lock = 0
        for _ in range(trials):
            res = simulate_round(n_agents, k, rng)
            occ += res.occ_retries
            lock += res.lock_waits
        rows.append({
            "keys": k,
            "contention": round(n_agents / k, 2),
            "gset_cost": 0.0,
            "occ_retries": round(occ / trials, 2),
            "lock_waits": round(lock / trials, 2),
        })
    return rows
