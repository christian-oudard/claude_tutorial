"""SLSQP multistart optimizer for the two-cylinder post.

Maximise the standoff height ``H = h`` subject to the fixed metal budget and
all structural / stability / serviceability constraints.

Design choices (per spec "known traps"):

* **Nondimensionalisation.**  Lengths are scaled by ``L0 = V^(1/3)`` before
  they reach SLSQP so the Jacobian is well conditioned (trap 2).
* **Volume equality eliminated.**  The plate thickness ``t`` is solved from the
  metal budget, so the equality never enters SLSQP as a badly scaled row; the
  gauge floor ``t >= t_min`` re-enters as a clean inequality.
* **Log-space radii.**  ``r`` and ``D`` are optimised in log space so they stay
  positive and thin members near their bounds behave (trap 3).
* **Explicit feasibility re-verification.**  SLSQP happily reports "success" on
  slightly infeasible points near a boundary (trap 1); every candidate is
  re-evaluated with the full model and rejected unless every margin clears
  ``-feas_tol``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

from .config import PostConfig
from .model import PostEvaluation, PostModel


@dataclass
class OptimizeResult:
    success: bool
    evaluation: PostEvaluation | None
    H: float
    n_feasible_starts: int
    n_starts: int
    message: str


class PostOptimizer:
    def __init__(self, config: PostConfig):
        self.cfg = config
        self.model = PostModel(config)
        self.L0 = config.volume ** (1.0 / 3.0)

    # -- reduced <-> physical ---------------------------------------------
    def _physical(self, x: np.ndarray) -> tuple[float, float, float, float]:
        """Reduced vector ``[ln(r/L0), h/L0, ln(D/L0)]`` -> ``(r, h, D, t)``."""
        r = math.exp(x[0]) * self.L0
        h = x[1] * self.L0
        D = math.exp(x[2]) * self.L0
        t = self.model.solve_t_for_volume(r, h, D)
        return r, h, D, t

    # -- objective & constraints ------------------------------------------
    def _neg_height(self, x: np.ndarray) -> float:
        return -x[1]  # maximise h/L0

    def _constraint_vector(self, x: np.ndarray) -> np.ndarray:
        r, h, D, t = self._physical(x)
        gvals: list[float] = []
        # gauge floor on the derived plate thickness
        gvals.append(t / self.cfg.solver.t_min - 1.0)
        # all structural margins
        try:
            ev = self.model.evaluate(r, h, D, t)
            gvals.extend(ev.margins.values())
        except (ValueError, ZeroDivisionError, FloatingPointError):
            gvals.extend([-1e6] * 8)
        # Clamp non-finite margins so SLSQP's finite differences stay valid
        # (an unstable geometry can send yield/deflection margins to -inf).
        return np.nan_to_num(
            np.array(gvals, dtype=float), nan=-1e6, posinf=1e6, neginf=-1e6
        )

    # -- one SLSQP run -----------------------------------------------------
    def _run_once(self, x0: np.ndarray) -> tuple[np.ndarray, bool]:
        cfg = self.cfg.solver
        bounds = [
            (math.log(self.cfg.solver.r_min / self.L0), math.log(2.0)),
            (1e-3, 500.0),
            (math.log(1e-3), math.log(10.0)),
        ]
        res = minimize(
            self._neg_height,
            x0,
            method="SLSQP",
            bounds=bounds,
            constraints=[{"type": "ineq", "fun": self._constraint_vector}],
            options={"maxiter": cfg.maxiter, "ftol": cfg.ftol},
        )
        return res.x, res.success

    # -- feasibility re-verification --------------------------------------
    def _verify(self, x: np.ndarray) -> PostEvaluation | None:
        r, h, D, t = self._physical(x)
        if t < self.cfg.solver.t_min * (1.0 - self.cfg.solver.feas_tol):
            return None
        if r < self.cfg.solver.r_min * (1.0 - self.cfg.solver.feas_tol):
            return None
        try:
            ev = self.model.evaluate(r, h, D, t)
        except (ValueError, ZeroDivisionError, FloatingPointError):
            return None
        if ev.min_margin() < -self.cfg.solver.feas_tol:
            return None
        return ev

    # -- multistart --------------------------------------------------------
    def _sample_start(self, rng: np.random.Generator) -> np.ndarray:
        lr = rng.uniform(math.log(self.cfg.solver.r_min / self.L0), math.log(0.6))
        lh = rng.uniform(math.log(0.5), math.log(200.0))
        lD = rng.uniform(math.log(0.05), math.log(5.0))
        return np.array([lr, math.exp(lh), lD])

    def optimize(self) -> OptimizeResult:
        rng = np.random.default_rng(self.cfg.solver.seed)
        best: PostEvaluation | None = None
        n_feasible = 0
        n = self.cfg.solver.multistart
        for _ in range(n):
            x0 = self._sample_start(rng)
            try:
                x, _ok = self._run_once(x0)
            except Exception:
                continue
            ev = self._verify(x)
            if ev is None:
                continue
            n_feasible += 1
            if best is None or ev.H > best.H:
                best = ev
        if best is None:
            return OptimizeResult(
                False, None, 0.0, 0, n, "no feasible solution found"
            )
        return OptimizeResult(
            True, best, best.H, n_feasible, n, "ok"
        )
