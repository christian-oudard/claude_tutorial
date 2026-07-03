// Package dim provides dimensional analysis over the exact kernel.
//
// A dimension is a monomial in the SI base symbols M, L, T with exact
// rational exponents (rational exponents are load-bearing: Manning's
// roughness carries T·L^{-1/3}, the Kolmogorov spectrum carries ε^{2/3}).
// Dimensional consistency of an equation is then a decidable, exact
// identity check in the kernel — the same guarantee F#'s units of measure
// give at compile time, provided here as a library.
package dim

import "github.com/christian-oudard/claude_tutorial/creek/exact"

// Base dimensions.
var (
	M = exact.Sym("M")
	L = exact.Sym("L")
	T = exact.Sym("T")
)

// Dimensionless is the unit of the dimension group.
var Dimensionless = exact.Int(1)

// Catalog holds the canonical dimensions of every physical quantity used
// in the creek specification (mirrors the `dim` dict of
// creek_equations.py so drift between the two suites is greppable).
var Catalog = map[string]exact.Expr{
	"length":          L,
	"time":            T,
	"mass":            M,
	"velocity":        L.Div(T),
	"accel":           L.Div(T.PowInt(2)),
	"density":         M.Div(L.PowInt(3)),
	"dyn_visc":        M.Div(L.Mul(T)),
	"kin_visc":        L.PowInt(2).Div(T),
	"pressure":        M.Div(L.Mul(T.PowInt(2))),
	"stress":          M.Div(L.Mul(T.PowInt(2))),
	"strain_rate":     exact.Int(1).Div(T),
	"grad_u":          exact.Int(1).Div(T),
	"surf_tension":    M.Div(T.PowInt(2)),
	"curvature":       exact.Int(1).Div(L),
	"wavenumber":      exact.Int(1).Div(L),
	"ang_freq":        exact.Int(1).Div(T),
	"body_force_vol":  M.Div(L.PowInt(2).Mul(T.PowInt(2))),
	"kin_accel":       L.Div(T.PowInt(2)),
	"dirac_line":      exact.Int(1).Div(L),
	"level_set":       L,
	"vol_frac":        Dimensionless,
	"manning_n":       T.Mul(exact.SymPow("L", -1, 3)),
	"energy_spectrum": L.PowInt(3).Div(T.PowInt(2)),
	"dissip_rate":     L.PowInt(2).Div(T.PowInt(3)),
	"angle":           Dimensionless,
	"index":           Dimensionless,
	"atten_coeff":     exact.Int(1).Div(L),
}

// Of returns the catalog dimension for a named quantity.
func Of(name string) exact.Expr {
	d, ok := Catalog[name]
	if !ok {
		panic("dim: unknown quantity " + name)
	}
	return d
}

// Same reports whether two dimensions are identical.
func Same(a, b exact.Expr) bool { return a.Equal(b) }
