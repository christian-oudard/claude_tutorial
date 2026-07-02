"""Serialise an optimization result to the JSON schema from the spec.

The JSON captures geometry, the active set, every constraint margin, and solver
diagnostics so a result is fully auditable offline (see ``tools/audit.py``).
"""

from __future__ import annotations

import json
from typing import Any

from .config import PostConfig
from .model import PostEvaluation
from .optimize import OptimizeResult


def evaluation_to_dict(ev: PostEvaluation) -> dict[str, Any]:
    g = ev.geom
    return {
        "geometry": {
            "r": g.r,
            "h": g.h,
            "D": g.D,
            "t": g.t,
            "H": ev.H,
            "volume": ev.volume,
        },
        "forces": {
            "N_shaft": ev.N_shaft,
            "N_soil": ev.N_soil,
            "weight": ev.weight,
            "M_base_second_order": ev.M_base,
            "M_base_first_order": ev.M_base_1st,
        },
        "response": {
            "sigma": ev.sigma,
            "tau": ev.tau,
            "tau_punch": ev.tau_punch,
            "sigma_plate": ev.sigma_plate,
            "q_max": ev.q_max,
            "buckling_lambda": ev.lam_buckle,
            "amplification": ev.amplification,
            "tip_deflection": ev.delta,
        },
        "overturning": {
            "model": ev.overturn.model,
            "e": ev.overturn.e,
            "M_applied": ev.overturn.M_applied,
            "M_cap": ev.overturn.M_cap,
            "contact_area": ev.overturn.contact_area,
            "kern_M_cap": ev.overturn_kern.M_cap,
        },
        "margins": ev.margins,
        "active_set": ev.active_set(),
        "feasible": ev.feasible,
        "min_margin": ev.min_margin(),
    }


def result_to_dict(res: OptimizeResult, cfg: PostConfig) -> dict[str, Any]:
    out: dict[str, Any] = {
        "config": cfg.to_dict(),
        "solver": {
            "success": res.success,
            "message": res.message,
            "n_starts": res.n_starts,
            "n_feasible_starts": res.n_feasible_starts,
            "H": res.H,
        },
    }
    if res.evaluation is not None:
        out["result"] = evaluation_to_dict(res.evaluation)
    return out


def write_result(res: OptimizeResult, cfg: PostConfig, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(result_to_dict(res, cfg), fh, indent=2)


def dumps(res: OptimizeResult, cfg: PostConfig) -> str:
    return json.dumps(result_to_dict(res, cfg), indent=2)
