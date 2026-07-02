"""Material stress checks: normal (axial + bending), shear, torsion, punching.

The shaft is a solid circle.  Normal stress at the extreme fibre of the base
section combines axial force and bending moment:

    sigma = N / A + M_b / S,   S = pi r^3 / 4.

Transverse shear peaks at the neutral axis of a solid circle at
``tau = 4 V / (3 A)``; torsion adds ``tau_T = T r / J``.  These are compared to
the shear yield ``tau_y = sigma_y / sqrt(3)`` (von Mises).

Punching shear at the shaft/plate junction spreads the transferred vertical
load over the cylindrical surface ``2 pi r t``.
"""

from __future__ import annotations

import math

SQRT3 = math.sqrt(3.0)


def normal_stress(N: float, M_b: float, area: float, section_modulus: float) -> float:
    """Extreme-fibre normal stress from axial force + bending moment."""
    return abs(N) / area + abs(M_b) / section_modulus


def transverse_shear_stress(V: float, area: float) -> float:
    """Peak transverse shear stress in a solid circular section."""
    return 4.0 * abs(V) / (3.0 * area)


def torsion_stress(T: float, r: float, J: float) -> float:
    """Surface shear stress from torsion, ``tau = T r / J``."""
    if T == 0.0:
        return 0.0
    return abs(T) * r / J


def combined_shear_stress(V: float, T: float, r: float, area: float, J: float) -> float:
    """Transverse shear + torsion (added at the worst point, conservative)."""
    return transverse_shear_stress(V, area) + torsion_stress(T, r, J)


def shear_yield(sigma_y: float) -> float:
    return sigma_y / SQRT3


def punching_shear_stress(V_vertical: float, r: float, t: float) -> float:
    """Punching shear at the shaft perimeter, ``tau = V / (2 pi r t)``."""
    return abs(V_vertical) / (2.0 * math.pi * r * t)


def plate_bending_stress(q: float, a: float, r: float, t: float) -> float:
    """Base-plate bending stress at the shaft junction.

    The annulus outside the shaft is treated as a radial cantilever of length
    ``a - r`` carrying uniform pressure ``q``; the junction moment per unit
    width is ``q (a - r)^2 / 2`` giving ``sigma = 3 q (a - r)^2 / t^2``.
    """
    lever = max(a - r, 0.0)
    return 3.0 * q * lever * lever / (t * t)
