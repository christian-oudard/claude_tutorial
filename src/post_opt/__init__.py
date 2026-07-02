"""Axisymmetric post optimizer.

Given a fixed metal mass, find the rotationally symmetric shape that stands a
load off the ground at maximum height without failing structurally, tipping, or
exceeding soil bearing pressure.

Milestone status:

* **M1 (this package):** two-cylinder ``(r, h, D, t)`` model with deflection
  (P-delta), partial-uplift overturning (+ kern ``--conservative`` flag),
  shear and punching checks, buckling, plate bending, bearing.
* M2-M4 (free profile FEM, bolt shapes, dynamics) are future milestones; the
  physics/model/optimizer separation here is designed for them to slot in.
"""

from .config import PostConfig
from .model import PostEvaluation, PostModel
from .optimize import OptimizeResult, PostOptimizer

__all__ = [
    "PostConfig",
    "PostModel",
    "PostEvaluation",
    "PostOptimizer",
    "OptimizeResult",
]

__version__ = "0.1.0"
