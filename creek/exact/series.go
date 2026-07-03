package exact

import "fmt"

// Series is a truncated univariate power series Σ c[i]·xⁱ, i ≤ order, with
// Expr coefficients — so a series can carry free symbolic parameters
// (e.g. the Nwogu α) exactly.
type Series struct {
	c []Expr
}

// ZeroSeries returns the zero series of the given order.
func ZeroSeries(order int) Series {
	c := make([]Expr, order+1)
	for i := range c {
		c[i] = Zero()
	}
	return Series{c: c}
}

// OneSeries returns the constant series 1.
func OneSeries(order int) Series {
	s := ZeroSeries(order)
	s.c[0] = Int(1)
	return s
}

// X returns the series x.
func X(order int) Series {
	s := ZeroSeries(order)
	if order >= 1 {
		s.c[1] = Int(1)
	}
	return s
}

// Order returns the truncation order.
func (s Series) Order() int { return len(s.c) - 1 }

// At returns the coefficient of xⁱ.
func (s Series) At(i int) Expr { return s.c[i] }

// SetCoeff returns a copy of s with the coefficient of xⁱ replaced by e.
func (s Series) SetCoeff(i int, e Expr) Series {
	r := s.clone()
	r.c[i] = e
	return r
}

func (s Series) clone() Series {
	c := make([]Expr, len(s.c))
	copy(c, s.c)
	return Series{c: c}
}

func (s Series) sameOrder(t Series, op string) {
	if len(s.c) != len(t.c) {
		panic(fmt.Sprintf("exact: series order mismatch in %s", op))
	}
}

// Add returns s + t.
func (s Series) Add(t Series) Series {
	s.sameOrder(t, "Add")
	r := ZeroSeries(s.Order())
	for i := range r.c {
		r.c[i] = s.c[i].Add(t.c[i])
	}
	return r
}

// Sub returns s - t.
func (s Series) Sub(t Series) Series {
	s.sameOrder(t, "Sub")
	r := ZeroSeries(s.Order())
	for i := range r.c {
		r.c[i] = s.c[i].Sub(t.c[i])
	}
	return r
}

// Mul returns s · t truncated to the common order.
func (s Series) Mul(t Series) Series {
	s.sameOrder(t, "Mul")
	r := ZeroSeries(s.Order())
	for i := 0; i <= s.Order(); i++ {
		if s.c[i].IsZero() {
			continue
		}
		for j := 0; i+j <= s.Order(); j++ {
			if t.c[j].IsZero() {
				continue
			}
			r.c[i+j] = r.c[i+j].Add(s.c[i].Mul(t.c[j]))
		}
	}
	return r
}

// Scale returns e · s.
func (s Series) Scale(e Expr) Series {
	r := ZeroSeries(s.Order())
	for i := range r.c {
		r.c[i] = s.c[i].Mul(e)
	}
	return r
}

// Integrate returns ∫s dx with zero constant term (truncated to the same
// order: the x^order coefficient of the result uses c[order-1]).
func (s Series) Integrate() Series {
	r := ZeroSeries(s.Order())
	for i := 1; i <= s.Order(); i++ {
		r.c[i] = s.c[i-1].Mul(Rat(1, int64(i)))
	}
	return r
}

// TanhSeries returns the Maclaurin series of tanh to the given order,
// computed by Picard iteration of the defining ODE t' = 1 - t², t(0) = 0.
// Each iteration extends correctness by at least one order.
func TanhSeries(order int) Series {
	t := ZeroSeries(order)
	one := OneSeries(order)
	for i := 0; i <= order+1; i++ {
		t = one.Sub(t.Mul(t)).Integrate()
	}
	return t
}

// Geom returns Σ_{j≥0} uʲ (truncated), i.e. 1/(1-u), for a series u with
// zero constant term.
func Geom(u Series) Series {
	if !u.c[0].IsZero() {
		panic("exact: Geom requires zero constant term")
	}
	r := OneSeries(u.Order())
	p := OneSeries(u.Order())
	for j := 1; j <= u.Order(); j++ {
		p = p.Mul(u)
		r = r.Add(p)
	}
	return r
}
