"""Geometry and section properties for the v1 two-cylinder post.

The post is a solid circular *shaft* of radius ``r`` and height ``h`` standing
on a circular *base plate* of diameter ``D`` and thickness ``t``.  The load is
applied at the top of the shaft, a standoff height ``H = h`` above the plate.

All functions are pure and take explicit floats.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

PI = math.pi


@dataclass(frozen=True)
class TwoCylinder:
    """A concrete two-cylinder geometry (physical units, metres)."""

    r: float  # shaft radius
    h: float  # shaft height (== standoff height H)
    D: float  # base plate diameter
    t: float  # base plate thickness

    # -- shaft section properties -----------------------------------------
    @property
    def area(self) -> float:
        """Shaft cross-sectional area A = pi r^2."""
        return PI * self.r * self.r

    @property
    def I(self) -> float:
        """Second moment of area I = pi r^4 / 4."""
        return PI * self.r**4 / 4.0

    @property
    def J(self) -> float:
        """Polar moment J = pi r^4 / 2 (torsion)."""
        return PI * self.r**4 / 2.0

    @property
    def section_modulus(self) -> float:
        """Elastic section modulus S = I / c = pi r^3 / 4."""
        return PI * self.r**3 / 4.0

    @property
    def plate_radius(self) -> float:
        return self.D / 2.0

    @property
    def plate_area(self) -> float:
        return PI * self.plate_radius**2

    # -- volumes -----------------------------------------------------------
    @property
    def shaft_volume(self) -> float:
        return self.area * self.h

    @property
    def plate_volume(self) -> float:
        return self.plate_area * self.t

    @property
    def volume(self) -> float:
        return self.shaft_volume + self.plate_volume

    @property
    def standoff(self) -> float:
        """Standoff height H (top of shaft above plate)."""
        return self.h


def shaft_weight(geom: TwoCylinder, rho: float, g: float) -> float:
    return rho * g * geom.shaft_volume


def plate_weight(geom: TwoCylinder, rho: float, g: float) -> float:
    return rho * g * geom.plate_volume


def total_weight(geom: TwoCylinder, rho: float, g: float) -> float:
    return rho * g * geom.volume


def weight_per_length(geom: TwoCylinder, rho: float, g: float) -> float:
    """Self-weight per unit length of the shaft, w = rho g A."""
    return rho * g * geom.area
