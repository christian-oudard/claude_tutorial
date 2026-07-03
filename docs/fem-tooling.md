# FEM tooling: empirical evaluation

This note records **measured** results (not opinions) from benchmarking
candidate tools on this project's actual FEM problem — the variable-section
beam-column of M2 — to decide what to build M3+ on. All numbers were produced
on the CPU of the dev container; scripts lived in a scratchpad and are
summarised here.

## The question

Our M2 optimizer needs gradients of FEM-derived constraints (yield, buckling
eigenvalue, deflection) w.r.t. ~20 design variables. The spec flags "finite
differences are acceptable at n = 20 ... structure the code so an adjoint can
replace them later." So: is automatic differentiation (adjoints) worth
adopting, and in what tool?

## What was tested

| Tool | Installable here | Result |
|------|------------------|--------|
| **JAX** (0.10) | yes (`uv pip install jax`, CPU) | winner for the gradient/optimizer layer — see below |
| **scikit-fem** (12.0) | yes (pip, pure numpy) | viable lightweight 2D framework for M3; **not** AD-differentiable |
| **Julia** (Ferrite/Gridap) | not available in this env | not evaluated empirically |
| FEniCSx / deal.II | heavy (conda/system) | not attempted in this sandbox |

## Findings — JAX automatic differentiation

The beam FEM (Hermitian-cubic assembly, geometric stiffness, generalized
eigenvalue buckling, second-order deflection) was reimplemented in `jax.numpy`
and compared against the production numpy code and finite differences.

1. **Faithful port.** JAX buckling factor for a uniform column = `508.73140`,
   identical to the numpy `fem.buckling_factor` to 6 digits.
2. **AD is correct.** Gradient of the p-norm yield constraint w.r.t. all design
   variables agreed with central differences to ~`2e-10` absolute. The
   generalized eigenvalue `K φ = λ K_G φ` differentiates cleanly when
   reformulated as `eigvalsh` of `L⁻¹ K_G L⁻ᵀ` (Cholesky `K = L Lᵀ`).
3. **~855× faster Jacobian.** Full constraint Jacobian (42 variables, 3
   constraints including the eigenvalue): **AD 3.8 ms vs FD 3230 ms**. FD needs
   one FEM+eigensolve per variable; reverse-mode AD needs one pass.
4. **AD rescues an optimizer architecture, not just speed.** The *direct*
   height-maximization SLSQP — which was hopeless with finite-difference
   gradients (stuck at ~30–50 % stress utilisation, `H ≈ 1 m`) — converged with
   exact AD gradients in **2.8 s to `H = 5.44 m`, utilisation `1.0000`, matching
   the analytic cube-root taper to 2.2 % at interior nodes.** Same solver, same
   problem; only the gradient source changed.
5. **float64 is mandatory.** JAX defaults to float32, under which the eigenvalue
   FD check disagreed by ~40 %. Structural stiffness matrices are
   ill-conditioned; `jax.config.update("jax_enable_x64", True)` is not optional.

## Findings — scikit-fem (the M3 candidate)

A 2D Poisson solve on a refined unit square gave `max = 0.07345` vs the analytic
`0.0737` — correct. `scikit-fem` is pure Python/numpy, pip-installable, meshes
via Gmsh, and supports the triangular/quad elements an axisymmetric continuum
model needs. **But its assembly is numpy-based, so you cannot `jax.grad`
through it** — using it forfeits automatic adjoints and puts you back on finite
differences (or a hand-written adjoint).

## Recommendation

- **Adopt JAX for the gradient / optimizer layer.** Reimplement the FEM
  assembly in `jax.numpy` (with x64). This is essential for M3+, where the
  statically-determinate structure that makes M2's fully-stressed-design inner
  sizer work no longer holds and a general gradient-based optimizer is needed.
  Keep numpy/scipy for the M1/M2 core (it works and keeps the core dependency
  set to numpy+scipy per the spec); add JAX as an optional extra.
- **For M3's flare, hand-roll the conical-frustum shell in JAX** (differentiable,
  primary model) and **validate it against a `scikit-fem` 2D axisymmetric solve**
  on one test case — which is exactly the spec's "frusta ... verify against a 2D
  axisymmetric solver" plan, now with the added benefit that the primary model
  stays differentiable end-to-end.
- **If the project ever needs full weak-form PDEs at scale**, the two credible
  step-ups are **FEniCSx + dolfin-adjoint** (Python; derives the adjoint PDE
  automatically) or **Julia + Ferrite.jl/Gridap.jl** (one fast language,
  AD-friendly). Neither is warranted at the current 1D/axisymmetric scale.

## Note on M2 specifically

M2 as shipped uses a gradient-free fully-stressed-design inner sizer plus
bisection on H, which is robust and fast precisely because a cantilever is
statically determinate. AD would not improve it. The AD case is about the
*general* path and M3+, where that structural shortcut disappears.
