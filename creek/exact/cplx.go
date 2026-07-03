package exact

// Cplx is a complex combination Re + i·Im of kernel expressions.
type Cplx struct {
	Re, Im Expr
}

// CRe returns the real element e + 0i.
func CRe(e Expr) Cplx { return Cplx{Re: e, Im: Zero()} }

// CIm returns the imaginary element 0 + e·i.
func CIm(e Expr) Cplx { return Cplx{Re: Zero(), Im: e} }

// CAdd returns a + b.
func (a Cplx) Add(b Cplx) Cplx { return Cplx{Re: a.Re.Add(b.Re), Im: a.Im.Add(b.Im)} }

// Sub returns a - b.
func (a Cplx) Sub(b Cplx) Cplx { return Cplx{Re: a.Re.Sub(b.Re), Im: a.Im.Sub(b.Im)} }

// Neg returns -a.
func (a Cplx) Neg() Cplx { return Cplx{Re: a.Re.Neg(), Im: a.Im.Neg()} }

// Mul returns a · b.
func (a Cplx) Mul(b Cplx) Cplx {
	return Cplx{
		Re: a.Re.Mul(b.Re).Sub(a.Im.Mul(b.Im)),
		Im: a.Re.Mul(b.Im).Add(a.Im.Mul(b.Re)),
	}
}

// MulI returns i · a.
func (a Cplx) MulI() Cplx { return Cplx{Re: a.Im.Neg(), Im: a.Re} }

// Conj returns the complex conjugate of a.
func (a Cplx) Conj() Cplx { return Cplx{Re: a.Re, Im: a.Im.Neg()} }

// Scale returns e · a for a real scalar e.
func (a Cplx) Scale(e Expr) Cplx { return Cplx{Re: a.Re.Mul(e), Im: a.Im.Mul(e)} }

// IsZero reports whether a is identically zero.
func (a Cplx) IsZero() bool { return a.Re.IsZero() && a.Im.IsZero() }

// MapExpr applies f to both components.
func (a Cplx) MapExpr(f func(Expr) Expr) Cplx { return Cplx{Re: f(a.Re), Im: f(a.Im)} }
