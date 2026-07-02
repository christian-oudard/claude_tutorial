"""Soil bearing pressure and vertical-support capacity under the base plate.

Two distinct notions, both reported:

* **Elastic peak pressure** (kern model): while the resultant is inside the
  kern (``e <= D/8``) the linear no-uplift distribution peaks at
  ``q_max = N / A_plate * (1 + 8 e / D)``.  This is the governing bearing
  measure for the elastic ``--conservative`` model.
* **Plastic contact area** (partial-uplift model): the rigid-plastic soil holds
  ``q_allow`` over a contact area ``A_c = N / q_allow``; vertical support is
  exhausted when that area no longer fits inside the plate.  The bearing margin
  is then the area utilisation ``A_c / A_plate`` -- for the light posts in scope
  this sits orders of magnitude below unity while overturning (a moment check)
  may still govern.
"""

from __future__ import annotations

import math


def plate_area(D: float) -> float:
    return math.pi * D * D / 4.0


def elastic_peak_pressure(N: float, D: float, e: float) -> float:
    """Elastic (kern) peak pressure; grows past ``2N/A`` beyond the kern."""
    A = plate_area(D)
    if N <= 0.0:
        return 0.0
    return N / A * (1.0 + 8.0 * e / D)


def contact_area(N: float, q_allow: float) -> float:
    """Plastic contact area required to carry the vertical load ``N``."""
    if N <= 0.0:
        return 0.0
    return N / q_allow


def contact_area_fraction(N: float, D: float, q_allow: float) -> float:
    """``A_c / A_plate`` -- vertical-support utilisation (partial uplift)."""
    return contact_area(N, q_allow) / plate_area(D)


def average_pressure(N: float, D: float) -> float:
    return N / plate_area(D) if N > 0.0 else 0.0
