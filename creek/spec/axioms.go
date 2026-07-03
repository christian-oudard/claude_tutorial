// Package spec is the verification suite for the creek surface equation
// specification. It certifies the spec in tiers of decreasing trust:
//
//	T0  the exact kernel (package exact) — the trusted computing base
//	T1  claims reduced to kernel identities, checked by `go test`
//	T2  named axioms (this file) — analysis facts the kernel cannot
//	    express, assumed VISIBLY, with justification and usage recorded
//	T3  float64 runtime code pinned against the exact layer at sample
//	    points (the ℝ ≠ float64 seam, made explicit)
//
// This is the Lean discipline ("prove what you care about, and #print
// axioms for the rest") implemented as a library convention instead of a
// language: the ledger below is this suite's axiom printout.
package spec

// Axiom is a named analysis fact assumed without kernel proof.
type Axiom struct {
	Name          string
	Statement     string
	Justification string
	UsedBy        []string
}

// Axioms is the complete ledger. Nothing else in the suite is assumed:
// every other check reduces to an exact kernel identity or a documented
// float tolerance.
var Axioms = []Axiom{
	{
		Name:          "AxTanhRange",
		Statement:     "for x > 0: 0 < tanh(x) < 1, tanh is increasing, and tanh(x) → 1 as x → ∞",
		Justification: "standard real analysis; corroborated numerically in T3 via the bound 0 < 1 - tanh(x) ≤ 2e^{-2x}",
		UsedBy: []string{
			"deep-water limit of the dispersion relation (§3.1)",
			"positivity/realness of ω₀ (§3.1)",
		},
	},
	{
		Name:          "AxGaussianIntegral",
		Statement:     "∫_ℝ e^{-u²} du = √π",
		Justification: "standard; corroborated numerically in T3 by quadrature to 1e-9",
		UsedBy:        []string{"Cox–Munk slope-PDF normalization (§6.4)"},
	},
	{
		Name:          "AxClairaut",
		Statement:     "mixed partial derivatives of C² fields commute",
		Justification: "proved exactly by the kernel for the entire linear-phase wave family (see TestCurlNoiseDivergenceFree); assumed for general C² fields",
		UsedBy:        []string{"div(curl Ψ) = 0 for general noise potentials (§5.3)"},
	},
	{
		Name:          "AxTrigValues",
		Statement:     "cos(0) = 1, sin(0) = 0, cos(π/2) = 0",
		Justification: "definitional values used to instantiate symbolic cosθ at endpoints",
		UsedBy:        []string{"Schlick endpoints (§6.2)", "Fresnel normal incidence (§6.2)"},
	},
	{
		Name:          "AxWlogFrequency",
		Statement:     "the Hermitian-symmetry identity is checked at a fixed rational frequency; it holds for all ω by linearity of the phase in ω",
		Justification: "the identity's dependence on ω is through e^{±iωt} only; substituting ωt → t' is a bijective reparameterization",
		UsedBy:        []string{"Tessendorf reality condition (§3.3)"},
	},
	{
		Name:          "AxGridIdentity",
		Statement:     "a multivariate polynomial identity of degree ≤ d per variable that holds on a grid larger than d per variable holds identically",
		Justification: "deterministic Schwartz–Zippel / polynomial interpolation; used where wave-vector components enter polynomially",
		UsedBy:        []string{"Kraichnan divergence-free check over all wave vectors (§5.3)"},
	},
}
