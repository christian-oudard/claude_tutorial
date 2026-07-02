"""Global buckling of the shaft column under self-weight + tip load.

For a uniform cantilever the two closed-form limits are:

* **Self-weight (Greenhill):** the column buckles under its own weight when
  ``w h^3 / (E I) = 7.8373``  (the first root of the governing Bessel
  equation).  Hence the load factor on the self weight alone is
  ``lambda_self = 7.8373 E I / (w h^3)``.
* **Tip axial load (Euler):** a cantilever with a tip force ``P`` buckles at
  ``P_cr = pi^2 E I / (4 h^2)``, giving ``lambda_euler = P_cr / P``.

When both act, we combine them with a Dunkerley (lower-bound) interaction

    1 / lambda = 1 / lambda_self + 1 / lambda_euler

which is conservative and reduces to each limit when the other load is zero.
``lambda`` is the factor by which the *current* loads may be multiplied before
buckling; the design requires ``lambda >= SF``.

The same ``lambda`` fixes the second-order (P-delta) amplification factor
``AF = lambda / (lambda - 1)`` used by the deflection and yield checks, so
buckling and deflection stay mutually consistent (spec trap 5).
"""

from __future__ import annotations

import math

# First eigenvalue of self-weight cantilever buckling (Greenhill / Willers).
GREENHILL = 7.8373


def greenhill_lambda(E: float, I: float, w: float, h: float) -> float:
    """Load factor on self-weight ``w`` before self-weight buckling."""
    if w <= 0.0 or h <= 0.0:
        return math.inf
    return GREENHILL * E * I / (w * h**3)


def euler_tip_lambda(E: float, I: float, P: float, h: float) -> float:
    """Load factor on tip axial load ``P`` before Euler buckling.

    ``P`` is the compressive tip load; tension or zero gives an infinite
    factor (no buckling contribution).
    """
    if P <= 0.0 or h <= 0.0:
        return math.inf
    P_cr = math.pi**2 * E * I / (4.0 * h**2)
    return P_cr / P


def greenhill_height(E: float, I: float, w: float, SF: float = 1.0) -> float:
    """Critical (or SF-reduced) self-weight buckling height.

    ``h_cr = (7.8373 E I / (w SF))^(1/3)``.
    """
    return (GREENHILL * E * I / (w * SF)) ** (1.0 / 3.0)


def combined_lambda(
    E: float, I: float, w: float, P: float, h: float
) -> float:
    """Dunkerley-combined buckling load factor for self-weight + tip load."""
    ls = greenhill_lambda(E, I, w, h)
    le = euler_tip_lambda(E, I, P, h)
    inv = 0.0
    if math.isfinite(ls):
        inv += 1.0 / ls
    if math.isfinite(le):
        inv += 1.0 / le
    if inv <= 0.0:
        return math.inf
    return 1.0 / inv


def amplification_factor(lam: float) -> float:
    """Second-order amplification ``AF = lambda / (lambda - 1)``.

    Returns ``+inf`` at or past the buckling load (``lambda <= 1``): the
    structure is unstable and any deflection/moment demand is unbounded.
    """
    if lam <= 1.0:
        return math.inf
    return lam / (lam - 1.0)
