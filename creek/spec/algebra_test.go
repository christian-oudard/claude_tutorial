package spec

// T1: algebraic identities certified as exact kernel identities. Where the
// informal spec divides by a sum or takes the root of a sum, the check is
// stated in cleared/adjoined form; the clearing step is the human-supplied
// certificate, the resulting identity is machine-checked exactly.

import (
	"testing"

	"github.com/christian-oudard/claude_tutorial/creek/exact"
)

// --- §3.1 capillary–gravity dispersion --------------------------------------

func TestCrossoverWavenumber(t *testing.T) {
	g, sigma, rho := exact.Sym("g"), exact.Sym("sigma"), exact.Sym("rho")

	// k_m = sqrt(rho g / sigma)
	km := rho.Mul(g).Div(sigma).Sqrt()

	// k_m solves g k = (sigma/rho) k^3 exactly.
	lhs := g.Mul(km)
	rhs := sigma.Div(rho).Mul(km.PowInt(3))
	if !lhs.Equal(rhs) {
		t.Fatalf("g k_m = (sigma/rho) k_m^3 fails: %s vs %s", lhs, rhs)
	}

	// lambda_m = 2 pi / k_m = 2 pi sqrt(sigma/(rho g)).
	pi := exact.Sym("pi")
	lam := exact.Int(2).Mul(pi).Div(km)
	want := exact.Int(2).Mul(pi).Mul(sigma.Div(rho.Mul(g)).Sqrt())
	if !lam.Equal(want) {
		t.Fatalf("lambda_m identity fails: %s vs %s", lam, want)
	}
}

func TestMinimumPhaseSpeed(t *testing.T) {
	g, sigma, rho, k := exact.Sym("g"), exact.Sym("sigma"), exact.Sym("rho"), exact.Sym("k")
	km := rho.Mul(g).Div(sigma).Sqrt()

	// Deep water: c_p^2 = omega^2/k^2 = g/k + (sigma/rho) k.
	cp2 := g.Div(k).Add(sigma.Div(rho).Mul(k))

	// Stationarity: d(c_p^2)/dk vanishes exactly at k = k_m.
	dcp2 := cp2.Deriv("k").SubstMono("k", km)
	if !dcp2.IsZero() {
		t.Fatalf("d(c_p^2)/dk at k_m != 0: %s", dcp2)
	}

	// Second derivative at k_m is a positive monomial => genuine minimum.
	d2 := cp2.Deriv("k").Deriv("k").SubstMono("k", km)
	if !d2.IsPosMono() {
		t.Fatalf("second derivative not positive monomial: %s", d2)
	}

	// Value: c_min^2 = 2 sqrt(g sigma / rho), hence c_min^4 = 4 g sigma/rho,
	// i.e. c_min = (4 g sigma / rho)^{1/4}.
	cmin2 := cp2.SubstMono("k", km)
	want2 := exact.Int(2).Mul(g.Mul(sigma).Div(rho).Sqrt())
	if !cmin2.Equal(want2) {
		t.Fatalf("c_min^2 = 2 sqrt(g sigma/rho) fails: %s", cmin2)
	}
	cmin4 := cmin2.PowInt(2)
	want4 := exact.Int(4).Mul(g).Mul(sigma).Div(rho)
	if !cmin4.Equal(want4) {
		t.Fatalf("c_min^4 = 4 g sigma / rho fails: %s", cmin4)
	}
}

func TestDispersionPositivity(t *testing.T) {
	// Both branches of omega0^2/tanh(kh) are positive monomials, so with
	// AxTanhRange (tanh > 0) the dispersion relation yields real omega0.
	g, sigma, rho, k := exact.Sym("g"), exact.Sym("sigma"), exact.Sym("rho"), exact.Sym("k")
	if !g.Mul(k).IsPosMono() {
		t.Error("gravity branch not positive")
	}
	if !sigma.Div(rho).Mul(k.PowInt(3)).IsPosMono() {
		t.Error("capillary branch not positive")
	}
	// The deep-water limit omega0^2 -> gk + (sigma/rho)k^3 is the factored
	// structure (gk + (sigma/rho)k^3)·tanh(kh) with tanh -> 1 [AxTanhRange].
}

// --- §4.2 Nwogu / Padé dispersion match -------------------------------------

func TestNwoguPadeMatchesAiry(t *testing.T) {
	// pade(x) = x(1 - (alpha+1/3)x^2) / (1 - alpha x^2), x = kh, equals
	// omega^2/(gk). Airy: tanh(x). Both odd; x^1 and x^3 coefficients agree
	// for every alpha, and the x^5 coefficient vanishes exactly at
	// alpha = -2/5. All coefficients computed exactly, alpha symbolic.
	const order = 7
	alpha := exact.Sym("alpha")

	u := exact.ZeroSeries(order).SetCoeff(2, alpha) // alpha x^2
	numer := exact.ZeroSeries(order).
		SetCoeff(1, exact.Int(1)).
		SetCoeff(3, alpha.Add(exact.Rat(1, 3)).Neg())
	pade := numer.Mul(exact.Geom(u)) // Geom(u) = 1/(1 - alpha x^2)

	diff := pade.Sub(exact.TanhSeries(order))

	if !diff.At(1).IsZero() || !diff.At(3).IsZero() {
		t.Fatalf("x^1/x^3 mismatch for symbolic alpha: %s / %s", diff.At(1), diff.At(3))
	}

	// Solve the linear x^5 condition for alpha, exactly.
	c5 := diff.At(5)
	a1 := c5.CoeffOf("alpha", 1, 1)
	a0 := c5.CoeffOf("alpha", 0, 1)
	if a1.IsZero() {
		t.Fatal("x^5 coefficient degenerate in alpha")
	}
	root := a0.Neg().Div(a1)
	if !root.Equal(exact.Rat(-2, 5)) {
		t.Fatalf("optimal alpha = %s, want -2/5", root)
	}

	// At alpha = -2/5 the x^5 term vanishes and a genuine x^7 residual
	// remains (the match is improved, not exact).
	c5at := c5.SubstExpr("alpha", exact.Rat(-2, 5))
	if !c5at.IsZero() {
		t.Fatalf("x^5 coefficient at alpha=-2/5: %s", c5at)
	}
	c7at := diff.At(7).SubstExpr("alpha", exact.Rat(-2, 5))
	if c7at.IsZero() {
		t.Fatal("x^7 residual unexpectedly zero — match would be exact")
	}
}

// --- §6.2 Fresnel -----------------------------------------------------------

func TestFresnelNormalIncidence(t *testing.T) {
	// At theta_i = 0 [AxTrigValues], r_s = (n1-n2)/(n1+n2) and
	// r_p = (n2-n1)/(n2+n1); both squared reflectances equal
	// R0 = ((n2-n1)/(n2+n1))^2. Cleared form: multiply through by (n1+n2)^2.
	n1, n2 := exact.Sym("n1"), exact.Sym("n2")
	rsNum := n1.Sub(n2) // r_s(0) * (n1+n2)
	rpNum := n2.Sub(n1) // r_p(0) * (n2+n1)
	r0Num := n2.Sub(n1) // sqrt(R0) * (n2+n1), up to sign

	if !rsNum.PowInt(2).Equal(r0Num.PowInt(2)) {
		t.Error("|r_s(0)|^2 != R0 (cleared form)")
	}
	if !rpNum.PowInt(2).Equal(r0Num.PowInt(2)) {
		t.Error("|r_p(0)|^2 != R0 (cleared form)")
	}
}

func TestBrewsterAngle(t *testing.T) {
	// At theta_B = arctan(n2/n1): with S = sqrt(n1^2 + n2^2) adjoined via
	// S^2 -> n1^2 + n2^2, the scaled trig values are
	//   sin(theta_i)·S = n2,  cos(theta_i)·S = n1,
	//   sin(theta_t)·S = n1,  cos(theta_t)·S = n2   (Snell + Pythagoras).
	n1, n2, S := exact.Sym("n1"), exact.Sym("n2"), exact.Sym("S")
	rel := n1.PowInt(2).Add(n2.PowInt(2))
	red := func(e exact.Expr) exact.Expr { return e.ReduceSquare("S", rel) }

	sinI, cosI := n2, n1
	sinT, cosT := n1, n2

	// Side conditions (each scaled by S^2): sin^2 + cos^2 = S^2.
	if !red(sinI.PowInt(2).Add(cosI.PowInt(2)).Sub(S.PowInt(2))).IsZero() {
		t.Error("incident Pythagoras fails")
	}
	if !red(sinT.PowInt(2).Add(cosT.PowInt(2)).Sub(S.PowInt(2))).IsZero() {
		t.Error("transmitted Pythagoras fails")
	}
	// Snell (scaled by S): n1 sin(theta_i) = n2 sin(theta_t).
	if !n1.Mul(sinI).Equal(n2.Mul(sinT)) {
		t.Error("Snell at Brewster fails")
	}
	// r_p numerator (scaled by S): n2 cos(theta_i) - n1 cos(theta_t) = 0.
	if !n2.Mul(cosI).Sub(n1.Mul(cosT)).IsZero() {
		t.Error("r_p at Brewster does not vanish")
	}
	// Meaningfulness: r_s does NOT vanish there (n1^2 - n2^2 != 0 as an
	// element of the algebra) — only p-polarization is extinguished.
	if n1.Mul(cosI).Sub(n2.Mul(cosT)).IsZero() {
		t.Error("r_s unexpectedly vanishes at Brewster")
	}
}

func TestSchlickEndpoints(t *testing.T) {
	// Schlick f(c) = R0 + (1-R0)(1-c)^5 with c = cos(theta_i) [AxTrigValues]:
	// f(1) = R0 (matches Fresnel at normal incidence), f(0) = 1 (grazing).
	c, R0 := exact.Sym("c"), exact.Sym("R0")
	f := R0.Add(exact.Int(1).Sub(R0).Mul(exact.Int(1).Sub(c).PowInt(5)))
	if !f.SubstExpr("c", exact.Int(1)).Equal(R0) {
		t.Error("Schlick(cos=1) != R0")
	}
	if !f.SubstExpr("c", exact.Zero()).Equal(exact.Int(1)) {
		t.Error("Schlick(cos=0) != 1")
	}
}

// --- §6.4 statistical glints ------------------------------------------------

func TestGGXAtNormal(t *testing.T) {
	// D(m) = a^2 / (pi [(n·m)^2 (a^2-1) + 1]^2) reduces to 1/(pi a^2) at
	// m = n. Cleared form: a^2 · (pi a^2) = pi · [denominator at c=1].
	a, c, pi := exact.Sym("a"), exact.Sym("c"), exact.Sym("pi")
	denom := c.PowInt(2).Mul(a.PowInt(2).Sub(exact.Int(1))).Add(exact.Int(1)).PowInt(2)
	denomAtN := denom.SubstExpr("c", exact.Int(1))
	if !denomAtN.Equal(a.PowInt(4)) {
		t.Fatalf("GGX denominator at m=n: %s", denomAtN)
	}
	lhs := a.PowInt(2).Mul(pi).Mul(a.PowInt(2))
	rhs := pi.Mul(denomAtN)
	if !lhs.Equal(rhs) {
		t.Error("GGX at m=n != 1/(pi a^2) (cleared form)")
	}
}

func TestCoxMunkNormalizationBookkeeping(t *testing.T) {
	// P = (2 pi sx sy)^{-1} exp(-etax^2/(2sx^2) - etay^2/(2sy^2)).
	// Factoring into 1D Gaussians and applying AxGaussianIntegral to each
	// gives ∫∫P = (2 pi sx sy)^{-1} · sqrt(2 pi) sx · sqrt(2 pi) sy.
	// The kernel checks the remaining bookkeeping in squared form
	// (squaring eliminates the radicals):
	//   [(2 pi sx sy)^{-1}]^2 · (2 pi sx^2) · (2 pi sy^2) = 1.
	pi, sx, sy := exact.Sym("pi"), exact.Sym("sx"), exact.Sym("sy")
	pref := exact.Int(2).Mul(pi).Mul(sx).Mul(sy).Inv()
	prod := pref.PowInt(2).
		Mul(exact.Int(2).Mul(pi).Mul(sx.PowInt(2))).
		Mul(exact.Int(2).Mul(pi).Mul(sy.PowInt(2)))
	if !prod.Equal(exact.Int(1)) {
		t.Fatalf("Cox-Munk normalization bookkeeping: %s", prod)
	}
}
