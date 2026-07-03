"""Axisymmetric post optimizer.

Given a fixed metal mass, find the rotationally symmetric shape that stands a
load off the ground at maximum height without failing structurally, tipping, or
exceeding soil bearing pressure.

Milestone status:

* **M1:** two-cylinder ``(r, h, D, t)`` model with deflection (P-delta),
  partial-uplift overturning (+ kern ``--conservative`` flag), shear and
  punching checks, buckling, plate bending, bearing.
* **M2:** free solid axisymmetric profile ``r(z)`` (PCHIP) solved with an
  Euler-Bernoulli FEM -- variable ``EI(z)``, eigenvalue buckling, second-order
  deflection -- via a fully-stressed-design inner sizer and bisection on ``H``.
* M3-M4 (bolt/flare shell models, dynamics) are future milestones.
"""

from .config import PostConfig
from .model import PostEvaluation, PostModel
from .optimize import OptimizeResult, PostOptimizer
from .profile import ProfileEvaluation, ProfileModel
from .profile_optimize import ProfileOptimizer, ProfileResult

__all__ = [
    "PostConfig",
    "PostModel",
    "PostEvaluation",
    "PostOptimizer",
    "OptimizeResult",
    "ProfileModel",
    "ProfileEvaluation",
    "ProfileOptimizer",
    "ProfileResult",
]

__version__ = "0.1.0"
