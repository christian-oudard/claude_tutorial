"""Configuration for the axisymmetric post optimizer.

A single :class:`PostConfig` dataclass captures every fixed input to the
problem (material, loads, soil, safety factors, solver settings).  It is
serialised to / from TOML so a run is fully reproducible from one file.

Units are SI throughout: metres, kilograms, seconds, newtons, pascals.
"""

from __future__ import annotations

import sys
import tomllib
from dataclasses import asdict, dataclass, field, fields

if sys.version_info < (3, 11):  # pragma: no cover - project requires >= 3.12
    raise RuntimeError("post_opt requires Python >= 3.12")


@dataclass(frozen=True)
class Loads:
    """Quasi-static wrench applied at the top of the post."""

    F: float = 1.0  # lateral force, worst-case direction [N]
    P: float = 0.0  # axial force at the tip (compression +) [N]
    T: float = 0.0  # torsion [N*m]


@dataclass(frozen=True)
class Material:
    rho: float = 7850.0  # density [kg/m^3]  (mild steel)
    E: float = 200e9  # Young's modulus [Pa]
    sigma_y: float = 250e6  # yield stress [Pa]


@dataclass(frozen=True)
class Soil:
    q_allow: float = 150e3  # allowable bearing pressure [Pa]


@dataclass(frozen=True)
class Safety:
    buckling_SF: float = 2.0  # eigenvalue must exceed this
    defl_ratio: float = 0.02  # serviceability: delta/H <= this (epsilon)


@dataclass(frozen=True)
class Solver:
    seed: int = 12345
    multistart: int = 48  # number of random starts (>= 40 per spec)
    maxiter: int = 300
    ftol: float = 1e-9
    feas_tol: float = 1e-4  # margin tolerance when re-verifying feasibility
    pdelta_iters: int = 4  # fixed-point iterations for the second-order moment
    r_min: float = 1e-4  # minimum shaft radius [m] (fabrication gauge)
    t_min: float = 2e-4  # minimum plate thickness [m]


@dataclass(frozen=True)
class PostConfig:
    """Top-level configuration.

    ``mass`` and gravity fix the metal budget ``V = mass / rho``.
    ``conservative`` selects the kern overturning model instead of the
    partial-uplift model, and disables nothing else.
    ``deflection`` toggles the serviceability constraint (used by the v1
    regression, which predates it).
    """

    mass: float = 1.0  # fixed metal mass [kg]
    g: float = 9.81  # gravity [m/s^2]
    loads: Loads = field(default_factory=Loads)
    material: Material = field(default_factory=Material)
    soil: Soil = field(default_factory=Soil)
    safety: Safety = field(default_factory=Safety)
    solver: Solver = field(default_factory=Solver)
    conservative: bool = False  # kern overturning model + report both
    deflection: bool = True  # enforce the P-delta deflection constraint
    buckling: bool = True  # enforce the buckling eigenvalue constraint
    name: str = "post"

    # -- derived -----------------------------------------------------------
    @property
    def volume(self) -> float:
        """Fixed metal volume ``V = M / rho``."""
        return self.mass / self.material.rho

    # -- (de)serialisation -------------------------------------------------
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PostConfig":
        nested = {
            "loads": Loads,
            "material": Material,
            "soil": Soil,
            "safety": Safety,
            "solver": Solver,
        }
        kwargs: dict = {}
        for f in fields(cls):
            if f.name not in data:
                continue
            val = data[f.name]
            if f.name in nested and isinstance(val, dict):
                sub = nested[f.name]
                allowed = {sf.name for sf in fields(sub)}
                kwargs[f.name] = sub(**{k: v for k, v in val.items() if k in allowed})
            else:
                kwargs[f.name] = val
        return cls(**kwargs)

    @classmethod
    def from_toml(cls, path: str) -> "PostConfig":
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
        return cls.from_dict(data)

    def to_toml(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(self.to_toml_str())

    def to_toml_str(self) -> str:
        """Minimal TOML writer (stdlib has no writer)."""
        d = self.to_dict()
        lines: list[str] = []
        scalars = {k: v for k, v in d.items() if not isinstance(v, dict)}
        for k, v in scalars.items():
            lines.append(f"{k} = {_toml_val(v)}")
        for k, v in d.items():
            if isinstance(v, dict):
                lines.append("")
                lines.append(f"[{k}]")
                for kk, vv in v.items():
                    lines.append(f"{kk} = {_toml_val(vv)}")
        return "\n".join(lines) + "\n"


def _toml_val(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return f'"{v}"'
    if isinstance(v, float):
        return repr(v)
    return str(v)
