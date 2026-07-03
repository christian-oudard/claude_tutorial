package spec

// T1: identities in the linear-phase wave family, differentiated exactly.

import (
	"testing"

	"github.com/christian-oudard/claude_tutorial/creek/exact"
)

// --- §3.3 spectral synthesis ------------------------------------------------

func TestTessendorfHermitianSymmetry(t *testing.T) {
	// h~(k,t) = h0(k) e^{i w t} + conj(h0(-k)) e^{-i w t} with w(k) = w(-k).
	// Reality of the surface requires h~(-k,t) = conj(h~(k,t)).
	// Checked at rational frequency w=3 [AxWlogFrequency], with
	// h0(k) = ar + i·ai and h0(-k) = br + i·bi fully symbolic.
	a := exact.Cplx{Re: exact.Sym("ar"), Im: exact.Sym("ai")}
	b := exact.Cplx{Re: exact.Sym("br"), Im: exact.Sym("bi")}
	plus := exact.PhaseOf("t", 3, 1)
	minus := exact.PhNeg(plus)

	hK := exact.Wave(a, plus).Add(exact.Wave(b.Conj(), minus))
	// At -k the roles of h0(k), h0(-k) swap; the frequency stays +w because
	// omega is even in k — that evenness is exactly the assumption in play.
	hMinusK := exact.Wave(b, plus).Add(exact.Wave(a.Conj(), minus))

	if !hMinusK.Sub(hK.Conj()).IsZero() {
		t.Fatal("h~(-k) != conj(h~(k)): surface would not be real")
	}
}

func TestSpectralSlopeOperator(t *testing.T) {
	// grad eta pulls down i k per mode: d/dx [h~ e^{i(px+qy)}] = i p · (...).
	h := exact.Cplx{Re: exact.Sym("hr"), Im: exact.Sym("hi")}
	for _, pq := range [][2]int{{2, 3}, {5, -1}, {-4, 7}} {
		ph := exact.PhaseOf("x", pq[0], 1, "y", pq[1], 1)
		mode := exact.Wave(h, ph)
		dx := mode.Deriv("x")
		want := mode.ScaleC(exact.CIm(exact.Int(int64(pq[0]))))
		if !dx.Sub(want).IsZero() {
			t.Fatalf("slope operator fails for k=%v", pq)
		}
	}
}

// --- §5.3 synthetic turbulence ----------------------------------------------

func TestKraichnanModeDivergenceFree(t *testing.T) {
	// u'(x,t) = 2 uhat cos(k·x + w t + psi) sigma is divergence-free iff
	// sigma·k = 0. The divergence is linear in the components of k; checking
	// it exactly on several wave vectors certifies the identity for all k
	// [AxGridIdentity]. sigma and uhat stay fully symbolic; psi enters as a
	// unit-frequency phase variable.
	uh := exact.Sym("uhat")
	sig := []exact.Expr{exact.Sym("sx"), exact.Sym("sy"), exact.Sym("sz")}
	vars := []string{"x", "y", "z"}

	kvecs := [][3]int{{2, 3, 5}, {1, 1, -2}, {4, -1, 3}, {-3, 2, 7}}
	for _, k := range kvecs {
		ph := exact.PhaseOf(
			"x", k[0], 1, "y", k[1], 1, "z", k[2], 1,
			"t", 7, 1, "psi", 1, 1,
		)
		div := exact.NewField()
		for i := range vars {
			ui := exact.CosPh(ph).ScaleE(exact.Int(2).Mul(uh).Mul(sig[i]))
			div = div.Add(ui.Deriv(vars[i]))
		}

		// Without the constraint the divergence must NOT vanish
		// (meaningfulness check).
		if div.IsZero() {
			t.Fatalf("divergence trivially zero for k=%v — test is vacuous", k)
		}

		// Impose sigma·k = 0 by eliminating sz = -(sx kx + sy ky)/kz.
		szVal := exact.Sym("sx").Mul(exact.Int(int64(k[0]))).
			Add(exact.Sym("sy").Mul(exact.Int(int64(k[1])))).
			Neg().Div(exact.Int(int64(k[2])))
		constrained := div.MapCoeff(func(e exact.Expr) exact.Expr {
			return e.SubstExpr("sz", szVal)
		})
		if !constrained.IsZero() {
			t.Fatalf("divergence nonzero under sigma.k=0 for k=%v", k)
		}
	}
}

func TestCurlNoiseDivergenceFree(t *testing.T) {
	// u' = curl(Psi) has div u' = 0 identically. Proven exactly for the
	// whole linear-phase family (mixed partials commute by construction
	// here; AxClairaut extends the conclusion to general C² potentials).
	A, B, C := exact.Sym("A"), exact.Sym("B"), exact.Sym("C")
	P := exact.CosPh(exact.PhaseOf("x", 2, 1, "y", -1, 1, "z", 3, 1)).ScaleE(A)
	Q := exact.SinPh(exact.PhaseOf("x", 1, 2, "y", 5, 1, "z", -2, 1)).ScaleE(B)
	R := exact.CosPh(exact.PhaseOf("x", -3, 1, "y", 4, 1, "z", 7, 3)).ScaleE(C)

	curlX := R.Deriv("y").Sub(Q.Deriv("z"))
	curlY := P.Deriv("z").Sub(R.Deriv("x"))
	curlZ := Q.Deriv("x").Sub(P.Deriv("y"))

	div := curlX.Deriv("x").Add(curlY.Deriv("y")).Add(curlZ.Deriv("z"))
	if !div.IsZero() {
		t.Fatal("div(curl Psi) != 0 in the wave family")
	}
	// Meaningfulness: the curl itself is not the zero field.
	if curlX.IsZero() && curlY.IsZero() && curlZ.IsZero() {
		t.Fatal("curl vanished — test is vacuous")
	}
}
