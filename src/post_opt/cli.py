"""Command-line interface for the axisymmetric post optimizer.

    post-opt run    config.toml [-o result.json]
    post-opt sweep  config.toml --param F --values 0.1,0.5,1,2 [-o out.json]
    post-opt audit  result.json
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import json
import sys

from .config import PostConfig
from .optimize import PostOptimizer
from .results import evaluation_to_dict, result_to_dict


def _load_config(path: str | None) -> PostConfig:
    return PostConfig.from_toml(path) if path else PostConfig()


def _with_param(cfg: PostConfig, param: str, value: float) -> PostConfig:
    """Return a copy of ``cfg`` with a (possibly nested) parameter overridden."""
    d = cfg.to_dict()
    nested_keys = {
        "F": ("loads", "F"), "P": ("loads", "P"), "T": ("loads", "T"),
        "mass": ("mass",), "g": ("g",),
        "q_allow": ("soil", "q_allow"),
        "E": ("material", "E"), "sigma_y": ("material", "sigma_y"),
        "rho": ("material", "rho"),
    }
    if param not in nested_keys:
        raise SystemExit(f"unknown sweep param: {param!r}")
    keys = nested_keys[param]
    node = d
    for k in keys[:-1]:
        node = node[k]
    node[keys[-1]] = value
    return PostConfig.from_dict(d)


def _print_summary(cfg: PostConfig, res, out=sys.stdout) -> None:
    if not res.success:
        print(f"[{cfg.name}] NO FEASIBLE SOLUTION ({res.message})", file=out)
        return
    ev = res.evaluation
    g = ev.geom
    print(f"[{cfg.name}] H = {res.H:.4f} m  "
          f"(feasible starts {res.n_feasible_starts}/{res.n_starts})", file=out)
    print(f"  geometry: r={g.r*1e3:.3f} mm  h={g.h:.4f} m  "
          f"D={g.D:.4f} m  t={g.t*1e3:.3f} mm", file=out)
    print(f"  overturning model: {ev.overturn.model}  "
          f"(kern M_cap={ev.overturn_kern.M_cap:.4g} N*m)", file=out)
    print(f"  active set: {', '.join(ev.active_set()) or '(none)'}", file=out)
    for k, v in ev.margins.items():
        flag = " <-- active" if abs(v) <= 1e-3 else ""
        print(f"    {k:14s} {v:+.4f}{flag}", file=out)


def cmd_run(args) -> int:
    cfg = _load_config(args.config)
    res = PostOptimizer(cfg).optimize()
    _print_summary(cfg, res)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(result_to_dict(res, cfg), fh, indent=2)
        print(f"  wrote {args.output}")
    return 0 if res.success else 1


def cmd_sweep(args) -> int:
    cfg = _load_config(args.config)
    values = [float(v) for v in args.values.split(",")]
    records = []
    for val in values:
        scfg = _with_param(cfg, args.param, val)
        res = PostOptimizer(scfg).optimize()
        print(f"{args.param}={val:g}: H={res.H:.4f} m  "
              f"active={res.evaluation.active_set() if res.evaluation else 'INFEASIBLE'}")
        records.append({
            "param": args.param, "value": val,
            **result_to_dict(res, scfg),
        })
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(records, fh, indent=2)
        print(f"wrote {args.output}")
    return 0


def cmd_audit(args) -> int:
    from importlib import import_module

    audit = import_module("post_opt.audit")
    ok = audit.audit_file(args.result)
    return 0 if ok else 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="post-opt", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("run", help="optimize a single configuration")
    pr.add_argument("config", nargs="?", help="TOML config (defaults if omitted)")
    pr.add_argument("-o", "--output", help="write result JSON here")
    pr.set_defaults(func=cmd_run)

    ps = sub.add_parser("sweep", help="sweep one parameter")
    ps.add_argument("config", nargs="?")
    ps.add_argument("--param", required=True, help="F,P,T,mass,g,q_allow,E,sigma_y,rho")
    ps.add_argument("--values", required=True, help="comma-separated values")
    ps.add_argument("-o", "--output", help="write records JSON here")
    ps.set_defaults(func=cmd_sweep)

    pa = sub.add_parser("audit", help="re-verify a result JSON independently")
    pa.add_argument("result", help="result JSON from `run`")
    pa.set_defaults(func=cmd_audit)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
