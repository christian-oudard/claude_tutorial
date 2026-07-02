"""Second-order (P-delta) tip deflection and amplified bending moment.

The first-order cantilever tip deflection under a lateral tip force ``F`` is
``delta0 = F h^3 / (3 E I)``.  Axial compression ``N`` softens the column and
amplifies both the deflection and the base moment.  We iterate the
fixed-point

    M2 = F h + N * delta
    delta = delta0 + N * delta * h^2 / (2 E I)      (secant softening)

to convergence, which sums to the closed-form amplification
``AF = 1 / (1 - N h^2 / (2 E I))``.  In practice we drive the amplification
with the buckling eigenvalue ``lambda`` (``AF = lambda / (lambda - 1)``) so
the deflection and buckling checks stay consistent, and use the fixed-point
loop only to fold the axial term into the *moment* used for yield (spec
trap 4).
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class DeflectionResult:
    delta0: float  # first-order tip deflection
    delta: float  # second-order (amplified) tip deflection
    moment2: float  # second-order base bending moment
    amplification: float  # AF actually applied


def first_order_deflection(F: float, h: float, E: float, I: float) -> float:
    return F * h**3 / (3.0 * E * I)


def second_order(
    F: float,
    h: float,
    E: float,
    I: float,
    N: float,
    amplification: float,
    iters: int = 4,
) -> DeflectionResult:
    """Amplified tip deflection and base moment.

    ``amplification`` is the AF from the buckling eigenvalue.  ``N`` is the
    axial compression that couples into the base moment via P-delta.  The
    fixed-point loop refines the second-order moment ``M2 = F h + N delta``.
    """
    delta0 = first_order_deflection(F, h, E, I)
    if not math.isfinite(amplification):
        return DeflectionResult(delta0, math.inf, math.inf, math.inf)

    delta = delta0 * amplification
    moment2 = F * h
    for _ in range(max(1, iters)):
        moment2 = F * h + N * delta
        # deflection consistent with the amplified moment
        delta = delta0 * amplification
    return DeflectionResult(delta0, delta, moment2, amplification)
