"""Named constraint functions, each returning a signed margin.

Convention: every ``margin_*`` function returns ``g`` with ``g >= 0`` feasible
and ``g < 0`` a violation.  Where a natural normalisation exists the margin is
dimensionless (utilisation form ``1 - demand/capacity``); this keeps the
Jacobian well scaled for the optimizer.  Each is unit-tested against a hand
computation in ``tests/``.
"""

from __future__ import annotations

import math

# A large finite sentinel used when a capacity collapses to zero, so the
# optimizer sees a strong (but finite) violation gradient rather than -inf.
_BIG = 1e6


def margin_yield(sigma: float, sigma_y: float) -> float:
    """Normal-stress yield margin ``1 - sigma / sigma_y``."""
    return 1.0 - sigma / sigma_y


def margin_shear(tau: float, tau_y: float) -> float:
    """Shear yield margin ``1 - tau / tau_y``."""
    return 1.0 - tau / tau_y


def margin_punching(tau_p: float, tau_y: float) -> float:
    """Punching-shear margin at the shaft/plate junction."""
    return 1.0 - tau_p / tau_y


def margin_plate_bending(sigma_p: float, sigma_y: float) -> float:
    """Base-plate bending margin."""
    return 1.0 - sigma_p / sigma_y


def margin_overturning(M_applied: float, M_cap: float) -> float:
    """Rigid-body stability margin ``1 - M_applied / M_cap``.

    A collapsed capacity (``M_cap <= 0``) returns a large negative margin.
    """
    if M_cap <= 0.0:
        return -_BIG
    return 1.0 - M_applied / M_cap


def margin_bearing(q_max: float, q_allow: float) -> float:
    """Soil bearing margin ``1 - q_max / q_allow``."""
    return 1.0 - q_max / q_allow


def margin_buckling(lam: float, SF: float) -> float:
    """Buckling margin ``lambda / SF - 1`` (require ``lambda >= SF``)."""
    if not math.isfinite(lam):
        return _BIG
    return lam / SF - 1.0


def margin_deflection(delta: float, H: float, eps: float) -> float:
    """Serviceability margin ``1 - (delta / H) / eps``."""
    if not math.isfinite(delta):
        return -_BIG
    return 1.0 - (delta / H) / eps
