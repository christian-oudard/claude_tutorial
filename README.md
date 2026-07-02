# post-opt — axisymmetric post optimizer

Given a fixed metal mass, find the rotationally symmetric shape that stands a
load off the ground at **maximum standoff height** without failing
structurally, tipping, or exceeding soil bearing pressure.

This repository implements **Milestone M1** of the spec: the two-cylinder
`(r, h, D, t)` design with the full constraint set, a nondimensionalised
multistart SLSQP optimizer, config/results serialisation, a CLI, and an
independent audit tool. The physics / model / optimizer layers are separated so
the free-profile FEM of M2–M4 can slot in without touching the solver.

## Install

```bash
uv venv --python 3.13 .venv && source .venv/bin/activate
uv pip install -e '.[dev]'
```

or, with Nix:

```bash
nix develop      # dev shell with python + numpy + scipy + pytest
nix flake check  # builds the package and runs the test suite
```

## Use

```bash
post-opt run   configs/default.toml -o result.json
post-opt sweep configs/default.toml --param F --values 0.1,0.5,1,2,5
post-opt audit result.json          # independent re-verification
```

`run` prints the optimum geometry, the active constraint set, and every signed
margin. `--conservative` in the config switches overturning from the
partial-uplift model to the elastic kern model (both are always reported).

## The problem

Maximise `H` subject to a fixed metal volume `V = M / ρ` and:

| constraint      | model |
|-----------------|-------|
| `yield`         | `σ = N/A + M_b·c/I ≤ σ_y` at the shaft base (P-δ second-order moment) |
| `shear`         | transverse + torsion vs `τ_y = σ_y/√3` |
| `punching`      | shaft/plate junction punching shear |
| `plate_bending` | base-plate radial cantilever bending |
| `overturning`   | rigid-plastic **partial-uplift** contact (or elastic **kern** if `--conservative`) |
| `bearing`       | plastic contact area fits the plate (or elastic peak pressure ≤ `q_allow`) |
| `buckling`      | Greenhill self-weight ⊕ Euler tip load (Dunkerley), `λ ≥ SF` |
| `deflection`    | `δ/H ≤ ε` with P-δ amplification |

Each constraint is a pure, named function in `src/post_opt/` returning a signed
margin (`≥ 0` feasible), unit-tested against a hand computation.

## Key modelling choices (spec "known traps")

- **Nondimensionalisation** by `L0 = V^(1/3)` before SLSQP (trap 2).
- **Volume equality eliminated** — `t` is solved from the mass budget, so the
  ill-scaled equality never reaches the optimizer; the gauge floor `t ≥ t_min`
  re-enters as a clean inequality.
- **Log-space radii** `r`, `D` (trap 3).
- **P-δ amplification driven by the buckling eigenvalue** `AF = λ/(λ−1)`, with a
  fixed-point pass on the second-order moment (traps 4, 5).
- **Explicit feasibility re-verification** of every candidate — SLSQP reports
  "success" on slightly infeasible boundary points (trap 1).

## Reproduced regime facts (from the spec)

- Tipping (not bearing) governs the base size for light posts.
- Bearing is inactive by ~3 orders of magnitude at `M = 1 kg`.
- Low-`F` optima are self-weight-buckling limited (`λ → SF`).
- High-`F` kern optima satisfy `h ≈ D·W/(8F)`.
- The Greenhill uniform limit `h_cr = (7.8373 EI/w)^(1/3)` is matched exactly.

These are covered by `tests/test_regimes.py`; the locked v1 baseline table is in
`tests/v1_regression.py`.

## Tests

```bash
pytest -q
```

## Milestone status

- **M1 — done.** Two-cylinder model, all constraints, optimizer, CLI, audit,
  serialisation, tests, packaging.
- **M2–M4 — not yet implemented.** Free radius profile `r(z)` via PCHIP,
  Euler–Bernoulli FEM with variable `EI(z)`, generalized-eigenvalue buckling,
  bolt/flare shell models, and dynamics. The current layering
  (`physics/` pure functions, `model.py`, `optimize.py`) is structured for them.
