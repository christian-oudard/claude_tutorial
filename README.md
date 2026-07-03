# post-opt — axisymmetric post optimizer

Given a fixed metal mass, find the rotationally symmetric shape that stands a
load off the ground at **maximum standoff height** without failing
structurally, tipping, or exceeding soil bearing pressure.

This repository implements **Milestones M1 and M2** of the spec:

* **M1** — the two-cylinder `(r, h, D, t)` design with the full constraint set,
  a nondimensionalised multistart SLSQP optimizer, config/results
  serialisation, a CLI, and an independent audit tool.
* **M2** — the free solid axisymmetric profile `r(z)`: an `n`-point PCHIP
  radius profile solved with an Euler–Bernoulli FEM (variable `EI(z)`,
  geometric stiffness, generalized-eigenvalue buckling, second-order
  deflection), reusing the M1 base plate.

The physics / model / optimizer layers are separated so the shell/bolt models
of M3–M4 can slot in without touching the solver.

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
post-opt run   --profile            # M2 free-profile r(z) model
post-opt sweep configs/default.toml --param F --values 0.1,0.5,1,2,5
post-opt audit result.json          # independent re-verification (two-cylinder)
```

Set `model = "profile"` in the TOML (or pass `--profile`) to optimise the free
`r(z)` profile. At equal mass the shaped profile stands taller than the crude
two-cylinder.

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

## M2 — free profile `r(z)`

The shaft becomes an `n`-point PCHIP radius profile (`H` a separate scalar
variable); the base plate stays a discrete disc.  Structural response is an
Euler–Bernoulli FEM (`src/post_opt/fem.py`) with variable `EI(z)`, geometric
stiffness `K_G(N(z))`, buckling from `K φ = λ K_G φ`, and second-order
deflection from `(K − K_G)`.

The optimizer (`src/post_opt/profile_optimize.py`) exploits the fact that a
cantilever is statically determinate: instead of a fragile 20-variable SLSQP it
uses a **fully-stressed design** inner sizer (solve `σ_y = N/A + 4M/(πr³)` per
section, iterated in PCHIP space so the FEM-evaluated stress reaches `σ_y`),
a **stiffness-inflation** step for buckling/deflection-governed regimes, and
**bisection on `H`**.  This is deterministic, robust, and fast (~0.5–5 s).

Validated against the analytic limits (`tests/test_profile_m2.py`,
`tests/test_fem.py`):

- **cube-root taper** `r³ ∝ F(H−z)` recovered to <0.1 % at interior nodes when
  yield governs (`P = 0`, buckling/deflection off);
- **constant `r`** under axial-dominated loading (`F = 0`, `P > 0`);
- **Greenhill** uniform-column self-weight buckling to 0.03 %, **Euler** tip
  load exact.

## Milestone status

- **M1 — done.** Two-cylinder model, all constraints, optimizer, CLI, audit.
- **M2 — done.** Free `r(z)` profile, Euler–Bernoulli FEM, eigenvalue buckling,
  second-order deflection; all three analytic acceptance limits reproduced.
- **M3–M4 — not yet implemented.** Bolt/flare shell models, hollow variants,
  and dynamics. The current layering is structured for them.
