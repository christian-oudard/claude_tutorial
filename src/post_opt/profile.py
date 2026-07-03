"""M2: free solid axisymmetric profile ``r(z)``.

The slender shaft becomes a free radius profile defined by ``n`` control radii
on a fixed relative grid ``z_i = xi_i H`` and interpolated with a monotone cubic
(PCHIP) to avoid spline oscillation.  ``H`` is a separate scalar variable; the
base plate stays a discrete disc ``(D, t)`` (absorbed into the profile only in
M3).

Structural response is an Euler-Bernoulli FEM with variable ``EI(z)`` and
distributed self-weight (see :mod:`post_opt.fem`).  Constraints:

* **yield** pointwise ``sigma(z) = N(z)/A(z) + M_b(z) c / I(z)`` at every mesh
  node, aggregated by a p-norm (``p = 12``) into one smooth constraint, with a
  hard per-node check reported at the optimum;
* **buckling** from the generalized eigenproblem ``K phi = lambda K_G phi``,
  ``lambda >= SF``;
* **deflection** from the second-order stiffness ``(K - K_G)``;
* base-plate **overturning / bearing / plate-bending / punching / shear**
  reused unchanged from M1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.interpolate import PchipInterpolator

from . import constraints as C
from . import fem
from .config import PostConfig
from .physics import bearing, overturning, stress


@dataclass
class ProfileEvaluation:
    H: float
    xi: np.ndarray  # relative control grid
    radii: np.ndarray  # control radii
    D: float
    t: float
    volume: float
    shaft_volume: float
    weight: float
    lam_buckle: float
    delta_tip: float
    sigma_max: float  # hard max stress / sigma_y over all nodes
    sigma_pnorm: float  # p-norm aggregate / sigma_y
    z_nodes: np.ndarray
    sigma_nodes: np.ndarray
    overturn: overturning.OverturnResult
    overturn_kern: overturning.OverturnResult
    margins: dict[str, float] = field(default_factory=dict)

    @property
    def feasible(self) -> bool:
        return all(m >= 0.0 for m in self.margins.values())

    def min_margin(self) -> float:
        return min(self.margins.values()) if self.margins else 0.0

    def active_set(self, tol: float = 1e-3) -> list[str]:
        return [k for k, v in self.margins.items() if abs(v) <= tol]


class ProfileModel:
    def __init__(self, config: PostConfig):
        self.cfg = config
        self.n = config.profile.n_control
        self.xi = np.linspace(0.0, 1.0, self.n)

    def radius_fn(self, H: float, radii: np.ndarray):
        z_ctrl = self.xi * H
        pchip = PchipInterpolator(z_ctrl, radii, extrapolate=True)
        return lambda z: np.maximum(pchip(np.asarray(z, dtype=float)), 1e-9)

    # 5-point Gauss-Legendre nodes/weights on [-1, 1] (exact to degree 9;
    # r(z) is piecewise cubic so r(z)^2 is degree 6 -> integrated exactly).
    _GL_X = np.array([-0.9061798459, -0.5384693101, 0.0,
                      0.5384693101, 0.9061798459])
    _GL_W = np.array([0.2369268851, 0.4786286705, 0.5688888889,
                      0.4786286705, 0.2369268851])

    def shaft_volume(self, H: float, radii: np.ndarray, rf=None) -> float:
        """Exact shaft volume ``int pi r(z)^2 dz`` via per-segment Gauss.

        Integrating each PCHIP segment exactly gives a smooth volume with no
        quadrature noise, which keeps the optimizer's finite-difference
        gradients clean.
        """
        rf = rf or self.radius_fn(H, radii)
        z_ctrl = self.xi * H
        a = z_ctrl[:-1]
        b = z_ctrl[1:]
        half = 0.5 * (b - a)  # (nseg,)
        mid = 0.5 * (a + b)
        # evaluation points: (nseg, 5)
        zpts = mid[:, None] + half[:, None] * self._GL_X[None, :]
        vals = math.pi * rf(zpts.ravel()).reshape(zpts.shape) ** 2
        return float(np.sum(half * (vals @ self._GL_W)))

    def solve_t_for_volume(self, H, radii, D) -> float:
        plate_area = math.pi * (D / 2.0) ** 2
        return (self.cfg.volume - self.shaft_volume(H, radii)) / plate_area

    # -- full evaluation ---------------------------------------------------
    def evaluate(self, H: float, radii: np.ndarray, D: float, t: float) -> ProfileEvaluation:
        cfg = self.cfg
        mat = cfg.material
        radii = np.asarray(radii, dtype=float)
        rf = self.radius_fn(H, radii)
        rho_g = mat.rho * cfg.g
        P, F, T = cfg.loads.P, cfg.loads.F, cfg.loads.T

        mesh = fem.build_mesh(H, rf, mat.E, rho_g, cfg.profile.nel)
        K, KG, _Nc = fem.assemble(mesh, P)
        nel = cfg.profile.nel

        # buckling
        if cfg.buckling:
            lam = fem.buckling_factor(K, KG, nel)
        else:
            lam = math.inf

        # deflection & second-order moment
        if cfg.deflection:
            w_nodes = fem.deflection(K, KG, mesh, F)
            if w_nodes is None:  # unstable / past buckling
                w_nodes = np.full(nel + 1, np.inf)
        else:
            w_nodes = np.zeros(nel + 1)

        if np.all(np.isfinite(w_nodes)):
            delta_tip = abs(w_nodes[-1])
            M_nodes = fem.bending_moment(mesh, w_nodes, F, P)
        else:
            delta_tip = math.inf
            M_nodes = fem.bending_moment(mesh, np.zeros(nel + 1), F, P)

        # nodal section properties and axial force
        z_nodes = mesh.z_nodes
        r_nodes = rf(z_nodes)
        A_nodes = math.pi * r_nodes**2
        seg_w = mesh.w_line * mesh.L
        # weight above each node = sum of element weights at/above it
        w_above = np.array([seg_w[j:].sum() for j in range(nel + 1)])
        N_nodes = P + w_above

        # pointwise yield stress
        sigma_nodes = N_nodes / A_nodes + 4.0 * np.abs(M_nodes) / (math.pi * r_nodes**3)
        util = sigma_nodes / mat.sigma_y
        p = cfg.profile.p_norm
        sigma_pnorm = float(np.sum(util**p) ** (1.0 / p))
        sigma_max = float(util.max())

        # base plate quantities
        shaft_vol = self.shaft_volume(H, radii, rf=rf)
        plate_vol = math.pi * (D / 2.0) ** 2 * t
        W = rho_g * (shaft_vol + plate_vol)
        N_soil = P + W
        N_shaft_base = P + rho_g * shaft_vol
        M_ot = F * H
        r_base = float(r_nodes[0])

        ot = overturning.overturning(N_soil, M_ot, D, cfg.soil.q_allow, cfg.conservative)
        ot_kern = overturning.overturning(N_soil, M_ot, D, cfg.soil.q_allow, True)
        q_max = bearing.elastic_peak_pressure(N_soil, D, ot.e)
        if cfg.conservative:
            bearing_margin = C.margin_bearing(q_max, cfg.soil.q_allow)
        else:
            frac = bearing.contact_area_fraction(N_soil, D, cfg.soil.q_allow)
            bearing_margin = 1.0 - frac

        tau = stress.combined_shear_stress(
            F, T, r_base, math.pi * r_base**2, math.pi * r_base**4 / 2
        )
        tau_y = stress.shear_yield(mat.sigma_y)
        tau_punch = stress.punching_shear_stress(N_shaft_base, r_base, t)
        q_avg = bearing.average_pressure(N_soil, D)
        sigma_plate = stress.plate_bending_stress(q_avg, D / 2.0, r_base, t)

        margins: dict[str, float] = {
            "yield": 1.0 - sigma_pnorm,
            "shear": C.margin_shear(tau, tau_y),
            "punching": C.margin_punching(tau_punch, tau_y),
            "plate_bending": C.margin_plate_bending(sigma_plate, mat.sigma_y),
            "overturning": C.margin_overturning(ot.M_applied, ot.M_cap),
            "bearing": bearing_margin,
        }
        if cfg.buckling:
            margins["buckling"] = C.margin_buckling(lam, cfg.safety.buckling_SF)
        if cfg.deflection:
            margins["deflection"] = C.margin_deflection(delta_tip, H, cfg.safety.defl_ratio)

        return ProfileEvaluation(
            H=H, xi=self.xi, radii=radii, D=D, t=t,
            volume=shaft_vol + plate_vol, shaft_volume=shaft_vol, weight=W,
            lam_buckle=lam, delta_tip=delta_tip,
            sigma_max=sigma_max, sigma_pnorm=sigma_pnorm,
            z_nodes=z_nodes, sigma_nodes=sigma_nodes,
            overturn=ot, overturn_kern=ot_kern, margins=margins,
        )
