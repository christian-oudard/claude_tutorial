package exact

import "testing"

// Kernel self-tests: the trusted base gets its own sanity layer.

func TestMonomialAlgebra(t *testing.T) {
	g, sigma, rho := Sym("g"), Sym("sigma"), Sym("rho")

	// √(4gσ/ρ) = 2 g^{1/2} σ^{1/2} ρ^{-1/2}
	r := Int(4).Mul(g).Mul(sigma).Div(rho).Sqrt()
	want := Int(2).Mul(SymPow("g", 1, 2)).Mul(SymPow("sigma", 1, 2)).Mul(SymPow("rho", -1, 2))
	if !r.Equal(want) {
		t.Fatalf("sqrt: got %s want %s", r, want)
	}

	// (a+b)² = a² + 2ab + b²
	a, b := Sym("a"), Sym("b")
	lhs := a.Add(b).PowInt(2)
	rhs := a.PowInt(2).Add(Int(2).Mul(a).Mul(b)).Add(b.PowInt(2))
	if !lhs.Equal(rhs) {
		t.Fatalf("binomial: got %s", lhs)
	}
}

func TestDerivAndSubst(t *testing.T) {
	k, g := Sym("k"), Sym("g")
	// d/dk (g/k) = -g/k²
	d := g.Div(k).Deriv("k")
	if !d.Equal(g.Neg().Mul(SymPow("k", -2, 1))) {
		t.Fatalf("deriv: got %s", d)
	}
	// substitute k -> g^{1/2} into k²: get g
	s := k.PowInt(2).SubstMono("k", SymPow("g", 1, 2))
	if !s.Equal(g) {
		t.Fatalf("subst: got %s", s)
	}
}

func TestReduceSquare(t *testing.T) {
	n1, n2, S := Sym("n1"), Sym("n2"), Sym("S")
	rel := n1.PowInt(2).Add(n2.PowInt(2))
	// S² - (n1²+n2²) reduces to 0
	e := S.PowInt(2).Sub(rel).ReduceSquare("S", rel)
	if !e.IsZero() {
		t.Fatalf("reduce: got %s", e)
	}
	// S⁴ reduces to (n1²+n2²)²
	e4 := S.PowInt(4).ReduceSquare("S", rel)
	if !e4.Equal(rel.PowInt(2)) {
		t.Fatalf("reduce S^4: got %s", e4)
	}
}

func TestTanhSeriesKnownCoefficients(t *testing.T) {
	// tanh x = x - x³/3 + 2x⁵/15 - 17x⁷/315 + ...
	// Known values act as a cross-certificate for the Picard iteration.
	s := TanhSeries(7)
	want := map[int]Expr{
		0: Zero(), 1: Int(1), 2: Zero(), 3: Rat(-1, 3),
		4: Zero(), 5: Rat(2, 15), 6: Zero(), 7: Rat(-17, 315),
	}
	for i, w := range want {
		if !s.At(i).Equal(w) {
			t.Fatalf("tanh coeff x^%d: got %s want %s", i, s.At(i), w)
		}
	}
}

func TestFieldCalculus(t *testing.T) {
	// d/dx cos(2x) = -2 sin(2x), exactly, in the wave-field family.
	ph := PhaseOf("x", 2, 1)
	d := CosPh(ph).Deriv("x")
	want := SinPh(ph).ScaleE(Int(-2))
	if !d.Sub(want).IsZero() {
		t.Fatal("d/dx cos(2x) != -2 sin(2x)")
	}
	// conj(e^{i(2x)}) = e^{-i(2x)}
	w := Wave(CRe(Int(1)), ph)
	if !w.Conj().Sub(Wave(CRe(Int(1)), PhNeg(ph))).IsZero() {
		t.Fatal("conjugate of wave term wrong")
	}
}
