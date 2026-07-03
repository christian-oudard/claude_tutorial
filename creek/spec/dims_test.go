package spec

// T1: dimensional consistency of every equation in the specification.
// Each case reduces to an exact identity between monomials in M, L, T
// with rational exponents — a decidable check, performed exactly.

import (
	"testing"

	"github.com/christian-oudard/claude_tutorial/creek/dim"
	"github.com/christian-oudard/claude_tutorial/creek/exact"
)

func d(name string) exact.Expr { return dim.Of(name) }

func TestDimensionalConsistency(t *testing.T) {
	L, T_ := dim.L, dim.T
	one := dim.Dimensionless

	cases := []struct {
		name string
		a, b exact.Expr
	}{
		// --- §1.1 bulk equations ---
		{"momentum: rho*Du/Dt has dim M L^-2 T^-2",
			d("density").Mul(d("velocity")).Div(d("time")), d("body_force_vol")},
		{"momentum: -grad p matches",
			d("pressure").Div(L), d("body_force_vol")},
		{"momentum: div(2 mu D) matches",
			d("dyn_visc").Mul(d("strain_rate")).Div(L), d("body_force_vol")},
		{"momentum: rho g matches",
			d("density").Mul(d("accel")), d("body_force_vol")},
		{"incompressibility: div(u) has dim 1/T",
			d("velocity").Div(L), exact.Int(1).Div(T_)},

		// --- §1.2 interface kinematics ---
		{"level set: d(phi)/dt matches u.grad(phi)",
			d("level_set").Div(d("time")), d("velocity").Mul(d("level_set")).Div(L)},
		{"level set: |grad phi| is dimensionless",
			d("level_set").Div(L), one},
		{"curvature kappa = div(n) has dim 1/L",
			one.Div(L), d("curvature")},
		{"VOF: d(alpha)/dt matches div(alpha u)",
			d("vol_frac").Div(d("time")), d("vol_frac").Mul(d("velocity")).Div(L)},

		// --- §1.3 jump conditions ---
		{"normal-stress jump: [p] matches sigma*kappa",
			d("pressure"), d("surf_tension").Mul(d("curvature"))},
		{"normal-stress jump: 2 mu n.D.n matches sigma*kappa",
			d("dyn_visc").Mul(d("strain_rate")), d("surf_tension").Mul(d("curvature"))},
		{"tangential-stress jump: viscous term matches grad_s sigma",
			d("dyn_visc").Mul(d("strain_rate")), d("surf_tension").Div(L)},
		{"CSF: f_sigma is a body force per volume",
			d("surf_tension").Mul(d("curvature")).Mul(d("dirac_line")), d("body_force_vol")},

		// --- §1.4 boundary conditions ---
		{"Cox-Voinov: capillary number Ca is dimensionless",
			d("dyn_visc").Mul(d("velocity")).Div(d("surf_tension")), one},
		{"outflow BC: U_c du/dn matches du/dt",
			d("velocity").Mul(d("velocity")).Div(L), d("velocity").Div(d("time"))},

		// --- §2 scale analysis ---
		{"Re = U h / nu is dimensionless",
			d("velocity").Mul(L).Div(d("kin_visc")), one},
		{"Kolmogorov eta = (nu^3/eps)^{1/4} has dim L",
			d("kin_visc").PowInt(3).Div(d("dissip_rate")).MonoPow(1, 4), L},
		{"capillary CFL: sqrt(rho dx^3/(4 pi sigma)) has dim T",
			d("density").Mul(L.PowInt(3)).Div(d("surf_tension")).Sqrt(), T_},
		{"viscous CFL: dx^2/(2 d nu) has dim T",
			L.PowInt(2).Div(d("kin_visc")), T_},
		{"Weber number dimensionless",
			d("density").Mul(d("velocity").PowInt(2)).Mul(L).Div(d("surf_tension")), one},
		{"Froude number dimensionless",
			d("velocity").Div(d("accel").Mul(L).Sqrt()), one},

		// --- §3 wave theory ---
		{"dispersion: g*k has dim 1/T^2",
			d("accel").Mul(d("wavenumber")), exact.Int(1).Div(T_.PowInt(2))},
		{"dispersion: (sigma/rho) k^3 has dim 1/T^2",
			d("surf_tension").Div(d("density")).Mul(d("wavenumber").PowInt(3)),
			exact.Int(1).Div(T_.PowInt(2))},
		{"Doppler: U.k has dim of omega",
			d("velocity").Mul(d("wavenumber")), d("ang_freq")},
		{"ray refraction dk/dt = -grad(U.k) consistent",
			d("wavenumber").Div(d("time")), d("velocity").Mul(d("wavenumber")).Div(L)},
		{"Phillips: L = U^2/g has dim L",
			d("velocity").PowInt(2).Div(d("accel")), L},

		// --- §4 depth-averaged flow ---
		{"SWE continuity: dh/dt matches div(h u)",
			L.Div(d("time")), L.Mul(d("velocity")).Div(L)},
		{"SWE momentum: div(h u x u) matches d(h u)/dt",
			L.Mul(d("velocity").PowInt(2)).Div(L), L.Mul(d("velocity")).Div(d("time"))},
		{"SWE momentum: div(1/2 g h^2) matches",
			d("accel").Mul(L.PowInt(2)).Div(L), L.Mul(d("velocity")).Div(d("time"))},
		{"SWE momentum: g h grad(b) matches",
			d("accel").Mul(L), L.Mul(d("velocity")).Div(d("time"))},
		{"SWE momentum: eddy term div(h nu_t grad u) matches",
			L.Mul(d("kin_visc")).Mul(d("velocity")).Div(L.PowInt(2)),
			L.Mul(d("velocity")).Div(d("time"))},
		{"Manning: tau_b/rho matches SWE momentum (n_M ~ s m^-1/3)",
			d("accel").Mul(d("manning_n").PowInt(2)).Mul(d("velocity").PowInt(2)).
				Div(exact.SymPow("L", 1, 3)),
			L.Mul(d("velocity")).Div(d("time"))},
		{"Manning n_M units are s m^-1/3 as stated",
			d("manning_n"), T_.Mul(exact.SymPow("L", -1, 3))},
		{"Chezy: tau_b/rho = C_f |u| u matches",
			d("velocity").PowInt(2), L.Mul(d("velocity")).Div(d("time"))},
		{"Boussinesq capillary term (sigma/rho) grad(lap zeta) has dim L/T^2",
			d("surf_tension").Div(d("density")).Mul(L).Div(L.PowInt(3)), d("accel")},

		// --- §5 turbulence ---
		{"Smagorinsky: (Cs Delta)^2 |D| is an eddy viscosity",
			L.PowInt(2).Mul(d("strain_rate")), d("kin_visc")},
		{"LES: d(tau_sgs)/dx has dim of per-mass accel",
			d("velocity").PowInt(2).Div(L), d("kin_accel")},
		{"Kolmogorov: C_K eps^{2/3} k^{-5/3} has dim of E(k)",
			d("dissip_rate").MonoPow(2, 3).Mul(d("wavenumber").MonoPow(-5, 3)),
			d("energy_spectrum")},
		{"Strouhal: f_shed = St U/d has dim 1/T",
			d("velocity").Div(L), exact.Int(1).Div(T_)},

		// --- §6 optics ---
		{"Beer-Lambert: c_lambda * ell is dimensionless",
			d("atten_coeff").Mul(L), one},
		{"slope variance: int k^2 S d^2k is dimensionless (S ~ L^4 in 2D)",
			d("wavenumber").PowInt(2).Mul(L.PowInt(4)).Mul(d("wavenumber").PowInt(2)), one},

		// --- §7 nesting ---
		{"GSD = r p_px / f has dim L", L.Mul(L).Div(L), L},
		{"motion-blur smear = U_s t_e has dim L", d("velocity").Mul(d("time")), L},
	}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if !dim.Same(c.a, c.b) {
				t.Errorf("dimension mismatch: %s vs %s", c.a, c.b)
			}
		})
	}
}
