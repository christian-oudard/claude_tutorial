# creek — verified math + performant graphics, one Go codebase

An experiment: take the creek-surface simulation spec (see
`../creek_equations.py`, the SymPy design-time oracle) and see what it
takes to get **high certainty about the math** and **performance-grade
graphics** inside a single Go module, with **zero dependencies** beyond
the standard library.

The organizing thesis: *the proof assistant should be a library, not a
language.* Instead of moving the project into Lean, the trust discipline
moves into Go: a small exact-arithmetic kernel plays the role of the
proof kernel, `go test` plays the role of the checker, and a named axiom
ledger plays the role of `#print axioms`.

## Trust tiers

| Tier | What | Where |
|------|------|-------|
| T0 | Exact kernel: rational Puiseux algebra, symbolic power series, complex coefficients, linear-phase wave fields with exact differentiation. Depends only on `math/big`. Refuses to approximate (e.g. panics on `4^{1/4}`). | `exact/` |
| T1 | Spec claims reduced to kernel identities: 40+ dimensional-consistency checks (rational exponents exact), the algebraic derivations (crossover wavenumber, minimum phase speed *with* second-derivative certificate, Nwogu α = −2/5 by exact series solve, Brewster ⇒ r_p = 0 via radical adjunction, Hermitian reality, divergence-free turbulence constructions), and every number the spec quotes. | `dim/`, `spec/` |
| T2 | Named axioms: the analysis facts the kernel cannot express (tanh limit, Gaussian integral, Clairaut, …). Declared with justification and usage; an empty or anonymous ledger fails the suite. | `spec/axioms.go` |
| T3 | The float64 runtime layer pinned against the exact layer, plus numeric corroboration of the axioms. This is the ℝ ≠ float64 seam made explicit. | `spec/float_test.go` |
| T4 | The performance layer: FFT, spectral surface, renderer. Fast, tested behaviorally, *not* certified — but its constants and closed forms come from `phys`, which T3 pins to the kernel. | `fft/`, `wave/`, `render/` |

Checks that require dividing by a sum or taking the root of a sum are
stated in *cleared/adjoined form*: the clearing step is the
human-supplied certificate, the resulting identity is machine-checked
exactly (`ReduceSquare` adjoins √(n1²+n2²) for Brewster, etc.). This is
the find-hard/check-cheap asymmetry used deliberately: SymPy (or a
human, or an LLM) finds the form; the Go kernel checks it.

## What the discipline caught while being built

- **Schlick's true worst-case error** vs exact Fresnel for air→water is
  ≈ 0.059 absolute, not the ~0.04 initially asserted. T3 measured it;
  the bound is now pinned both ways (fails if worse *or* suspiciously
  better).
- **float64 cannot witness `tanh(x) < 1` past x ≈ 19** — the strict
  real-number inequality rounds away. The T3 test now demonstrates the
  seam it exists to police.
- **The Nyquist band breaks the certified Hermitian identity on even
  grids**: the k = −k self-paired modes make the Doppler phase factor
  non-real. The `ImagResidual` runtime probe of the certified identity
  caught it; the fix (zeroing the self-paired band) enforces the
  identity's hypothesis. A theorem, its runtime probe, and a
  discretization bug meeting exactly as designed.
- The two **documentation discrepancies** found by the Python suite
  (capillary-CFL ~33 µs not ~1 µs at Δx = 100 µm; Kolmogorov η ≈ 36 µm
  vs the quoted 50–100 µm) are pinned as expected-discrepancy tests in
  both languages — cross-language drift detection.

## The performance half

- `fft/` — in-place radix-2 FFT, goroutine-parallel 2D transform.
  Verified against a naive DFT, round-trip, and Parseval.
- `wave/` — Tessendorf spectral synthesis (§3.3) with the full
  finite-depth capillary–gravity dispersion (§3.1), **Doppler advection
  by the creek current** (§3.2, exact-advection tested), choppy
  displacement with the DC-mode 0/0 guarded, and the §6.4 sub-grid
  slope-variance tail computed from the same spectrum.
- `render/` — ray-marched heightfield; Schlick reflectance (pinned to
  exact Fresnel), GGX sun glints whose roughness *is* the spectral tail
  the grid can't resolve, Beer–Lambert bed attenuation, procedural
  cobbles. CPU-only, scanline-parallel.

Measured on this 4-core container (Xeon 2.8 GHz):

- ocean step, 256² grid, 5 inverse FFTs: **~10.5 ms** (~95 Hz)
- 960×540 render, 1 sample/px: ~0.6 s; 2×2 supersampled: ~2.2 s

The simulation layer is real-time on CPU today; the shading loop is an
embarrassingly parallel transcription away from a GPU fragment/compute
shader — `render.Shade` is deliberately written as the reference
implementation of that shader.

## Run

```
go test ./...            # certify: 76 test functions, kernel → spec → float
go run ./cmd/creek       # render frames into ./out, print derived constants
go test ./wave -bench .  # simulation benchmark
```

## Relation to the SymPy suite

`../creek_equations.py` remains the design-time oracle (better at
*finding* — limits, solving, series with remainder). This module is the
shipping-language *checker*: everything the Python suite asserts
numerically is re-asserted here, and the algebraic core is re-derived
exactly rather than trusted. Where the two disagree, a test fails in at
least one of them.
