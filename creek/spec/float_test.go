package spec

// T3: the float64 runtime layer (package phys) pinned against the exact
// kernel, plus numeric corroboration of the analysis axioms. This is the
// ℝ ≠ float64 seam: the kernel certifies real-number identities; these
// tests bound how far the shipping float code sits from them.

import (
	"math"
	"testing"

	"github.com/christian-oudard/claude_tutorial/creek/exact"
	"github.com/christian-oudard/claude_tutorial/creek/phys"
)

var physVals = map[string]float64{
	"g":     phys.Grav,
	"sigma": phys.SigmaWater,
	"rho":   phys.RhoWater,
	"n1":    phys.NAir,
	"n2":    phys.NWater,
	"pi":    math.Pi,
}

func pin(t *testing.T, name string, runtimeVal float64, kernelExpr exact.Expr) {
	t.Helper()
	ref := kernelExpr.EvalF64(physVals)
	rel := math.Abs(runtimeVal-ref) / math.Abs(ref)
	if rel > 1e-12 {
		t.Errorf("%s: runtime %.17g vs kernel %.17g (rel %.2g)", name, runtimeVal, ref, rel)
	}
}

func TestRuntimeConstantsPinnedToKernel(t *testing.T) {
	g, sigma, rho := exact.Sym("g"), exact.Sym("sigma"), exact.Sym("rho")
	n1, n2, pi := exact.Sym("n1"), exact.Sym("n2"), exact.Sym("pi")

	km := rho.Mul(g).Div(sigma).Sqrt()
	pin(t, "KCross", phys.KCross(), km)
	pin(t, "LambdaCross", phys.LambdaCross(), exact.Int(2).Mul(pi).Div(km))
	// CMin is pinned in squared form: the kernel (correctly) refuses
	// (4gσ/ρ)^{1/4} since 4^{1/4} = √2 is irrational, but it certifies
	// c_min² = 2√(gσ/ρ) exactly (TestMinimumPhaseSpeed).
	pin(t, "CMin^2", phys.CMin()*phys.CMin(),
		exact.Int(2).Mul(g.Mul(sigma).Div(rho).Sqrt()))

	// R0 = (n2-n1)^2/(n2+n1)^2: the kernel side is evaluated in cleared
	// form since Expr does not divide by sums.
	r0Cleared := n2.Sub(n1).PowInt(2)
	denom := n2.Add(n1).PowInt(2)
	ref := r0Cleared.EvalF64(physVals) / denom.EvalF64(physVals)
	if rel := math.Abs(phys.R0()-ref) / ref; rel > 1e-12 {
		t.Errorf("R0: runtime %.17g vs kernel %.17g", phys.R0(), ref)
	}
}

func TestSchlickApproximatesFresnel(t *testing.T) {
	// Schlick is an approximation: both endpoints are exact (certified in
	// TestSchlickEndpoints); in between, T3 measurement puts the maximum
	// absolute deviation from exact unpolarized Fresnel for air→water at
	// ≈0.059 (near grazing). The bound below pins that measured fact —
	// if the renderer's shortcut ever gets worse than the known worst
	// case, this fails.
	maxAbs := 0.0
	for i := 0; i <= 1000; i++ {
		cosI := float64(i) / 1000
		d := math.Abs(phys.SchlickR(cosI) - phys.FresnelR(cosI))
		if d > maxAbs {
			maxAbs = d
		}
	}
	if maxAbs > 0.065 {
		t.Errorf("Schlick deviates from Fresnel by %.4f > 0.065", maxAbs)
	}
	if maxAbs < 0.05 {
		t.Errorf("Schlick deviation %.4f suspiciously small — measurement or formula changed", maxAbs)
	}
	// Endpoints exact in float too.
	if math.Abs(phys.SchlickR(1)-phys.FresnelR(1)) > 1e-12 {
		t.Error("Schlick(0 deg) != Fresnel(0 deg)")
	}
	if math.Abs(phys.SchlickR(0)-1) > 1e-12 || math.Abs(phys.FresnelR(0)-1) > 1e-9 {
		t.Error("grazing reflectance != 1")
	}
}

func TestAxTanhRangeNumeric(t *testing.T) {
	// Corroborate AxTanhRange: 0 < 1 - tanh(x) <= 2 e^{-2x} for x > 0.
	// The strict inequality tanh(x) < 1 is a real-number fact that float64
	// cannot witness past x ≈ 19: math.Tanh(20) rounds to exactly 1.0.
	// So the float corroboration checks strictness only where float64 can
	// represent it — a live demonstration of the ℝ ≠ float64 seam.
	for _, x := range []float64{0.1, 0.5, 1, 2, 5, 10, 20} {
		d := 1 - math.Tanh(x)
		if d < 0 || d > 2*math.Exp(-2*x)+1e-16 {
			t.Errorf("tanh bound violated at x=%g: 1-tanh=%g", x, d)
		}
		if x <= 15 && d <= 0 {
			t.Errorf("tanh(%g) not strictly below 1 in float64", x)
		}
	}
}

func TestAxGaussianIntegralNumeric(t *testing.T) {
	// Corroborate AxGaussianIntegral by Simpson quadrature on [-10,10].
	const n = 20000
	a, b := -10.0, 10.0
	hstep := (b - a) / n
	sum := 0.0
	f := func(x float64) float64 { return math.Exp(-x * x) }
	for i := 0; i <= n; i++ {
		x := a + float64(i)*hstep
		w := 4.0
		switch {
		case i == 0 || i == n:
			w = 1
		case i%2 == 0:
			w = 2
		}
		sum += w * f(x)
	}
	integral := sum * hstep / 3
	if math.Abs(integral-math.Sqrt(math.Pi)) > 1e-9 {
		t.Errorf("Gaussian integral %.12f vs sqrt(pi) %.12f", integral, math.Sqrt(math.Pi))
	}
}

func TestAxiomLedgerIsDeclared(t *testing.T) {
	// The ledger must exist and every axiom must carry a justification and
	// at least one recorded use — no anonymous assumptions.
	if len(Axioms) == 0 {
		t.Fatal("axiom ledger empty — suspicious for a suite this size")
	}
	for _, ax := range Axioms {
		if ax.Name == "" || ax.Statement == "" || ax.Justification == "" || len(ax.UsedBy) == 0 {
			t.Errorf("axiom %q incompletely declared", ax.Name)
		}
		t.Logf("AXIOM %s: %s", ax.Name, ax.Statement)
	}
}
