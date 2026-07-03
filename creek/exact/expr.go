// Package exact is the trusted kernel of the creek verification suite.
//
// It implements exact rational arithmetic over four small algebraic
// structures, and nothing else:
//
//   - Expr:   finite sums of monomials  c · Π sᵢ^{eᵢ}  with exact rational
//     coefficients c AND exact rational exponents eᵢ over named
//     symbols (a Puiseux-style algebra). Radicals of monomials are
//     therefore free: √(gσ/ρ) is just g^{1/2}σ^{1/2}ρ^{-1/2}.
//     Radicals of sums are handled by adjoining a symbol S with a
//     rewrite relation S² → expr (ReduceSquare).
//   - Series: univariate truncated power series with Expr coefficients
//     (so series can carry free symbolic parameters exactly).
//   - Cplx:   complex combinations of Exprs.
//   - Field:  finite sums of terms  c · e^{i(Σ φ_v · v)}  with Cplx
//     coefficients and exact rational frequencies — closed under
//     exact differentiation and conjugation.
//
// Everything the spec layer certifies reduces to an identity in this
// kernel. The kernel is the trusted computing base; it depends only on
// math/big. Claims that cannot be reduced to kernel identities are
// declared as named axioms in the spec package's axiom ledger — they are
// assumed, visibly, never silently.
package exact

import (
	"fmt"
	"math"
	"math/big"
	"sort"
	"strings"
)

// term is a single monomial c · Π s^e. Exponents are nonzero rationals.
type term struct {
	coeff *big.Rat
	exps  map[string]*big.Rat
}

func (t *term) clone() *term {
	e := make(map[string]*big.Rat, len(t.exps))
	for k, v := range t.exps {
		e[k] = new(big.Rat).Set(v)
	}
	return &term{coeff: new(big.Rat).Set(t.coeff), exps: e}
}

// sig is the canonical signature of the exponent vector.
func (t *term) sig() string {
	keys := make([]string, 0, len(t.exps))
	for k := range t.exps {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	var b strings.Builder
	for _, k := range keys {
		b.WriteString(k)
		b.WriteByte('^')
		b.WriteString(t.exps[k].RatString())
		b.WriteByte(' ')
	}
	return b.String()
}

// Expr is a normalized finite sum of monomials.
type Expr struct {
	terms []*term // sorted by signature, no zero coefficients
}

// norm combines like terms, drops zeros, and sorts. All Expr values are
// built through norm, so equality is structural equality.
func norm(ts []*term) Expr {
	m := map[string]*term{}
	for _, t := range ts {
		if t.coeff.Sign() == 0 {
			continue
		}
		for k, v := range t.exps {
			if v.Sign() == 0 {
				delete(t.exps, k)
			}
		}
		s := t.sig()
		if ex, ok := m[s]; ok {
			ex.coeff.Add(ex.coeff, t.coeff)
		} else {
			m[s] = t
		}
	}
	sigs := make([]string, 0, len(m))
	for s, t := range m {
		if t.coeff.Sign() != 0 {
			sigs = append(sigs, s)
		}
	}
	sort.Strings(sigs)
	out := make([]*term, 0, len(sigs))
	for _, s := range sigs {
		out = append(out, m[s])
	}
	return Expr{terms: out}
}

// ---------------------------------------------------------------- constructors

// Zero returns the zero expression.
func Zero() Expr { return Expr{} }

// Int returns the constant n.
func Int(n int64) Expr { return FromRat(new(big.Rat).SetInt64(n)) }

// Rat returns the constant p/q.
func Rat(p, q int64) Expr { return FromRat(new(big.Rat).SetFrac64(p, q)) }

// FromRat returns the constant r.
func FromRat(r *big.Rat) Expr {
	return norm([]*term{{coeff: new(big.Rat).Set(r), exps: map[string]*big.Rat{}}})
}

// Sym returns the symbol s (assumed positive real throughout the suite).
func Sym(s string) Expr { return SymPow(s, 1, 1) }

// SymPow returns s^{p/q}.
func SymPow(s string, p, q int64) Expr {
	return norm([]*term{{
		coeff: new(big.Rat).SetInt64(1),
		exps:  map[string]*big.Rat{s: new(big.Rat).SetFrac64(p, q)},
	}})
}

// ---------------------------------------------------------------- arithmetic

// Add returns a + b.
func (a Expr) Add(b Expr) Expr {
	ts := make([]*term, 0, len(a.terms)+len(b.terms))
	for _, t := range a.terms {
		ts = append(ts, t.clone())
	}
	for _, t := range b.terms {
		ts = append(ts, t.clone())
	}
	return norm(ts)
}

// Neg returns -a.
func (a Expr) Neg() Expr {
	ts := make([]*term, 0, len(a.terms))
	for _, t := range a.terms {
		nt := t.clone()
		nt.coeff.Neg(nt.coeff)
		ts = append(ts, nt)
	}
	return norm(ts)
}

// Sub returns a - b.
func (a Expr) Sub(b Expr) Expr { return a.Add(b.Neg()) }

// Mul returns a · b.
func (a Expr) Mul(b Expr) Expr {
	var ts []*term
	for _, x := range a.terms {
		for _, y := range b.terms {
			t := x.clone()
			t.coeff.Mul(t.coeff, y.coeff)
			for k, v := range y.exps {
				if cur, ok := t.exps[k]; ok {
					cur.Add(cur, v)
				} else {
					t.exps[k] = new(big.Rat).Set(v)
				}
			}
			ts = append(ts, t)
		}
	}
	return norm(ts)
}

// single asserts a is a single monomial and returns it.
func (a Expr) single(op string) *term {
	if len(a.terms) != 1 {
		panic(fmt.Sprintf("exact: %s requires a single monomial, got %q", op, a.String()))
	}
	return a.terms[0]
}

// Inv returns 1/a for a single monomial a.
func (a Expr) Inv() Expr {
	t := a.single("Inv")
	nt := &term{coeff: new(big.Rat).Inv(t.coeff), exps: map[string]*big.Rat{}}
	for k, v := range t.exps {
		nt.exps[k] = new(big.Rat).Neg(v)
	}
	return norm([]*term{nt})
}

// Div returns a / b for a single-monomial divisor b.
func (a Expr) Div(b Expr) Expr { return a.Mul(b.Inv()) }

// PowInt returns aⁿ. Negative n requires a to be a single monomial.
func (a Expr) PowInt(n int) Expr {
	if n < 0 {
		return a.Inv().PowInt(-n)
	}
	r := Int(1)
	for i := 0; i < n; i++ {
		r = r.Mul(a)
	}
	return r
}

// MonoPow returns a^{p/q} for a single monomial a whose coefficient has an
// exact rational q-th root; it panics otherwise (the kernel refuses to
// approximate).
func (a Expr) MonoPow(p, q int64) Expr {
	t := a.single("MonoPow")
	r := new(big.Rat).SetFrac64(p, q)
	nt := &term{coeff: ratPowExact(t.coeff, p, q), exps: map[string]*big.Rat{}}
	for k, v := range t.exps {
		nt.exps[k] = new(big.Rat).Mul(v, r)
	}
	return norm([]*term{nt})
}

// Sqrt returns a^{1/2} for a single monomial a.
func (a Expr) Sqrt() Expr { return a.MonoPow(1, 2) }

// ---------------------------------------------------------------- calculus

// Deriv returns ∂a/∂v.
func (a Expr) Deriv(v string) Expr {
	var ts []*term
	for _, t := range a.terms {
		e, ok := t.exps[v]
		if !ok {
			continue
		}
		nt := t.clone()
		nt.coeff.Mul(nt.coeff, e)
		one := new(big.Rat).SetInt64(1)
		nt.exps[v].Sub(nt.exps[v], one)
		ts = append(ts, nt)
	}
	return norm(ts)
}

// ---------------------------------------------------------------- substitution

// SubstMono substitutes the single monomial m for symbol v (valid for any
// rational exponent of v, since monomial powers stay exact).
func (a Expr) SubstMono(v string, m Expr) Expr {
	mt := m.single("SubstMono")
	var ts []*term
	for _, t := range a.terms {
		e, ok := t.exps[v]
		if !ok {
			ts = append(ts, t.clone())
			continue
		}
		if !e.Num().IsInt64() || !e.Denom().IsInt64() {
			panic("exact: SubstMono exponent overflow")
		}
		nt := t.clone()
		delete(nt.exps, v)
		nt.coeff.Mul(nt.coeff, ratPowExact(mt.coeff, e.Num().Int64(), e.Denom().Int64()))
		for k, w := range mt.exps {
			add := new(big.Rat).Mul(w, e)
			if cur, ok := nt.exps[k]; ok {
				cur.Add(cur, add)
			} else {
				nt.exps[k] = add
			}
		}
		ts = append(ts, nt)
	}
	return norm(ts)
}

// SubstExpr substitutes an arbitrary expression val for symbol v; every
// occurrence of v must have a nonnegative integer exponent.
func (a Expr) SubstExpr(v string, val Expr) Expr {
	acc := Zero()
	for _, t := range a.terms {
		e, ok := t.exps[v]
		if !ok {
			acc = acc.Add(norm([]*term{t.clone()}))
			continue
		}
		if !e.IsInt() || e.Sign() < 0 || !e.Num().IsInt64() {
			panic(fmt.Sprintf("exact: SubstExpr needs nonneg integer exponent of %s", v))
		}
		nt := t.clone()
		delete(nt.exps, v)
		acc = acc.Add(norm([]*term{nt}).Mul(val.PowInt(int(e.Num().Int64()))))
	}
	return acc
}

// ReduceSquare rewrites every occurrence of v^e (integer e ≥ 2) using the
// adjunction relation v² = repl, until no such power remains. This is how
// radicals of sums (e.g. S = √(n1²+n2²)) are given exact meaning.
func (a Expr) ReduceSquare(v string, repl Expr) Expr {
	cur := a
	for {
		changed := false
		acc := Zero()
		two := new(big.Rat).SetInt64(2)
		for _, t := range cur.terms {
			e, ok := t.exps[v]
			if ok && e.IsInt() && e.Cmp(two) >= 0 {
				nt := t.clone()
				nt.exps[v].Sub(nt.exps[v], two)
				acc = acc.Add(norm([]*term{nt}).Mul(repl))
				changed = true
			} else {
				acc = acc.Add(norm([]*term{t.clone()}))
			}
		}
		cur = acc
		if !changed {
			return cur
		}
	}
}

// CoeffOf returns the coefficient of v^{p/q} in a (with v removed).
func (a Expr) CoeffOf(v string, p, q int64) Expr {
	target := new(big.Rat).SetFrac64(p, q)
	var ts []*term
	for _, t := range a.terms {
		e, ok := t.exps[v]
		if !ok {
			e = new(big.Rat) // exponent 0
		}
		if e.Cmp(target) == 0 {
			nt := t.clone()
			delete(nt.exps, v)
			ts = append(ts, nt)
		}
	}
	return norm(ts)
}

// ---------------------------------------------------------------- predicates

// IsZero reports whether a is identically zero.
func (a Expr) IsZero() bool { return len(a.terms) == 0 }

// Equal reports whether a and b are identical elements of the algebra.
func (a Expr) Equal(b Expr) bool { return a.Sub(b).IsZero() }

// IsPosMono reports whether a is a single monomial with positive
// coefficient — hence positive under the suite's convention that all
// symbols denote positive reals. This is the kernel's (sound, incomplete)
// positivity check.
func (a Expr) IsPosMono() bool {
	return len(a.terms) == 1 && a.terms[0].coeff.Sign() > 0
}

// NumTerms returns the number of monomials in a.
func (a Expr) NumTerms() int { return len(a.terms) }

// ---------------------------------------------------------------- evaluation

// EvalF64 numerically evaluates a at the given positive symbol values.
// This leaves the exact world — used only to tie the float runtime layer
// to the kernel, never inside a proof.
func (a Expr) EvalF64(vals map[string]float64) float64 {
	sum := 0.0
	for _, t := range a.terms {
		c, _ := t.coeff.Float64()
		for s, e := range t.exps {
			v, ok := vals[s]
			if !ok {
				panic("exact: EvalF64 missing value for symbol " + s)
			}
			ef, _ := e.Float64()
			c *= math.Pow(v, ef)
		}
		sum += c
	}
	return sum
}

// String renders a deterministically (for test diagnostics).
func (a Expr) String() string {
	if len(a.terms) == 0 {
		return "0"
	}
	parts := make([]string, 0, len(a.terms))
	for _, t := range a.terms {
		keys := make([]string, 0, len(t.exps))
		for k := range t.exps {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		s := t.coeff.RatString()
		for _, k := range keys {
			s += "*" + k
			if t.exps[k].Cmp(new(big.Rat).SetInt64(1)) != 0 {
				s += "^" + t.exps[k].RatString()
			}
		}
		parts = append(parts, s)
	}
	return strings.Join(parts, " + ")
}

// ---------------------------------------------------------------- exact roots

// ratPowExact returns c^{p/q} when it exists as an exact rational; panics
// otherwise.
func ratPowExact(c *big.Rat, p, q int64) *big.Rat {
	if q <= 0 {
		panic("exact: root index must be positive")
	}
	if c.Sign() == 0 {
		if p <= 0 {
			panic("exact: 0 to nonpositive power")
		}
		return new(big.Rat)
	}
	base := new(big.Rat).Set(c)
	if p < 0 {
		base.Inv(base)
		p = -p
	}
	num := new(big.Int).Exp(base.Num(), big.NewInt(p), nil)
	den := new(big.Int).Exp(base.Denom(), big.NewInt(p), nil)
	rn, ok1 := nthRootExact(num, q)
	rd, ok2 := nthRootExact(den, q)
	if !ok1 || !ok2 {
		panic(fmt.Sprintf("exact: %s has no exact %d-th root", c.RatString(), q))
	}
	return new(big.Rat).SetFrac(rn, rd)
}

// nthRootExact returns the exact integer q-th root of x if one exists.
func nthRootExact(x *big.Int, q int64) (*big.Int, bool) {
	if x.Sign() == 0 {
		return new(big.Int), true
	}
	if x.Sign() < 0 {
		if q%2 == 0 {
			return nil, false
		}
		r, ok := nthRootExact(new(big.Int).Neg(x), q)
		if !ok {
			return nil, false
		}
		return r.Neg(r), true
	}
	// binary search for y with y^q == x
	bits := int64(x.BitLen())
	hi := new(big.Int).Lsh(big.NewInt(1), uint(bits/q+2))
	lo := new(big.Int)
	bq := big.NewInt(q)
	for lo.Cmp(hi) < 0 {
		mid := new(big.Int).Add(lo, hi)
		mid.Add(mid, big.NewInt(1))
		mid.Rsh(mid, 1)
		p := new(big.Int).Exp(mid, bq, nil)
		switch p.Cmp(x) {
		case 0:
			return mid, true
		case -1:
			lo.Set(mid)
		default:
			hi.Sub(mid, big.NewInt(1))
		}
	}
	p := new(big.Int).Exp(lo, bq, nil)
	return lo, p.Cmp(x) == 0
}
