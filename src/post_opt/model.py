"""The two-cylinder post model: geometry -> all constraint margins.

This is the single place that turns the four design variables
``(r, h, D, t)`` plus a :class:`PostConfig` into a full structural evaluation:
weights, forces, stresses, and every named constraint margin.  The optimizer
consumes :meth:`PostModel.evaluate`; it holds no solver state itself, keeping
physics and optimization cleanly separated (spec engineering requirement).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import constraints as C
from .config import PostConfig
from .physics import bearing, buckling, deflection, geometry, overturning, stress


@dataclass
class PostEvaluation:
    """Everything computed for one geometry."""

    geom: geometry.TwoCylinder
    H: float
    volume: float
    weight: float
    # forces at the shaft base
    N_shaft: float  # axial through the shaft (P + shaft self weight)
    N_soil: float  # vertical on the soil (P + total weight)
    M_base: float  # second-order base bending moment
    M_base_1st: float  # first-order base moment (F h)
    # intermediate quantities
    sigma: float
    tau: float
    tau_punch: float
    sigma_plate: float
    q_max: float
    lam_buckle: float
    amplification: float
    delta: float
    overturn: overturning.OverturnResult
    overturn_kern: overturning.OverturnResult
    margins: dict[str, float] = field(default_factory=dict)

    @property
    def feasible(self) -> bool:
        return all(m >= 0.0 for m in self.margins.values())

    def min_margin(self) -> float:
        return min(self.margins.values()) if self.margins else 0.0

    def active_set(self, tol: float = 1e-3) -> list[str]:
        """Names of constraints within ``tol`` of binding."""
        return [k for k, v in self.margins.items() if abs(v) <= tol]


class PostModel:
    def __init__(self, config: PostConfig):
        self.cfg = config

    # -- volume residual (equality constraint) ----------------------------
    def volume_residual(self, r: float, h: float, D: float, t: float) -> float:
        g = geometry.TwoCylinder(r, h, D, t)
        return g.volume - self.cfg.volume

    def solve_t_for_volume(self, r: float, h: float, D: float) -> float:
        """Plate thickness that exactly satisfies the metal budget."""
        import math

        plate_area = math.pi * (D / 2.0) ** 2
        shaft_vol = math.pi * r * r * h
        return (self.cfg.volume - shaft_vol) / plate_area

    # -- full evaluation ---------------------------------------------------
    def evaluate(self, r: float, h: float, D: float, t: float) -> PostEvaluation:
        cfg = self.cfg
        mat = cfg.material
        g = geometry.TwoCylinder(r, h, D, t)

        W = geometry.total_weight(g, mat.rho, cfg.g)
        W_shaft = geometry.shaft_weight(g, mat.rho, cfg.g)
        w_line = geometry.weight_per_length(g, mat.rho, cfg.g)

        P = cfg.loads.P
        F = cfg.loads.F
        T = cfg.loads.T
        H = g.standoff

        # axial forces
        N_shaft = P + W_shaft
        N_soil = P + W

        # buckling eigenvalue and amplification (drives P-delta)
        if cfg.buckling:
            lam = buckling.combined_lambda(mat.E, g.I, w_line, P, h)
        else:
            lam = float("inf")
        AF = buckling.amplification_factor(lam)

        # second-order deflection and base moment
        if cfg.deflection:
            defl = deflection.second_order(
                F, h, mat.E, g.I, N_shaft, AF, iters=cfg.solver.pdelta_iters
            )
            M_base = defl.moment2
            delta = defl.delta
        else:
            # first-order only: v1 regression path
            M_base = F * h
            delta = deflection.first_order_deflection(F, h, mat.E, g.I)

        M_base_1st = F * h

        # stresses
        sigma = stress.normal_stress(N_shaft, M_base, g.area, g.section_modulus)
        tau = stress.combined_shear_stress(F, T, r, g.area, g.J)
        tau_punch = stress.punching_shear_stress(N_shaft, r, t)
        q_avg = bearing.average_pressure(N_soil, D)
        sigma_plate = stress.plate_bending_stress(q_avg, g.plate_radius, r, t)
        tau_y = stress.shear_yield(mat.sigma_y)

        # overturning: always compute both models; enforce the selected one
        ot = overturning.overturning(
            N_soil, M_base_1st, D, cfg.soil.q_allow, conservative=cfg.conservative
        )
        ot_kern = overturning.overturning(
            N_soil, M_base_1st, D, cfg.soil.q_allow, conservative=True
        )
        q_max = bearing.elastic_peak_pressure(N_soil, D, ot.e)

        # Bearing / vertical-support margin depends on the soil model:
        #  * kern (elastic): elastic peak pressure must clear q_allow
        #  * partial uplift (plastic): the plastic contact area must fit
        if cfg.conservative:
            bearing_margin = C.margin_bearing(q_max, cfg.soil.q_allow)
        else:
            frac = bearing.contact_area_fraction(N_soil, D, cfg.soil.q_allow)
            bearing_margin = 1.0 - frac

        margins: dict[str, float] = {
            "yield": C.margin_yield(sigma, mat.sigma_y),
            "shear": C.margin_shear(tau, tau_y),
            "punching": C.margin_punching(tau_punch, tau_y),
            "plate_bending": C.margin_plate_bending(sigma_plate, mat.sigma_y),
            "overturning": C.margin_overturning(ot.M_applied, ot.M_cap),
            "bearing": bearing_margin,
        }
        if cfg.buckling:
            margins["buckling"] = C.margin_buckling(lam, cfg.safety.buckling_SF)
        if cfg.deflection:
            margins["deflection"] = C.margin_deflection(
                delta, H, cfg.safety.defl_ratio
            )

        return PostEvaluation(
            geom=g,
            H=H,
            volume=g.volume,
            weight=W,
            N_shaft=N_shaft,
            N_soil=N_soil,
            M_base=M_base,
            M_base_1st=M_base_1st,
            sigma=sigma,
            tau=tau,
            tau_punch=tau_punch,
            sigma_plate=sigma_plate,
            q_max=q_max,
            lam_buckle=lam,
            amplification=AF,
            delta=delta,
            overturn=ot,
            overturn_kern=ot_kern,
            margins=margins,
        )
