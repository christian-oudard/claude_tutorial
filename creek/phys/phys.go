// Package phys holds the float64 runtime constants and closed-form
// formulas used by the simulation and renderer.
//
// Every formula here is the numeric image of an expression certified in
// the spec package: the spec's float-tie tests evaluate the exact-kernel
// expressions and pin these functions against them. This is the
// "verified layer generates the runtime constants" bridge, in miniature —
// the renderer cannot silently drift from the checked math without a
// test failing.
package phys

import "math"

// Physical constants for clean water at ~15 °C (spec §1, §6).
const (
	SigmaWater = 0.073  // surface tension, N/m
	RhoWater   = 998.0  // density, kg/m³
	RhoAir     = 1.2    // air density, kg/m³
	MuWater    = 1.0e-3 // dynamic viscosity, Pa·s
	Grav       = 9.81   // gravity, m/s²
	NAir       = 1.000  // refractive index of air
	NWater     = 1.333  // refractive index of water (550 nm)
)

// NuWater is the kinematic viscosity of water, m²/s.
const NuWater = MuWater / RhoWater

// KCross is the gravity–capillary crossover wavenumber k_m = √(ρg/σ) (§3.1).
func KCross() float64 { return math.Sqrt(RhoWater * Grav / SigmaWater) }

// LambdaCross is the crossover wavelength λ_m = 2π√(σ/ρg) ≈ 1.7 cm (§3.1).
func LambdaCross() float64 { return 2 * math.Pi / KCross() }

// CMin is the minimum capillary–gravity phase speed (4gσ/ρ)^{1/4} (§3.1).
func CMin() float64 { return math.Pow(4*Grav*SigmaWater/RhoWater, 0.25) }

// Omega0 is the still-water capillary–gravity dispersion relation at
// finite depth: ω₀²  = (gk + (σ/ρ)k³) tanh(kh) (§3.1).
func Omega0(k, depth float64) float64 {
	if k <= 0 {
		return 0
	}
	return math.Sqrt((Grav*k + SigmaWater/RhoWater*k*k*k) * math.Tanh(k*depth))
}

// R0 is the unpolarized normal-incidence Fresnel reflectance ≈ 0.02 (§6.2).
func R0() float64 {
	r := (NWater - NAir) / (NWater + NAir)
	return r * r
}

// SchlickR is the Schlick approximation R0 + (1-R0)(1-cosθ)⁵ (§6.2).
func SchlickR(cosI float64) float64 {
	c := 1 - cosI
	c2 := c * c
	return R0() + (1-R0())*c2*c2*c
}

// FresnelR is the exact unpolarized Fresnel reflectance for light entering
// water from air at incidence cosine cosI (§6.2).
func FresnelR(cosI float64) float64 {
	sinI := math.Sqrt(math.Max(0, 1-cosI*cosI))
	sinT := NAir / NWater * sinI
	if sinT >= 1 {
		return 1 // total internal reflection (not reachable from air side)
	}
	cosT := math.Sqrt(1 - sinT*sinT)
	rs := (NAir*cosI - NWater*cosT) / (NAir*cosI + NWater*cosT)
	rp := (NWater*cosI - NAir*cosT) / (NWater*cosI + NAir*cosT)
	return 0.5 * (rs*rs + rp*rp)
}

// CriticalAngle is arcsin(n1/n2) ≈ 48.6° (§6.1), radians.
func CriticalAngle() float64 { return math.Asin(NAir / NWater) }

// BrewsterAngle is arctan(n2/n1) ≈ 53.1° (§6.2), radians.
func BrewsterAngle() float64 { return math.Atan(NWater / NAir) }

// SunSolidAngle is the solid angle of the 0.53°-diameter solar disk,
// Ω = 2π(1-cos(θ/2)) ≈ 6.8×10⁻⁵ sr (§6.4).
func SunSolidAngle() float64 {
	half := 0.53 * math.Pi / 180 / 2
	return 2 * math.Pi * (1 - math.Cos(half))
}
