"""Rigid-body overturning of the base plate.

Two models are provided:

**Kern (elastic, ``--conservative``).**  No tension is allowed and the soil is
elastic, so the vertical resultant must fall inside the kern of the circular
plate: eccentricity ``e = M / N <= D / 8``.

**Partial uplift (rigid-plastic, default).**  The soil is rigid-plastic and can
push at up to ``q_allow`` over whatever contact area it needs; it cannot pull.
Vertical equilibrium fixes the contact area ``A_c = N / q_allow``.  The largest
resisting moment is obtained when that area is a circular segment pushed to the
far rim; its first moment about the centre gives the overturning capacity

    M_cap = q_allow * (2/3) (a^2 - p^2)^(3/2)

where ``a = D/2`` and the chord offset ``p`` solves ``A_seg(p) = A_c`` with

    A_seg(p) = a^2 * acos(p/a) - p * sqrt(a^2 - p^2).

Overturning is exhausted when ``A_c`` no longer fits inside the plate
(``A_c >= pi a^2``): then ``M_cap = 0`` and the design fails outright.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class OverturnResult:
    e: float  # eccentricity M / N
    M_applied: float  # overturning moment demand
    M_cap: float  # overturning capacity
    contact_area: float  # required contact area (partial-uplift) or nan
    model: str


def kern_capacity(N: float, D: float) -> float:
    """Overturning capacity under the kern model: ``M_cap = N D / 8``."""
    return N * D / 8.0


def _segment_area(p: float, a: float) -> float:
    """Area of the circular segment of radius ``a`` beyond chord offset ``p``."""
    p = min(max(p, 0.0), a)
    return a * a * math.acos(p / a) - p * math.sqrt(max(a * a - p * p, 0.0))


def _solve_chord_offset(A_c: float, a: float) -> float:
    """Chord offset ``p`` such that the far segment has area ``A_c``.

    ``A_seg`` decreases monotonically from ``pi a^2`` (p=0) to 0 (p=a), so a
    bisection is robust.
    """
    lo, hi = 0.0, a
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if _segment_area(mid, a) > A_c:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def partial_uplift_capacity(N: float, D: float, q_allow: float) -> tuple[float, float]:
    """Return ``(M_cap, contact_area)`` for the rigid-plastic contact model."""
    a = D / 2.0
    plate_area = math.pi * a * a
    if N <= 0.0:
        return 0.0, 0.0
    A_c = N / q_allow
    if A_c >= plate_area:
        return 0.0, A_c
    p = _solve_chord_offset(A_c, a)
    M_cap = q_allow * (2.0 / 3.0) * (a * a - p * p) ** 1.5
    return M_cap, A_c


def overturning(
    N: float, M_applied: float, D: float, q_allow: float, conservative: bool
) -> OverturnResult:
    e = M_applied / N if N > 0.0 else math.inf
    if conservative:
        M_cap = kern_capacity(N, D)
        return OverturnResult(e, M_applied, M_cap, math.nan, "kern")
    M_cap, A_c = partial_uplift_capacity(N, D, q_allow)
    return OverturnResult(e, M_applied, M_cap, A_c, "partial_uplift")
