package exact

import (
	"math/big"
	"sort"
	"strings"
)

// Field is a finite sum of linear-phase waves
//
//	Σ  c_j · exp( i · Σ_v φ_{j,v} · v )
//
// with Cplx coefficients c_j and exact rational frequencies φ. The family
// is closed under +, scalar multiplication, ∂/∂v, and conjugation, and
// mixed partial derivatives commute by construction — which makes it a
// small exactly-differentiable function space: precisely the Fourier modes
// the spectral surface model (§3.3) and synthetic turbulence (§5.3) are
// built from.
type Field struct {
	terms map[string]*fterm
}

type fterm struct {
	c  Cplx
	ph map[string]*big.Rat
}

func phClone(ph map[string]*big.Rat) map[string]*big.Rat {
	out := make(map[string]*big.Rat, len(ph))
	for k, v := range ph {
		if v.Sign() != 0 {
			out[k] = new(big.Rat).Set(v)
		}
	}
	return out
}

func phSig(ph map[string]*big.Rat) string {
	keys := make([]string, 0, len(ph))
	for k := range ph {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	var b strings.Builder
	for _, k := range keys {
		b.WriteString(k)
		b.WriteByte(':')
		b.WriteString(ph[k].RatString())
		b.WriteByte(';')
	}
	return b.String()
}

// Ph builds a phase map from alternating name/rational pairs given as
// (name, p, q) triples encoded in parallel slices — see PhaseOf for the
// convenient constructor used by tests.
type Ph = map[string]*big.Rat

// PhaseOf builds a phase map: PhaseOf("x", 2, 1, "t", -3, 1) means 2x - 3t.
func PhaseOf(args ...any) Ph {
	if len(args)%3 != 0 {
		panic("exact: PhaseOf wants (name, p, q) triples")
	}
	ph := Ph{}
	for i := 0; i < len(args); i += 3 {
		name := args[i].(string)
		p := int64(args[i+1].(int))
		q := int64(args[i+2].(int))
		ph[name] = new(big.Rat).SetFrac64(p, q)
	}
	return ph
}

// PhNeg negates a phase map.
func PhNeg(ph Ph) Ph {
	out := Ph{}
	for k, v := range ph {
		out[k] = new(big.Rat).Neg(v)
	}
	return out
}

// NewField returns the zero field.
func NewField() Field { return Field{terms: map[string]*fterm{}} }

// Wave returns c · e^{i·(Σ φ_v v)}.
func Wave(c Cplx, ph Ph) Field {
	f := NewField()
	f.insert(c, phClone(ph))
	return f
}

func (f Field) insert(c Cplx, ph map[string]*big.Rat) {
	if c.IsZero() {
		return
	}
	s := phSig(ph)
	if ex, ok := f.terms[s]; ok {
		ex.c = ex.c.Add(c)
		if ex.c.IsZero() {
			delete(f.terms, s)
		}
	} else {
		f.terms[s] = &fterm{c: c, ph: ph}
	}
}

// Add returns f + g.
func (f Field) Add(g Field) Field {
	r := NewField()
	for _, t := range f.terms {
		r.insert(t.c, phClone(t.ph))
	}
	for _, t := range g.terms {
		r.insert(t.c, phClone(t.ph))
	}
	return r
}

// Neg returns -f.
func (f Field) Neg() Field {
	r := NewField()
	for _, t := range f.terms {
		r.insert(t.c.Neg(), phClone(t.ph))
	}
	return r
}

// Sub returns f - g.
func (f Field) Sub(g Field) Field { return f.Add(g.Neg()) }

// ScaleC returns c · f.
func (f Field) ScaleC(c Cplx) Field {
	r := NewField()
	for _, t := range f.terms {
		r.insert(t.c.Mul(c), phClone(t.ph))
	}
	return r
}

// ScaleE returns e · f for a real scalar expression e.
func (f Field) ScaleE(e Expr) Field { return f.ScaleC(CRe(e)) }

// Deriv returns ∂f/∂v, exactly: each term picks up a factor i·φ_v.
func (f Field) Deriv(v string) Field {
	r := NewField()
	for _, t := range f.terms {
		freq, ok := t.ph[v]
		if !ok {
			continue
		}
		r.insert(t.c.MulI().Scale(FromRat(freq)), phClone(t.ph))
	}
	return r
}

// Conj returns the complex conjugate field (coefficients conjugated,
// phases negated).
func (f Field) Conj() Field {
	r := NewField()
	for _, t := range f.terms {
		r.insert(t.c.Conj(), phClone(PhNeg(t.ph)))
	}
	return r
}

// MapCoeff applies fn to every coefficient component (used to impose
// side conditions such as σ·k = 0 by substitution).
func (f Field) MapCoeff(fn func(Expr) Expr) Field {
	r := NewField()
	for _, t := range f.terms {
		r.insert(t.c.MapExpr(fn), phClone(t.ph))
	}
	return r
}

// IsZero reports whether f is identically zero.
func (f Field) IsZero() bool { return len(f.terms) == 0 }

// NumTerms returns the number of distinct phases in f.
func (f Field) NumTerms() int { return len(f.terms) }

// CosPh returns cos(Σ φ_v v) = ½e^{iφ} + ½e^{-iφ}.
func CosPh(ph Ph) Field {
	return Wave(CRe(Rat(1, 2)), ph).Add(Wave(CRe(Rat(1, 2)), PhNeg(ph)))
}

// SinPh returns sin(Σ φ_v v) = (e^{iφ} - e^{-iφ})/(2i).
func SinPh(ph Ph) Field {
	return Wave(CIm(Rat(-1, 2)), ph).Add(Wave(CIm(Rat(1, 2)), PhNeg(ph)))
}
