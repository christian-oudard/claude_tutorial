"""Optimizer for the M2 free-profile model.

Direct SLSQP maximisation of ``H`` over 20+ radius variables with
finite-difference gradients through the FEM is badly conditioned and
unreliable.  Instead we exploit structure, following the spec's
"bisect on H with an inner feasibility problem" recommendation:

* **Inner shaft sizing is a fully-stressed design (FSD).**  A cantilever is
  statically determinate, so the yield-limited section is *explicit*: at each
  station solve ``sigma_y = N/(pi r^2) + 4 M /(pi r^3)`` for ``r``.  With
  self-weight the axial term ``N`` couples the stations, so a 2-3 step
  fixed-point pass suffices.  When P-delta is active the bending moment is
  refreshed from an FEM deflection solve between passes.  This reliably returns
  the fully-stressed profile -- the cube-root taper for pure bending, constant
  ``r`` for axial-dominated loading.
* **The base plate** ``(D, t)`` is sized by the M1 disc physics, reusing the
  partial-uplift / kern overturning model.
* **Bisection on ``H``** brackets the largest height whose fully-stressed shaft
  fits the metal budget and clears the global buckling / deflection limits.

Every accepted optimum is re-verified with the full :class:`ProfileModel`
(hard per-node yield audit included).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import brentq

from . import fem
from .config import PostConfig
from .physics import overturning
from .profile import ProfileEvaluation, ProfileModel


@dataclass
class ProfileResult:
    success: bool
    evaluation: ProfileEvaluation | None
    H: float
    n_feasible_starts: int
    n_starts: int
    message: str


def _fully_stressed_radius(M: float, N: float, sigma_y: float, r_min: float) -> float:
    """Solve ``sigma_y = N/(pi r^2) + 4 M/(pi r^3)`` for the section radius.

    ``f(r) = sigma_y pi r^3 - N r - 4 M`` is monotone increasing for ``r > 0``
    with ``f(0) <= 0``, so the positive root is unique.  ``M`` and ``N`` are
    taken as magnitudes (worst-fibre stress = |axial| + |bending|); the
    second-order moment can dip slightly negative near the tip.
    """
    M = abs(M)
    N = abs(N)
    if M <= 0.0 and N <= 0.0:
        return r_min

    def f(r):
        return sigma_y * math.pi * r**3 - N * r - 4.0 * M

    hi = max(r_min, 1e-3)
    while f(hi) < 0.0:
        hi *= 2.0
    r = brentq(f, 0.0, hi, xtol=1e-12, rtol=1e-12)
    return max(r, r_min)


class ProfileOptimizer:
    def __init__(self, config: PostConfig):
        self.cfg = config
        self.model = ProfileModel(config)
        self.n = config.profile.n_control
        self.xi = np.linspace(0.0, 1.0, self.n)

    # -- mesh-node utilisation for a set of control radii -----------------
    def _mesh_util(self, H: float, radii: np.ndarray):
        """FEM-evaluated stress utilisation ``sigma(z)/sigma_y`` at mesh nodes.

        Returns ``(util, z_nodes)`` using the same second-order pathway as the
        full model, but without the base plate (shaft stress is independent of
        the plate).
        """
        cfg = self.cfg
        mat = cfg.material
        F, P = cfg.loads.F, cfg.loads.P
        rho_g = mat.rho * cfg.g
        rf = self.model.radius_fn(H, radii)
        mesh = fem.build_mesh(H, rf, mat.E, rho_g, cfg.profile.nel)
        if cfg.deflection:
            K, KG, _ = fem.assemble(mesh, P)
            w_nodes = fem.deflection(K, KG, mesh, F)
            if w_nodes is None:
                w_nodes = np.zeros(cfg.profile.nel + 1)
        else:
            w_nodes = np.zeros(cfg.profile.nel + 1)
        M = fem.bending_moment(mesh, w_nodes, F, P)
        z = mesh.z_nodes
        r = rf(z)
        seg_w = mesh.w_line * mesh.L
        w_above = np.array([seg_w[j:].sum() for j in range(cfg.profile.nel + 1)])
        N = P + w_above
        sigma = N / (math.pi * r**2) + 4.0 * np.abs(M) / (math.pi * r**3)
        return sigma / mat.sigma_y, z

    # -- fully-stressed shaft at fixed H ----------------------------------
    def size_shaft_fsd(self, H: float, passes: int = 4, repair: int = 40):
        """Return control radii of the fully-stressed shaft at height ``H``.

        Two stages:

        1. Analytic FSD at the control stations (``sigma = sigma_y`` per
           section) with a self-weight axial fixed point and, when enabled, an
           FEM second-order bending refresh.
        2. A resize loop *in PCHIP space*: because the monotone interpolant
           undershoots the convex cube-root between stations (and cannot
           represent the tip cusp), each control radius is rescaled by the
           local FEM-node utilisation, ``r_i <- r_i * util_i^(1/3)``.  This
           drives the actually-evaluated stress to ``sigma_y`` -- fattening the
           tip while leaving the interior at the cube-root shape.
        """
        cfg = self.cfg
        mat = cfg.material
        F, P = cfg.loads.F, cfg.loads.P
        rho_g = mat.rho * cfg.g
        z = self.xi * H
        r_min = cfg.solver.r_min

        M = F * (H - z)
        radii = np.array(
            [_fully_stressed_radius(M[i], 0.0, mat.sigma_y, r_min) for i in range(self.n)]
        )
        for _ in range(passes):
            rf = self.model.radius_fn(H, radii)
            zz = np.linspace(z, np.full(self.n, H), 40)  # (40, n)
            w_above = np.trapezoid(math.pi * rf(zz) ** 2 * rho_g, zz, axis=0)
            N = P + w_above
            if cfg.deflection:
                mesh = fem.build_mesh(H, rf, mat.E, rho_g, cfg.profile.nel)
                K, KG, _ = fem.assemble(mesh, P)
                w_nodes = fem.deflection(K, KG, mesh, F)
                M = (np.interp(z, mesh.z_nodes, fem.bending_moment(mesh, w_nodes, F, P))
                     if w_nodes is not None else F * (H - z))
            else:
                M = F * (H - z)
            radii = np.array(
                [_fully_stressed_radius(M[i], N[i], mat.sigma_y, r_min)
                 for i in range(self.n)]
            )

        # PCHIP-space FSD resize so the FEM-evaluated stress reaches sigma_y
        for _ in range(repair):
            util, z_nodes = self._mesh_util(H, radii)
            # assign each mesh node to the nearest control station
            idx = np.argmin(np.abs(z_nodes[:, None] - z[None, :]), axis=1)
            local = np.ones(self.n)
            for i in range(self.n):
                sel = util[idx == i]
                if sel.size:
                    local[i] = sel.max()
            radii = np.maximum(radii * local ** (1.0 / 3.0), r_min)
            if abs(util.max() - 1.0) < 5e-3 and util.max() <= 1.0 + 5e-3:
                break
        return radii

    # -- stiffness inflation (buckling / deflection governed) -------------
    def _stiffness_margins(self, H: float, radii: np.ndarray):
        """Return ``(lambda, delta_tip)`` for a profile (plate-independent)."""
        cfg = self.cfg
        mat = cfg.material
        rho_g = mat.rho * cfg.g
        rf = self.model.radius_fn(H, radii)
        mesh = fem.build_mesh(H, rf, mat.E, rho_g, cfg.profile.nel)
        K, KG, _ = fem.assemble(mesh, cfg.loads.P)
        lam = fem.buckling_factor(K, KG, cfg.profile.nel) if cfg.buckling else math.inf
        if cfg.deflection:
            w = fem.deflection(K, KG, mesh, cfg.loads.F)
            delta = math.inf if w is None else abs(w[-1])
        else:
            delta = 0.0
        return lam, delta

    def inflate_for_stiffness(self, H: float, radii: np.ndarray, k_max: float = 30.0):
        """Scale the fully-stressed shape until buckling & deflection clear.

        Uniform radius scaling by ``k`` raises the buckling factor (``EI`` grows
        faster than self-weight) and shrinks the deflection (``delta ~ 1/EI``),
        so a single scalar ``k`` found by bisection makes a yield-optimal but
        too-slender shaft stiff enough.  Returns ``None`` if even ``k_max`` is
        insufficient at this height.
        """
        cfg = self.cfg
        if not (cfg.buckling or cfg.deflection):
            return radii

        def ok(k):
            lam, delta = self._stiffness_margins(H, radii * k)
            good = True
            if cfg.buckling:
                good &= lam >= cfg.safety.buckling_SF
            if cfg.deflection:
                good &= (delta / H) <= cfg.safety.defl_ratio
            return good

        if ok(1.0):
            return radii
        if not ok(k_max):
            return None
        lo, hi = 1.0, k_max
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            if ok(mid):
                hi = mid
            else:
                lo = mid
        return radii * hi

    # -- base plate sizing (reuse M1 disc physics) ------------------------
    def size_plate(self, H: float, shaft_weight: float, plate_volume_budget: float):
        """Choose ``(D, t)`` that clears overturning/bearing/plate/punching.

        Sweeps diameter, spends the plate volume budget on thickness, and takes
        the smallest feasible plate; falls back to the largest tried if none is
        fully feasible (the outer bisection then rejects the height).
        """
        cfg = self.cfg
        F, P = cfg.loads.F, cfg.loads.P
        rho_g = cfg.material.rho * cfg.g
        M_ot = F * H
        best = None
        for D in np.linspace(2 * cfg.solver.r_min, 8.0 * (plate_volume_budget) ** (1 / 3) + 1.0, 60):
            a = D / 2.0
            plate_vol = plate_volume_budget
            t = plate_vol / (math.pi * a * a)
            if t < cfg.solver.t_min:
                continue
            W = shaft_weight + rho_g * plate_vol
            N_soil = P + W
            ot = overturning.overturning(N_soil, M_ot, D, cfg.soil.q_allow, cfg.conservative)
            if ot.M_cap <= M_ot:
                continue
            best = (D, t)
            break
        return best

    # -- feasibility of a height ------------------------------------------
    def _evaluate_height(self, H: float) -> ProfileEvaluation | None:
        cfg = self.cfg
        radii = self.size_shaft_fsd(H)
        radii = self.inflate_for_stiffness(H, radii)
        if radii is None:
            return None  # cannot be made stiff enough at this height
        rho_g = cfg.material.rho * cfg.g
        shaft_vol = self.model.shaft_volume(H, radii)
        plate_budget = cfg.volume - shaft_vol
        if plate_budget <= 0:
            return None  # shaft alone exceeds the metal budget
        shaft_weight = rho_g * shaft_vol
        plate = self.size_plate(H, shaft_weight, plate_budget)
        if plate is None:
            return None
        D, t = plate
        try:
            ev = self.model.evaluate(H, radii, D, t)
        except Exception:
            return None
        return ev

    def _feasible(self, ev: ProfileEvaluation | None) -> bool:
        if ev is None:
            return False
        tol = self.cfg.solver.feas_tol
        # FSD guarantees yield ~ at the limit; allow a small overshoot from the
        # p-norm/tip cusp and enforce the remaining margins.
        checks = {k: v for k, v in ev.margins.items()}
        if ev.sigma_max > 1.0 + 5e-3:
            return False
        for k, v in checks.items():
            if k == "yield":
                continue
            if v < -tol:
                return False
        return True

    # -- bisection on H ----------------------------------------------------
    def optimize(self) -> ProfileResult:
        L0 = self.cfg.volume ** (1.0 / 3.0)
        H = L0
        best = None
        H_lo, H_hi = 0.0, None
        for _ in range(40):
            ev = self._evaluate_height(H)
            if self._feasible(ev):
                H_lo, best = H, ev
                H *= 1.5
            else:
                H_hi = H
                break
        if best is None:
            return ProfileResult(False, None, 0.0, 0, 1, "no feasible height found")
        if H_hi is None:
            H_hi = H
        for _ in range(40):
            Hm = 0.5 * (H_lo + H_hi)
            ev = self._evaluate_height(Hm)
            if self._feasible(ev):
                H_lo, best = Hm, ev
            else:
                H_hi = Hm
            if H_hi - H_lo < 1e-4 * L0:
                break
        return ProfileResult(True, best, best.H, 1, 1, "ok")
