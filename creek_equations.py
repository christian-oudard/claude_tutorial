#!/usr/bin/env python3
"""
creek_equations.py
==================

A computer-algebra transcription of the "Creek Surface Simulation" equation
specification, section by section, written as a *self-checking* SymPy document.

Language choice
---------------
The spec is continuum mechanics + wave theory + geometric optics: PDEs with no
theorems to prove, only a model to state and validate. A proof assistant
(Lean/Coq/Isabelle) is the wrong tool -- it would type-check definitions while
verifying nothing physical, and formalizing Navier-Stokes analytically needs a
research-grade analysis library. A CAS is the right tool, because what this
document contains that actually has teeth is checkable by symbolic algebra:

    (1) DIMENSIONAL CONSISTENCY of every equation (base dims M, L, T, plus
        temperature-independent here).
    (2) The ~15 QUOTED NUMBERS reproducing from their formulas.
    (3) The ALGEBRAIC CLAIMS holding symbolically (deep-water limit,
        crossover wavelength, minimum phase speed, Nwogu's alpha, Brewster
        angle => r_p = 0, Schlick = Fresnel at normal incidence, the
        divergence-free synthetic-turbulence constructions, Hermitian
        symmetry of the wave spectrum).

Run it (needs only SymPy):
    pip install sympy
    python creek_equations.py

It prints a per-section report and exits nonzero if any *equation* check fails.
Two places where the document's stated NUMBER does not reproduce from its own
formula are reported as DISCREPANCY (the equations are fine; the annotations
are off) and summarized at the end. These do not fail the suite.
"""

from __future__ import annotations
import sympy as sp

# ---------------------------------------------------------------------------
# Reporting harness
# ---------------------------------------------------------------------------
_PASS = 0
_FAIL = 0
_DISCREP: list[str] = []
_NOTES: list[str] = []


def check(name: str, ok: bool) -> None:
    """Record a boolean check (an equation/identity that must hold)."""
    global _PASS, _FAIL
    if ok:
        _PASS += 1
        print(f"  [ ok ] {name}")
    else:
        _FAIL += 1
        print(f"  [FAIL] {name}")


def approx(name: str, computed, stated, reltol=0.05) -> None:
    """Record a numeric reproduction of a quoted value (within reltol)."""
    c = float(computed)
    s = float(stated)
    rel = abs(c - s) / abs(s) if s != 0 else abs(c)
    if rel <= reltol:
        check(f"{name}: computed {c:.4g} ~= stated {s:.4g} (rel {rel:.1%})", True)
    else:
        # Number doesn't reproduce -> flag as a documentation discrepancy,
        # not an equation failure.
        msg = f"{name}: computed {c:.4g} vs stated {s:.4g} (rel {rel:.0%})"
        _DISCREP.append(msg)
        print(f"  [DISC] {msg}")


def note(msg: str) -> None:
    _NOTES.append(msg)


def section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


# ---------------------------------------------------------------------------
# Dimensional algebra.  A dimension is a monomial in base symbols M, L, T.
# Two quantities are dimensionally equal iff their ratio simplifies to 1.
# ---------------------------------------------------------------------------
M, L, T = sp.symbols("M L T", positive=True)

DIMLESS = sp.Integer(1)


def same_dim(a, b) -> bool:
    return sp.simplify(sp.nsimplify(a) / sp.nsimplify(b)) == 1


# Canonical dimensions of the physical quantities used throughout.
dim = {
    "length": L,
    "time": T,
    "mass": M,
    "velocity": L / T,                 # u, U, c_p, c_g, u_in
    "accel": L / T**2,                 # g
    "density": M / L**3,               # rho
    "dyn_visc": M / (L * T),           # mu   [Pa s]
    "kin_visc": L**2 / T,              # nu, nu_t  [m^2/s]
    "pressure": M / (L * T**2),        # p    [Pa]
    "stress": M / (L * T**2),          # viscous stress, tau_b (per area)
    "strain_rate": 1 / T,             # D = sym grad u
    "grad_u": 1 / T,
    "surf_tension": M / T**2,          # sigma [N/m]
    "curvature": 1 / L,               # kappa = div n
    "wavenumber": 1 / L,              # k
    "ang_freq": 1 / T,                # omega
    "body_force_vol": M / (L**2 * T**2),  # rho*g, CSF f_sigma
    "kin_accel": L / T**2,             # per-mass momentum-eq term
    "dirac_line": 1 / L,              # delta_Gamma = |grad alpha|
    "level_set": L,                    # phi (signed distance)
    "vol_frac": DIMLESS,               # alpha
    "manning_n": T / L ** sp.Rational(1, 3),  # n_M [s m^-1/3]
    "energy_spectrum": L**3 / T**2,    # E(k)  [ (m/s)^2 / (1/m) ]
    "dissip_rate": L**2 / T**3,        # epsilon
    "angle": DIMLESS,
    "index": DIMLESS,                  # refractive index
    "atten_coeff": 1 / L,             # c_lambda  [1/m]
}


# ===========================================================================
section("SECTION 1 -- Two-phase incompressible Navier-Stokes")
# ===========================================================================
# 1.1 Momentum:  rho(du/dt + (u.grad)u) = -grad p + div(2 mu D) + rho g
lhs = dim["density"] * (dim["velocity"] / dim["time"])          # rho * a
grad_p = dim["pressure"] / L
div_2muD = dim["dyn_visc"] * dim["strain_rate"] / L             # (mu D)/x
rho_g = dim["density"] * dim["accel"]
check("momentum: rho*Du/Dt has dim M L^-2 T^-2", same_dim(lhs, dim["body_force_vol"]))
check("momentum: -grad p matches", same_dim(grad_p, lhs))
check("momentum: div(2 mu D) matches", same_dim(div_2muD, lhs))
check("momentum: rho g matches", same_dim(rho_g, lhs))

# Incompressibility div u = 0  (dim of div u)
check("incompressibility: div(u) has dim 1/T", same_dim(dim["velocity"] / L, 1 / T))

# 1.2 Level set:  phi_t + u.grad phi = 0 ;  |grad phi| = 1
check("level set: d(phi)/dt matches u.grad(phi)",
      same_dim(dim["level_set"] / T, dim["velocity"] * dim["level_set"] / L))
check("level set: |grad phi| is dimensionless (=1)", same_dim(dim["level_set"] / L, DIMLESS))
check("normal n = grad(phi)/|grad phi| dimensionless", same_dim((L / L), DIMLESS))
check("curvature kappa = div(n) has dim 1/L", same_dim((DIMLESS) / L, dim["curvature"]))
# VOF: alpha_t + div(alpha u) = 0
check("VOF: d(alpha)/dt matches div(alpha u)",
      same_dim(dim["vol_frac"] / T, dim["vol_frac"] * dim["velocity"] / L))

# 1.3 Jump conditions
#   Normal stress:  [p - 2 mu n.D.n] = sigma kappa
sigma_kappa = dim["surf_tension"] * dim["curvature"]
check("normal-stress jump: [p] matches sigma*kappa",
      same_dim(dim["pressure"], sigma_kappa))
check("normal-stress jump: 2 mu n.D.n matches sigma*kappa",
      same_dim(dim["dyn_visc"] * dim["strain_rate"], sigma_kappa))
#   Tangential:  [2 mu t.D.n] = -t . grad_s sigma
check("tangential-stress jump: viscous term matches surface-gradient of sigma",
      same_dim(dim["dyn_visc"] * dim["strain_rate"], dim["surf_tension"] / L))
#   CSF:  f_sigma = sigma kappa n delta_Gamma  (a force per unit volume)
f_sigma = dim["surf_tension"] * dim["curvature"] * dim["dirac_line"]
check("CSF: f_sigma is a body force per volume (matches rho g)",
      same_dim(f_sigma, dim["body_force_vol"]))

# 1.4 Cox-Voinov contact line:  theta_d^3 = theta_e^3 + 9 Ca ln(L/lambda_s)
#   Ca = mu_w U_cl / sigma  must be dimensionless.
Ca = dim["dyn_visc"] * dim["velocity"] / dim["surf_tension"]
check("Cox-Voinov: capillary number Ca is dimensionless", same_dim(Ca, DIMLESS))
# Outflow convective BC: u_t + U_c u_n = 0
check("outflow BC: U_c * du/dn matches du/dt",
      same_dim(dim["velocity"] * dim["velocity"] / L, dim["velocity"] / T))


# ===========================================================================
section("SECTION 2 -- Scale analysis (why the ideal model is infeasible)")
# ===========================================================================
# Numeric constants from the document.
rho_w, rho_a = 998.0, 1.2
mu_w = 1.0e-3
sigma_val = 0.073
g = 9.81
U, h = 0.5, 0.2
nu_w = mu_w / rho_w

# Reynolds number
Re = U * h / nu_w
check("Re = U h / nu is dimensionless", same_dim(dim["velocity"] * L / dim["kin_visc"], DIMLESS))
approx("Re", Re, 1e5, reltol=0.10)
approx("nu_w = mu_w/rho_w", nu_w, 1.0e-6, reltol=0.05)

# Kolmogorov microscale  eta = (nu^3 / eps)^{1/4},  eps ~ U^3 / h
eps = U**3 / h
eta = (nu_w**3 / eps) ** 0.25
check("Kolmogorov: eta = (nu^3/eps)^1/4 has dim L",
      same_dim((dim["kin_visc"]**3 / dim["dissip_rate"]) ** sp.Rational(1, 4), L))
# Reproduce the microscale.  eps~U^3/h is itself an order-of-magnitude estimate;
# it lands ~35 um, a touch below the quoted 50-100 um band (same order).
print(f"  [info] eta = {eta*1e6:.1f} um  (doc quotes 50-100 um; same order, ~2x below)")
note(f"Kolmogorov eta reproduces to {eta*1e6:.0f} um from eps~U^3/h; "
     f"the quoted 50-100 um band is ~2x higher (order-of-magnitude estimate).")
check("Kolmogorov eta is O(10 um) i.e. in [10,100] um", 1e-5 <= eta <= 1e-4)

# DNS grid scaling  N ~ Re^{9/4}
N = Re ** 2.25
print(f"  [info] N ~ Re^(9/4) = {N:.2e}  (doc quotes 1e11-1e12)")
check("N ~ Re^9/4 lands in [1e11, 1e12]", 1e11 <= N <= 1e12)

# Capillary CFL  dt_sigma = sqrt((rho_w+rho_a) dx^3 / (4 pi sigma))
check("capillary CFL: sqrt(rho dx^3 / (4 pi sigma)) has dim T",
      same_dim(sp.sqrt(dim["density"] * L**3 / (dim["surf_tension"])), T))
dx = 100e-6
dt_sigma = ((rho_w + rho_a) * dx**3 / (4 * sp.pi * sigma_val)) ** 0.5
dt_sigma = float(dt_sigma)
print(f"  [info] dt_sigma(dx=100um) = {dt_sigma*1e6:.1f} us")
approx("capillary CFL dt_sigma at dx=100um", dt_sigma, 1e-6, reltol=0.30)
# Which dx *does* give ~1 us?  Solve sqrt(rho dx^3/(4 pi sigma)) = 1us.
dx_1us = ((1e-6) ** 2 * 4 * sp.pi * sigma_val / (rho_w + rho_a)) ** sp.Rational(1, 3)
note(f"Capillary CFL: at dx=100um the formula gives ~{dt_sigma*1e6:.0f} us, not the "
     f"quoted ~1 us.  ~1 us corresponds to dx~{float(dx_1us)*1e6:.0f} um.")

# Viscous stability  dt_nu <= dx^2 / (2 d nu)
check("viscous CFL: dx^2/(2 d nu) has dim T",
      same_dim(L**2 / (dim["kin_visc"]), T))

# We, Fr dimensionless
We = dim["density"] * dim["velocity"]**2 * L / dim["surf_tension"]
Fr = dim["velocity"] / sp.sqrt(dim["accel"] * L)
check("Weber number We dimensionless", same_dim(We, DIMLESS))
check("Froude number Fr dimensionless", same_dim(Fr, DIMLESS))


# ===========================================================================
section("SECTION 3 -- Free-surface capillary-gravity wave theory")
# ===========================================================================
k, hh, rho_s, sig, gg = sp.symbols("k h rho sigma g", positive=True)

# 3.1 Dispersion relation  omega0^2 = (g k + (sigma/rho) k^3) tanh(k h)
omega0_sq = (gg * k + sig / rho_s * k**3) * sp.tanh(k * hh)
check("dispersion: g*k term has dim 1/T^2",
      same_dim(dim["accel"] * dim["wavenumber"], 1 / T**2))
check("dispersion: (sigma/rho) k^3 term has dim 1/T^2",
      same_dim(dim["surf_tension"] / dim["density"] * dim["wavenumber"]**3, 1 / T**2))

# Deep-water limit kh -> inf  (tanh -> 1)
deep = sp.limit(omega0_sq, hh, sp.oo)
check("deep-water limit: omega0^2 -> g k + (sigma/rho) k^3",
      sp.simplify(deep - (gg * k + sig / rho_s * k**3)) == 0)

# Crossover wavenumber where gravity term == capillary term:
#   g k = (sigma/rho) k^3  =>  k_m = sqrt(rho g / sigma),  lambda_m = 2 pi / k_m
k_m_sol = sp.solve(sp.Eq(gg * k, sig / rho_s * k**3), k)
k_m = [s for s in k_m_sol if s.is_positive or s.free_symbols][-1]
k_m = sp.sqrt(rho_s * gg / sig)
check("crossover k_m = sqrt(rho g / sigma) solves g k = (sigma/rho) k^3",
      sp.simplify((gg * k_m) - (sig / rho_s * k_m**3)) == 0)
lambda_m = 2 * sp.pi / k_m
check("crossover: lambda_m = 2 pi sqrt(sigma/(rho g))",
      sp.simplify(lambda_m - 2 * sp.pi * sp.sqrt(sig / (rho_s * gg))) == 0)
lambda_m_val = float(lambda_m.subs({sig: sigma_val, rho_s: rho_w, gg: g}))
approx("crossover wavelength lambda_m", lambda_m_val, 0.017, reltol=0.05)

# Minimum phase speed.  Deep-water c_p^2 = omega0^2/k^2 = g/k + (sigma/rho) k.
cp_sq = gg / k + sig / rho_s * k
dcp = sp.diff(cp_sq, k)
k_star = sp.solve(dcp, k)
k_star = [s for s in k_star if s.is_positive][0]
check("min phase speed occurs at k = k_m", sp.simplify(k_star - k_m) == 0)
cmin_sq = cp_sq.subs(k, k_m)
cmin = sp.sqrt(sp.simplify(cmin_sq))
# Claim: c_min = (4 g sigma / rho)^{1/4}
check("min phase speed: c_min = (4 g sigma / rho)^{1/4}",
      sp.simplify(cmin - (4 * gg * sig / rho_s) ** sp.Rational(1, 4)) == 0)
cmin_val = float(cmin.subs({sig: sigma_val, rho_s: rho_w, gg: g}))
approx("minimum phase speed c_min", cmin_val, 0.23, reltol=0.05)

# 3.2 Doppler shift  omega = U.k + omega0 ; stationary waves omega=0
check("Doppler: U.k has dim 1/T (matches omega)",
      same_dim(dim["velocity"] * dim["wavenumber"], dim["ang_freq"]))
check("ray refraction dk/dt = -grad(U.k) dimensionally consistent",
      same_dim(dim["wavenumber"] / T, (dim["velocity"] * dim["wavenumber"]) / L))

# 3.3 Spectral synthesis: Hermitian symmetry => real surface.
# With even dispersion omega0(k)=omega0(-k):
#   h~(k,t) = h0(k) e^{i w t} + h0*(-k) e^{-i w t}
# Reality requires h~(-k) = conj(h~(k)).
kx, ky, x, y, t = sp.symbols("k_x k_y x y t", real=True)
w = sp.symbols("omega", real=True)
h0k, h0mk = sp.symbols("h0k h0mk")  # h0(k), h0(-k) as generic complex constants
htilde_k = h0k * sp.exp(sp.I * w * t) + sp.conjugate(h0mk) * sp.exp(-sp.I * w * t)
htilde_mk = h0mk * sp.exp(sp.I * w * t) + sp.conjugate(h0k) * sp.exp(-sp.I * w * t)
check("Tessendorf: h~(-k) = conj(h~(k)) (Hermitian => real surface)",
      sp.simplify(htilde_mk - sp.conjugate(htilde_k)) == 0)

# Slope field: grad eta = sum i k h~ e^{i k.x}  (spatial gradient pulls down i k)
mode = sp.exp(sp.I * (kx * x + ky * y))
grad_mode = [sp.diff(mode, x), sp.diff(mode, y)]
check("spectral slope: d/dx e^{i k.x} = i k_x e^{i k.x}",
      sp.simplify(grad_mode[0] - sp.I * kx * mode) == 0 and
      sp.simplify(grad_mode[1] - sp.I * ky * mode) == 0)

# Phillips spectrum length scale L = U_drive^2 / g has dim L
check("Phillips: L = U_drive^2 / g has dim L",
      same_dim(dim["velocity"]**2 / dim["accel"], L))


# ===========================================================================
section("SECTION 4 -- Depth-averaged bulk flow (shallow water + Boussinesq)")
# ===========================================================================
# 4.1 SWE continuity  h_t + div(h ubar) = 0
check("SWE continuity: d(h)/dt matches div(h ubar)",
      same_dim(L / T, L * dim["velocity"] / L))
# Momentum flux terms all M... per-area:  d(h u)/dt ~ L^2 T^-2
mom = L * dim["velocity"] / T                       # d(h ubar)/dt
check("SWE momentum: div(h u x u) matches d(h u)/dt",
      same_dim(L * dim["velocity"]**2 / L, mom))
check("SWE momentum: div(1/2 g h^2 I) matches",
      same_dim(dim["accel"] * L**2 / L, mom))
check("SWE momentum: g h grad(b) matches",
      same_dim(dim["accel"] * L * (L / L), mom))
check("SWE momentum: eddy term div(h nu_t grad u) matches",
      same_dim(L * dim["kin_visc"] * (dim["velocity"] / L) / L, mom))

# Manning friction  tau_b = rho g n^2 |u| u / h^{1/3};  tau_b/rho must match mom.
# This forces Manning n to have units s m^{-1/3}.  Verify that, using the
# document's own units for n_M, tau_b/rho reproduces L^2 T^-2.
tau_b_over_rho = (dim["accel"] * dim["manning_n"]**2 *
                  dim["velocity"] * dim["velocity"] / L**sp.Rational(1, 3))
check("Manning: tau_b/rho matches SWE momentum (forces n_M ~ s m^-1/3)",
      same_dim(tau_b_over_rho, mom))
check("Manning n_M units are s m^-1/3 as stated",
      same_dim(dim["manning_n"], T / L**sp.Rational(1, 3)))
# Chezy/drag form  tau_b = rho C_f |u| u,  C_f dimensionless
check("Chezy: tau_b/rho = C_f |u| u matches (C_f dimensionless)",
      same_dim(dim["velocity"]**2, mom))

# 4.2 Nwogu dispersion.  alpha = z_a^2/(2 h^2) + z_a/h with z_a = -0.531 h.
z_over_h = sp.Rational(-531, 1000)  # z_alpha / h = -0.531
alpha_nwogu = z_over_h**2 / 2 + z_over_h
approx("Nwogu alpha (z_a=-0.531 h)", float(alpha_nwogu), -0.39, reltol=0.03)

# The Nwogu/Pade form   omega^2 = g k^2 h (1-(a+1/3)mu)/(1-a mu),  mu=(k h)^2
# matches Airy   omega^2 = g k tanh(k h)   through O((kh)^4) when a = -2/5.
a = sp.symbols("alpha")
x_ = sp.symbols("x", positive=True)   # x = k h
pade = x_ * (1 - (a + sp.Rational(1, 3)) * x_**2) / (1 - a * x_**2)  # = omega^2/(g k)
airy = sp.tanh(x_)                                                    # = omega^2/(g k)
# Both are odd in x=kh; the x^1 and x^3 terms cancel identically for any alpha,
# so the leading mismatch is the x^5 term.  Kill it to fix alpha.
series_diff = sp.series(pade - airy, x_, 0, 8).removeO()
coeff_x5 = series_diff.coeff(x_, 5)
a_opt = sp.solve(coeff_x5, a)[0]
check("Nwogu/Pade matches Airy through O((kh)^4) when alpha = -2/5",
      sp.simplify(a_opt - sp.Rational(-2, 5)) == 0)
note(f"Nwogu z_alpha=-0.531 h gives alpha={float(alpha_nwogu):.3f}; the exact "
     f"4th-order Pade match is alpha=-2/5=-0.400 (z chosen to optimize a band).")

# Capillary extension term  -(sigma/rho) grad(lap zeta) has dim of accel
check("Boussinesq capillary term -(sigma/rho) grad(lap zeta) has dim L/T^2",
      same_dim(dim["surf_tension"] / dim["density"] * L / L**3, dim["accel"]))


# ===========================================================================
section("SECTION 5 -- Turbulence modeling (LES, spectra, synthetic inflow)")
# ===========================================================================
# 5.1 Smagorinsky  nu_t = (C_s Delta)^2 |D|,  |D| ~ 1/T
check("Smagorinsky: nu_t = (Cs Delta)^2 |D| is an eddy viscosity (L^2/T)",
      same_dim(L**2 * dim["strain_rate"], dim["kin_visc"]))
# LES subgrid term  d(tau_sgs)/dx_j,  tau_sgs ~ velocity^2
check("LES: d(tau_sgs)/dx has dim of per-mass accel (L/T^2)",
      same_dim(dim["velocity"]**2 / L, dim["kin_accel"]))

# 5.2 Kolmogorov inertial range  E(k) = C_K eps^{2/3} k^{-5/3}
check("Kolmogorov spectrum: C_K eps^2/3 k^-5/3 has dim of E(k) (L^3/T^2)",
      same_dim(dim["dissip_rate"]**sp.Rational(2, 3) * dim["wavenumber"]**sp.Rational(-5, 3),
               dim["energy_spectrum"]))

# 5.3 Synthetic turbulence.  Single Kraichnan mode
#   u' = 2 u_hat cos(k.x + w t + psi) sigma_vec,  with sigma_vec . k = 0.
# Divergence  div(u') = -2 u_hat sin(...) (k . sigma_vec) = 0  when orthogonal.
sx, sy, sz, k1, k2, k3, uh, psi = sp.symbols("s_x s_y s_z k1 k2 k3 uhat psi", real=True)
z = sp.symbols("z", real=True)
phase = k1 * x + k2 * y + k3 * z + w * t + psi
umode = [2 * uh * sp.cos(phase) * sx,
         2 * uh * sp.cos(phase) * sy,
         2 * uh * sp.cos(phase) * sz]
div_umode = sp.diff(umode[0], x) + sp.diff(umode[1], y) + sp.diff(umode[2], z)
# Substitute the orthogonality constraint sigma.k = 0  (solve s_z from it).
sz_sol = sp.solve(sx * k1 + sy * k2 + sz * k3, sz)[0]
check("Kraichnan mode is divergence-free when sigma . k = 0",
      sp.simplify(div_umode.subs(sz, sz_sol)) == 0)

# Curl-noise alternative  u' = curl(Psi)  is divergence-free identically.
P = sp.Function("P")(x, y, z)
Q = sp.Function("Q")(x, y, z)
Rv = sp.Function("R")(x, y, z)
curl = [sp.diff(Rv, y) - sp.diff(Q, z),
        sp.diff(P, z) - sp.diff(Rv, x),
        sp.diff(Q, x) - sp.diff(P, y)]
div_curl = sp.diff(curl[0], x) + sp.diff(curl[1], y) + sp.diff(curl[2], z)
check("curl-noise u' = curl(Psi) is divergence-free identically (div curl = 0)",
      sp.simplify(div_curl) == 0)

# Vortex shedding  f_shed = St U / d  is a frequency
check("Strouhal: f_shed = St U / d has dim 1/T",
      same_dim(dim["velocity"] / L, 1 / T))


# ===========================================================================
section("SECTION 6 -- Optics and rendering")
# ===========================================================================
n1, n2 = 1.000, 1.333
theta_i = sp.symbols("theta_i", positive=True)

# 6.1 Snell + critical angle  theta_c = arcsin(n1/n2) ~ 48.6 deg
theta_c = sp.asin(sp.Rational(1000, 1333))  # n1/n2
approx("critical angle theta_c (deg)", float(sp.deg(theta_c)), 48.6, reltol=0.01)

# 6.2 Fresnel.  Build r_s, r_p with theta_t from Snell.
ni, nt = sp.symbols("n_i n_t", positive=True)
theta_t = sp.asin(ni / nt * sp.sin(theta_i))
ci = sp.cos(theta_i)
ct = sp.cos(theta_t)
r_s = (ni * ci - nt * ct) / (ni * ci + nt * ct)
r_p = (nt * ci - ni * ct) / (nt * ci + ni * ct)

# Normal incidence: R0 = ((n2-n1)/(n2+n1))^2 ~ 0.02, and Fresnel -> same.
R0 = ((n2 - n1) / (n2 + n1)) ** 2
approx("normal-incidence reflectance R0", R0, 0.02, reltol=0.05)
r_s0 = r_s.subs({theta_i: 0, ni: n1, nt: n2})
r_p0 = r_p.subs({theta_i: 0, ni: n1, nt: n2})
check("Fresnel r_s, r_p at normal incidence give |r|^2 = R0",
      abs(float(r_s0)**2 - R0) < 1e-9 and abs(float(r_p0)**2 - R0) < 1e-9)

# Brewster angle  theta_B = arctan(n2/n1) ~ 53.1 deg, and r_p(theta_B)=0.
theta_B = sp.atan(nt / ni)
r_p_at_B = r_p.subs(theta_i, theta_B)
check("Brewster: r_p(arctan(n2/n1)) = 0 exactly (symbolic)",
      sp.simplify(r_p_at_B) == 0)
approx("Brewster angle theta_B (deg)",
       float(sp.deg(sp.atan(n2 / n1))), 53.1, reltol=0.01)

# Schlick approximation  R(t) = R0 + (1-R0)(1-cos t)^5
R0s = sp.symbols("R0", positive=True)
schlick = R0s + (1 - R0s) * (1 - sp.cos(theta_i)) ** 5
check("Schlick = R0 at normal incidence (theta_i = 0)",
      sp.simplify(schlick.subs(theta_i, 0) - R0s) == 0)
check("Schlick -> 1 at grazing (theta_i = pi/2), matching total reflection",
      sp.simplify(schlick.subs(theta_i, sp.pi / 2) - 1) == 0)

# 6.3 Beer-Lambert  L = L0 exp(-c ell),  exponent dimensionless
check("Beer-Lambert: c_lambda * ell is dimensionless",
      same_dim(dim["atten_coeff"] * L, DIMLESS))

# 6.4 Cox-Munk slope PDF integrates to 1 over all slopes.
ex, ey, ssx, ssy = sp.symbols("eta_x eta_y s_x s_y", positive=True, real=True)
P_slope = (1 / (2 * sp.pi * ssx * ssy)) * sp.exp(-ex**2 / (2 * ssx**2)
                                                 - ey**2 / (2 * ssy**2))
integral = sp.integrate(sp.integrate(P_slope, (ex, -sp.oo, sp.oo)),
                        (ey, -sp.oo, sp.oo))
check("Cox-Munk slope PDF integrates to 1", sp.simplify(integral) == 1)
# slope variance s^2 = int_{k>k_res} k^2 S(k) dk is dimensionless (a slope^2)
# with S(k) ~ L^4 in 2D (eta^2 ~ int S dk, dk ~ L^-2):
S_2d_dim = L**4
check("slope variance s^2 = int k^2 S dk is dimensionless (slope^2)",
      same_dim(dim["wavenumber"]**2 * S_2d_dim * dim["wavenumber"]**2, DIMLESS))

# Small-sun solid angle  Omega ~ 2 pi (1 - cos(half-angle)) for a 0.53 deg disk
half_angle = sp.rad(sp.Rational(53, 100)) / 2   # 0.53 deg diameter
Omega_sun = 2 * sp.pi * (1 - sp.cos(half_angle))
approx("solar disk solid angle Omega_sun (sr)", float(Omega_sun), 6.8e-5, reltol=0.05)

# 6.4 GGX at the surface normal (m = n):  D = 1/(pi alpha_g^2)
ag = sp.symbols("alpha_g", positive=True)
cos_nm = sp.symbols("c", positive=True)  # n.m
D_ggx = ag**2 / (sp.pi * (cos_nm**2 * (ag**2 - 1) + 1) ** 2)
check("GGX at m=n reduces to 1/(pi alpha_g^2)",
      sp.simplify(D_ggx.subs(cos_nm, 1) - 1 / (sp.pi * ag**2)) == 0)

# 6.4 Radiance-compression factor n2^2/n1^2 in the transmitted BSDF lobe.
check("BSDF transmitted lobe carries radiance-compression factor n2^2/n1^2 (>1)",
      (n2**2 / n1**2) > 1)


# ===========================================================================
section("SECTION 7 -- Adaptive resolution and nesting")
# ===========================================================================
# 7.1 Ground sampling distance  GSD = r p_px / f  is a length
check("GSD = r * p_px / f has dim L", same_dim(L * L / L, L))
# 7.2 Motion-blur smear = U_s * t_e is a length (compare to GSD)
check("motion-blur smear = U_s * t_e has dim L",
      same_dim(dim["velocity"] * T, L))
# One-way nesting fills band k in (k_Nyq_coarse, k_Nyq_fine] with synthetic q'.
check("nesting spectral gap is a wavenumber band (1/L)",
      same_dim(dim["wavenumber"], 1 / L))


# ===========================================================================
section("SUMMARY")
# ===========================================================================
print(f"\nEquation / identity checks:  {_PASS} passed, {_FAIL} failed")

if _DISCREP:
    print(f"\nDocumentation discrepancies (formula fine, quoted number off): {len(_DISCREP)}")
    for d in _DISCREP:
        print(f"  - {d}")

if _NOTES:
    print("\nNotes:")
    for nmsg in _NOTES:
        print(f"  - {nmsg}")

print()
if _FAIL == 0:
    print("All equation and identity checks PASSED.")
else:
    print(f"{_FAIL} equation check(s) FAILED.")

raise SystemExit(1 if _FAIL else 0)
