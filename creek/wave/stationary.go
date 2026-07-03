package wave

import (
	"math"

	"github.com/christian-oudard/claude_tutorial/creek/phys"
)

// This file implements the rock-locked stationary waves of §3.2: the
// ripple crescents anchored upstream of bed obstacles, which give a creek
// its characteristic non-homogeneous texture. A Gaussian spectral sea
// (§3.3) is statistically uniform by construction and can never produce
// them; they are the ω = 0 solutions of the Doppler-shifted dispersion
// relation,
//
//	U·k = -ω₀(k)  (stationary in the lab frame)
//
// whose existence requires |U| ≥ c_min — the certified minimum
// capillary–gravity phase speed. The wavelengths below are not tuned:
// they are solved from the same dispersion relation the spec suite
// certifies, per propagation direction.

// The stationarity condition k U cosθ = ω₀(k) has TWO roots when
// U cosθ > c_min — the phase-speed curve is U-shaped with its certified
// minimum at k_m (TestMinimumPhaseSpeed). The gravity branch (k < k_m,
// λ ~ 2πU²/g ~ 16 cm at 0.5 m/s) forms the visible wake trains downstream
// of a rock; the capillary branch (k > k_m, λ ~ 2 mm) forms the fine
// crescents upstream (its group velocity exceeds its phase velocity, so
// energy outruns the obstacle). Both vanish below c_min: one certified
// constant gates both features.

// KStationaryCapillary solves the stationarity condition on the capillary
// branch (k > k_m) at angle theta to the upstream axis.
func KStationaryCapillary(U, depth, theta float64) (float64, bool) {
	uc := U * math.Cos(theta)
	if uc <= phys.CMin() {
		return 0, false
	}
	f := func(k float64) float64 { return phys.Omega0(k, depth) - k*uc }
	lo, hi := phys.KCross(), 2e5
	if f(lo) >= 0 || f(hi) <= 0 {
		return 0, false
	}
	for i := 0; i < 80; i++ {
		mid := 0.5 * (lo + hi)
		if f(mid) < 0 {
			lo = mid
		} else {
			hi = mid
		}
	}
	return 0.5 * (lo + hi), true
}

// KStationaryGravity solves the stationarity condition on the gravity
// branch (k < k_m): the long stationary waves of the downstream wake.
func KStationaryGravity(U, depth, theta float64) (float64, bool) {
	uc := U * math.Cos(theta)
	if uc <= phys.CMin() {
		return 0, false
	}
	f := func(k float64) float64 { return phys.Omega0(k, depth) - k*uc }
	lo, hi := 0.5, phys.KCross()
	if f(lo) <= 0 || f(hi) >= 0 {
		return 0, false // uc >= c_p(k->0) = sqrt(gh): supercritical shallow flow
	}
	for i := 0; i < 80; i++ {
		mid := 0.5 * (lo + hi)
		if f(mid) > 0 {
			lo = mid
		} else {
			hi = mid
		}
	}
	return 0.5 * (lo + hi), true
}

// RockField holds one precomputed stationary interference pattern (in the
// local frame of a rock: ξ upstream, ζ across) instanced at several rock
// positions. Stationary means stationary: the pattern costs nothing per
// frame.
type RockField struct {
	Np       int
	Lp       float64 // local patch size, m
	CellSize float64
	Rocks    [][2]float64 // world positions

	upx, upy float64 // upstream unit vector (world)

	h, sxi, szeta []float64 // pattern and local-frame slopes
}

// Branch selects which stationary-wave family a RockField carries.
type Branch int

const (
	// Capillary: fine upstream crescents, k > k_m, strong viscous decay.
	Capillary Branch = iota
	// Gravity: long downstream wake trains, k < k_m, weak decay.
	Gravity
)

// NewRockField synthesizes the stationary pattern for flow (ux,uy) at the
// given depth, with peak amplitude amp (m). Wave directions θ ∈ ±72° are
// superposed with a cos²θ directional weight and a decay envelope on the
// side of the rock the branch physically occupies; each direction's
// wavenumber is solved from the certified dispersion relation.
func NewRockField(ux, uy, depth, amp float64, branch Branch, rocks [][2]float64) *RockField {
	U := math.Hypot(ux, uy)
	rf := &RockField{
		Np: 256, Lp: 0.7,
		Rocks: rocks,
		upx:   -ux / U, upy: -uy / U,
	}
	solver := KStationaryCapillary
	side, decay := 1.0, 0.09 // upstream, fast viscous decay
	if branch == Gravity {
		solver = KStationaryGravity
		side, decay = -1.0, 0.85 // downstream wake, slow decay
		rf.Np, rf.Lp = 512, 2.6  // long waves need a big patch
	}
	rf.CellSize = rf.Lp / float64(rf.Np)
	n := rf.Np
	rf.h = make([]float64, n*n)
	rf.sxi = make([]float64, n*n)
	rf.szeta = make([]float64, n*n)

	type mode struct{ k, ct, st, w float64 }
	var modes []mode
	for th := -1.25; th <= 1.2501; th += 0.05 {
		if k, ok := solver(U, depth, th); ok {
			c := math.Cos(th)
			modes = append(modes, mode{k, c, math.Sin(th), c * c})
		}
	}
	if len(modes) == 0 {
		return rf // subcritical flow: empty field, correctly
	}

	peak := 0.0
	for j := 0; j < n; j++ {
		zeta := (float64(j)+0.5)*rf.CellSize - rf.Lp/2 // across-flow
		for i := 0; i < n; i++ {
			xi := (float64(i)+0.5)*rf.CellSize - rf.Lp/2 // upstream
			rho := math.Hypot(xi, zeta)
			if rho < 0.02 {
				continue // over the rock itself
			}
			// the pattern lives on its branch's side of the rock, decaying
			// with distance (the §3.2 dissipation term D).
			env := math.Exp(-rho/decay) * smooth01((side*xi/rho+0.25)/0.65)
			if env < 1e-4 {
				continue
			}
			sum := 0.0
			for _, m := range modes {
				sum += m.w * math.Cos(m.k*(xi*m.ct+zeta*m.st))
			}
			v := env * sum
			rf.h[j*n+i] = v
			if a := math.Abs(v); a > peak {
				peak = a
			}
		}
	}
	if peak > 0 {
		f := amp / peak
		for i := range rf.h {
			rf.h[i] *= f
		}
	}
	// local-frame slopes by central differences
	for j := 1; j < n-1; j++ {
		for i := 1; i < n-1; i++ {
			rf.sxi[j*n+i] = (rf.h[j*n+i+1] - rf.h[j*n+i-1]) / (2 * rf.CellSize)
			rf.szeta[j*n+i] = (rf.h[(j+1)*n+i] - rf.h[(j-1)*n+i]) / (2 * rf.CellSize)
		}
	}
	return rf
}

func smooth01(t float64) float64 {
	if t <= 0 {
		return 0
	}
	if t >= 1 {
		return 1
	}
	return t * t * (3 - 2*t)
}

// Sample sums the pattern over all rock instances at world (x,y),
// returning height and world-frame slopes. Outside each local patch the
// contribution is exactly zero (clamped, not tiled — crescents don't
// repeat).
func (rf *RockField) Sample(x, y float64) (h, sx, sy float64) {
	if rf.h == nil {
		return
	}
	cx, cy := -rf.upy, rf.upx // across-flow unit vector
	for _, r := range rf.Rocks {
		dx, dy := x-r[0], y-r[1]
		xi := dx*rf.upx + dy*rf.upy
		zeta := dx*cx + dy*cy
		half := rf.Lp/2 - 2*rf.CellSize
		if xi < -half || xi > half || zeta < -half || zeta > half {
			continue
		}
		fi := (xi+rf.Lp/2)/rf.CellSize - 0.5
		fj := (zeta+rf.Lp/2)/rf.CellSize - 0.5
		i0, j0 := int(math.Floor(fi)), int(math.Floor(fj))
		tx, ty := fi-float64(i0), fj-float64(j0)
		n := rf.Np
		at := func(f []float64) float64 {
			a := f[j0*n+i0]*(1-tx) + f[j0*n+i0+1]*tx
			b := f[(j0+1)*n+i0]*(1-tx) + f[(j0+1)*n+i0+1]*tx
			return a*(1-ty) + b*ty
		}
		h += at(rf.h)
		gxi := at(rf.sxi)
		gzeta := at(rf.szeta)
		// rotate local gradient back to world axes
		sx += gxi*rf.upx + gzeta*cx
		sy += gxi*rf.upy + gzeta*cy
	}
	return
}
