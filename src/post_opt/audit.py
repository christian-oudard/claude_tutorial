"""Independent constraint audit.

Recomputes every constraint margin directly from the reported geometry using
first-principles formulas written out *here* -- deliberately not calling
``model.evaluate`` -- then checks feasibility and cross-checks against the
margins stored in the result JSON.  This is the offline guard required by the
spec: an optimum is only trustworthy if an independent recomputation agrees.
"""

from __future__ import annotations

import json
import math

from .config import PostConfig

SQRT3 = math.sqrt(3.0)
GREENHILL = 7.8373


def audit_geometry(cfg: PostConfig, r: float, h: float, D: float, t: float) -> dict:
    """Recompute all margins from scratch. Returns ``{name: margin}``."""
    mat, g = cfg.material, cfg.g
    a = D / 2.0
    A = math.pi * r * r
    I = math.pi * r**4 / 4.0
    J = math.pi * r**4 / 2.0
    S = math.pi * r**3 / 4.0
    F, P, T = cfg.loads.F, cfg.loads.P, cfg.loads.T

    shaft_vol = A * h
    plate_vol = math.pi * a * a * t
    W = mat.rho * g * (shaft_vol + plate_vol)
    W_shaft = mat.rho * g * shaft_vol
    w_line = mat.rho * g * A

    N_shaft = P + W_shaft
    N_soil = P + W

    # buckling (Dunkerley of Greenhill + Euler)
    if cfg.buckling and w_line > 0 and h > 0:
        lam_self = GREENHILL * mat.E * I / (w_line * h**3)
        inv = 1.0 / lam_self
        if P > 0:
            inv += P / (math.pi**2 * mat.E * I / (4 * h**2))
        lam = 1.0 / inv
    else:
        lam = math.inf
    AF = math.inf if lam <= 1.0 else lam / (lam - 1.0)

    # second-order moment / deflection
    delta0 = F * h**3 / (3 * mat.E * I)
    if cfg.deflection:
        if not math.isfinite(AF):
            delta, M_base = math.inf, math.inf
        else:
            delta = delta0 * AF
            M_base = F * h + N_shaft * delta
    else:
        delta, M_base = delta0, F * h

    # stresses
    sigma = abs(N_shaft) / A + abs(M_base) / S
    tau = 4 * abs(F) / (3 * A) + (abs(T) * r / J if T else 0.0)
    tau_y = mat.sigma_y / SQRT3
    tau_punch = abs(N_shaft) / (2 * math.pi * r * t)
    q_avg = N_soil / (math.pi * a * a)
    sigma_plate = 3 * q_avg * max(a - r, 0.0) ** 2 / (t * t)

    # overturning
    M_ot = F * h
    e = M_ot / N_soil if N_soil > 0 else math.inf
    if cfg.conservative:
        M_cap = N_soil * D / 8.0
        q_max = (N_soil / (math.pi * a * a)) * (1 + 8 * e / D)
        bearing_margin = 1.0 - q_max / cfg.soil.q_allow
    else:
        A_c = N_soil / cfg.soil.q_allow
        plate_area = math.pi * a * a
        if A_c >= plate_area:
            M_cap = 0.0
        else:
            # chord offset by bisection (matches overturning module)
            lo, hi = 0.0, a
            for _ in range(80):
                mid = 0.5 * (lo + hi)
                seg = a * a * math.acos(mid / a) - mid * math.sqrt(
                    max(a * a - mid * mid, 0.0)
                )
                if seg > A_c:
                    lo = mid
                else:
                    hi = mid
            p = 0.5 * (lo + hi)
            M_cap = cfg.soil.q_allow * (2.0 / 3.0) * (a * a - p * p) ** 1.5
        bearing_margin = 1.0 - A_c / (math.pi * a * a)

    margins = {
        "yield": 1.0 - sigma / mat.sigma_y,
        "shear": 1.0 - tau / tau_y,
        "punching": 1.0 - tau_punch / tau_y,
        "plate_bending": 1.0 - sigma_plate / mat.sigma_y,
        "overturning": (-1e6 if M_cap <= 0 else 1.0 - M_ot / M_cap),
        "bearing": bearing_margin,
    }
    if cfg.buckling:
        margins["buckling"] = (
            1e6 if not math.isfinite(lam) else lam / cfg.safety.buckling_SF - 1.0
        )
    if cfg.deflection:
        margins["deflection"] = (
            -1e6 if not math.isfinite(delta)
            else 1.0 - (delta / h) / cfg.safety.defl_ratio
        )
    return margins


def audit_file(path: str, tol: float = 1e-3) -> bool:
    with open(path, "rb") as fh:
        data = json.load(fh)
    cfg = PostConfig.from_dict(data["config"])
    if "result" not in data:
        print("audit: result has no feasible solution to check")
        return False
    geo = data["result"]["geometry"]
    stored = data["result"]["margins"]
    recomputed = audit_geometry(cfg, geo["r"], geo["h"], geo["D"], geo["t"])

    ok = True
    print(f"audit of {path}:  H = {geo['H']:.4f} m")
    print(f"  {'constraint':16s} {'stored':>12s} {'recomputed':>12s} {'status':>8s}")
    for name, rec in recomputed.items():
        st = stored.get(name, float("nan"))
        agree = math.isclose(rec, st, rel_tol=1e-3, abs_tol=1e-4) or (
            rec > 100 and st > 100
        )
        feasible = rec >= -tol
        status = "OK" if (agree and feasible) else ("VIOL" if not feasible else "MISMATCH")
        if status != "OK":
            ok = False
        print(f"  {name:16s} {st:12.4f} {rec:12.4f} {status:>8s}")
    # volume budget
    a = geo["D"] / 2.0
    vol = math.pi * geo["r"] ** 2 * geo["h"] + math.pi * a * a * geo["t"]
    vol_err = abs(vol - cfg.volume) / cfg.volume
    print(f"  volume budget error: {vol_err:.2e}")
    if vol_err > 1e-3:
        ok = False
    print(f"  RESULT: {'PASS' if ok else 'FAIL'}")
    return ok
