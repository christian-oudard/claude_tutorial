// Package wave implements the spectral surface layer of the spec (§3):
// Tessendorf-style synthesis on a periodic patch, with the full finite-
// depth capillary–gravity dispersion relation (§3.1), Doppler advection by
// the creek current (§3.2), choppy horizontal displacement, and spectral
// slopes for shading. The Hermitian pairing that keeps the surface real is
// exactly the identity certified in spec.TestTessendorfHermitianSymmetry;
// the ω₀ used here is pinned to the exact kernel through phys.
package wave

import (
	"math"
	"math/cmplx"

	"github.com/christian-oudard/claude_tutorial/creek/fft"
	"github.com/christian-oudard/claude_tutorial/creek/phys"
)

// Params configures the surface patch.
type Params struct {
	N      int     // grid resolution per side (power of two)
	L      float64 // physical patch size, m
	Depth  float64 // mean water depth, m (finite-depth dispersion)
	UDrive float64 // driving speed for the Phillips-type spectrum scale, m/s
	Ux, Uy float64 // advecting current for the Doppler term, m/s
	Cutoff float64 // small-scale spectral cutoff ℓ, m
	Chop   float64 // choppy displacement λ_c
	RMS    float64 // target surface-height rms, m (0: skip normalization)
	Seed   uint64

	// Multiscale cascade support (§7.2 one-way nesting, spectral form):
	// this band owns wavenumbers k ∈ [KLo, KHi); KHi = 0 means unbounded.
	// Bands with disjoint windows partition k-space, so summing them never
	// double-counts energy.
	KLo, KHi float64
	// CapAmp adds a capillary ripple bump centered at the certified
	// gravity–capillary crossover k_m = phys.KCross() (§3.1) with log-k
	// width ~1.1 — the "saturated capillary ripple range" of §5.2, with
	// its location pinned by the verified layer rather than tuned.
	CapAmp float64
	// Spread mixes the |k̂·ŵ|² directional factor toward isotropy
	// (0 = fully current-aligned, 1 = isotropic); fine turbulence-fed
	// ripples are less directional than the driven chop.
	Spread float64
}

// Surface is what the renderer consumes: a time-steppable heightfield
// with slopes and a sub-grid slope-variance tail (§6.4).
type Surface interface {
	Step(t float64)
	Sample(x, y float64) (h, sx, sy float64)
	SampleH(x, y float64) float64
	SlopeTail() float64
}

// Ocean holds the precomputed spectrum and per-frame output fields.
type Ocean struct {
	P Params

	h0, h0mc []complex128 // initial amplitudes and conj(h0(-k))
	omega0   []float64    // still-water dispersion ω₀(k)
	uk       []float64    // Doppler shift U·k
	kx, ky   []float64    // wave-vector components
	kmag     []float64

	// Real output fields, refreshed by Step.
	H, Sx, Sy, Dx, Dy []float64

	// SlopeVarTail is the slope variance carried by wavenumbers beyond the
	// grid Nyquist — the §6.4 rule: whatever the fluid layer does not
	// resolve, the shader must carry as roughness. Computed from the same
	// spectrum by radial quadrature at construction.
	SlopeVarTail float64

	// SlopeVarGrid is the resolved slope variance of this band, measured
	// from the synthesized fields — what a renderer must fold into
	// roughness when its pixel footprint outgrows this band's cells
	// (per-pixel LOD, §6.4 applied at the camera instead of the grid).
	SlopeVarGrid float64

	spec, ssx, ssy, sdx, sdy []complex128
}

// xorshift64* PRNG + Box–Muller: deterministic across runs and platforms.
type rng struct{ s uint64 }

func (r *rng) next() float64 {
	r.s ^= r.s >> 12
	r.s ^= r.s << 25
	r.s ^= r.s >> 27
	return float64(r.s*2685821657736338717>>11) / float64(1<<53)
}

func (r *rng) gauss() float64 {
	u1 := r.next()
	for u1 < 1e-300 {
		u1 = r.next()
	}
	u2 := r.next()
	return math.Sqrt(-2*math.Log(u1)) * math.Cos(2*math.Pi*u2)
}

// spectrum is the driving spectrum (§3.3): Phillips form with directional
// factor along the current, an optional capillary bump at the certified
// crossover k_m, a small-scale cutoff, and the band window [KLo, KHi).
func spectrum(kx, ky float64, p Params) float64 {
	k2 := kx*kx + ky*ky
	if k2 < 1e-12 {
		return 0
	}
	k := math.Sqrt(k2)
	if k < p.KLo || (p.KHi > 0 && k >= p.KHi) {
		return 0
	}
	// directional factor along the driving current (§3.3: current, not wind)
	ux, uy := p.Ux, p.Uy
	um := math.Hypot(ux, uy)
	if um < 1e-12 {
		ux, uy, um = 1, 0, 1
	}
	dir := (kx*ux + ky*uy) / (k * um)
	dirF := (1-p.Spread)*dir*dir + p.Spread*0.5
	return radialSpectrum(k, p) * dirF * 2.0
}

// radialSpectrum is the angle-averaged spectrum shape (angular mean of the
// directional factor is 1/2, folded in here so spectrum() and the slope
// tail integral share one definition).
func radialSpectrum(k float64, p Params) float64 {
	lp := p.UDrive * p.UDrive / phys.Grav
	base := math.Exp(-1/(k*k*lp*lp)) / (k * k * k * k)
	if p.CapAmp > 0 {
		l := math.Log(k / phys.KCross())
		base += p.CapAmp * math.Exp(-l*l/2.42) / (k * k * k * k)
	}
	return base * 0.5 * math.Exp(-k*k*p.Cutoff*p.Cutoff)
}

// NewOcean builds the spectrum, normalizes to the target rms height, and
// integrates the sub-grid slope-variance tail.
func NewOcean(p Params) *Ocean {
	n := p.N
	o := &Ocean{
		P:      p,
		h0:     make([]complex128, n*n),
		h0mc:   make([]complex128, n*n),
		omega0: make([]float64, n*n),
		uk:     make([]float64, n*n),
		kx:     make([]float64, n*n),
		ky:     make([]float64, n*n),
		kmag:   make([]float64, n*n),
		H:      make([]float64, n*n),
		Sx:     make([]float64, n*n),
		Sy:     make([]float64, n*n),
		Dx:     make([]float64, n*n),
		Dy:     make([]float64, n*n),
		spec:   make([]complex128, n*n),
		ssx:    make([]complex128, n*n),
		ssy:    make([]complex128, n*n),
		sdx:    make([]complex128, n*n),
		sdy:    make([]complex128, n*n),
	}

	r := &rng{s: p.Seed | 1}
	dk := 2 * math.Pi / p.L
	for j := 0; j < n; j++ {
		sj := j
		if sj > n/2 {
			sj -= n
		}
		for i := 0; i < n; i++ {
			si := i
			if si > n/2 {
				si -= n
			}
			idx := j*n + i
			kx, ky := dk*float64(si), dk*float64(sj)
			o.kx[idx], o.ky[idx] = kx, ky
			k := math.Hypot(kx, ky)
			o.kmag[idx] = k
			o.omega0[idx] = phys.Omega0(k, p.Depth)
			o.uk[idx] = p.Ux*kx + p.Uy*ky
			s := spectrum(kx, ky, p)
			// Nyquist rows/columns are their own -k partner on an even
			// grid, so the Doppler phase factor (not self-conjugate)
			// would break surface reality exactly there. The certified
			// Hermitian identity assumes distinct ±k pairs; enforce its
			// hypothesis by zeroing the self-paired band. (Found by the
			// ImagResidual runtime probe of that identity.)
			if si == n/2 || sj == n/2 {
				s = 0
			}
			// The dk factor makes bands with different patch sizes
			// mutually consistent: per-mode variance is S(k)·Δk², so a
			// cascade needs no per-band retuning.
			o.h0[idx] = complex(r.gauss(), r.gauss()) * complex(dk*math.Sqrt(s/2), 0)
		}
	}
	// conj(h0(-k)) lookup table; -k index is (n-i)%n, (n-j)%n.
	for j := 0; j < n; j++ {
		for i := 0; i < n; i++ {
			mi, mj := (n-i)%n, (n-j)%n
			o.h0mc[j*n+i] = cmplx.Conj(o.h0[mj*n+mi])
		}
	}

	// Normalize to target rms via one trial synthesis.
	o.Step(0)
	var sum float64
	for _, h := range o.H {
		sum += h * h
	}
	rms := math.Sqrt(sum / float64(len(o.H)))
	if rms > 0 && p.RMS > 0 {
		scale := complex(p.RMS/rms, 0)
		for i := range o.h0 {
			o.h0[i] *= scale
			o.h0mc[i] *= scale
		}
	}

	o.Step(0)
	o.SlopeVarTail = o.tailSlopeVariance()
	o.SlopeVarGrid = o.gridSlopeVariance()
	return o
}

func (o *Ocean) gridSlopeVariance() float64 {
	var v float64
	for i := range o.Sx {
		v += o.Sx[i]*o.Sx[i] + o.Sy[i]*o.Sy[i]
	}
	return v / float64(len(o.Sx))
}

// tailSlopeVariance implements the §6.4 rule s² = ∫_{k>k_res} k² S(k) d²k:
// the slope variance the grid cannot resolve, which the renderer must
// carry as microfacet roughness. Computed as (resolved slope variance
// measured from the synthesized fields) × (tail/resolved ratio of the
// radially integrated spectrum) — the spectrum normalization cancels in
// the ratio.
func (o *Ocean) tailSlopeVariance() float64 {
	kNyq := math.Pi * float64(o.P.N) / o.P.L
	dk := 2 * math.Pi / o.P.L

	// A band whose window closes below the grid Nyquist is fully resolved;
	// its unresolved tail belongs to the finer bands of the cascade.
	if o.P.KHi > 0 && o.P.KHi <= kNyq {
		return 0
	}

	radial := func(k float64) float64 { // k²·S̄(k)·2πk integrand
		return k * k * radialSpectrum(k, o.P) * 2 * math.Pi * k
	}
	var resolved, tail float64
	for k := math.Max(dk, o.P.KLo); k < kNyq; k += dk / 4 {
		resolved += radial(k) * dk / 4
	}
	kEnd := 20 * kNyq
	if o.P.KHi > 0 && o.P.KHi < kEnd {
		kEnd = o.P.KHi // the band owns nothing beyond its window
	}
	for k := kNyq; k < kEnd; k += kNyq / 64 {
		tail += radial(k) * kNyq / 64
	}
	if resolved == 0 {
		return 0
	}

	var gridSlopeVar float64
	for i := range o.Sx {
		gridSlopeVar += o.Sx[i]*o.Sx[i] + o.Sy[i]*o.Sy[i]
	}
	gridSlopeVar /= float64(len(o.Sx))
	return gridSlopeVar * tail / resolved
}

// Step synthesizes the surface at time t: height, slopes and choppy
// displacement, via five inverse FFTs.
func (o *Ocean) Step(t float64) {
	n := o.P.N
	for i := range o.spec {
		// Hermitian pair (certified in spec): h0 e^{iω₀t} + conj(h0(-k)) e^{-iω₀t},
		// then the Doppler advection factor e^{-i(U·k)t} (§3.2) — which
		// preserves reality because U·(-k) = -U·k.
		e := cmplx.Exp(complex(0, o.omega0[i]*t))
		hk := o.h0[i]*e + o.h0mc[i]*cmplx.Conj(e)
		hk *= cmplx.Exp(complex(0, -o.uk[i]*t))
		o.spec[i] = hk

		ikx := complex(0, o.kx[i])
		iky := complex(0, o.ky[i])
		o.ssx[i] = ikx * hk
		o.ssy[i] = iky * hk

		// Choppy displacement -i k/|k| h̃ (§3.3). The DC mode k=0 is the
		// 0/0 the real-number spec never mentions; the guard below is the
		// float-world patch for it (see spec float tests).
		if o.kmag[i] > 1e-12 {
			o.sdx[i] = complex(0, -o.kx[i]/o.kmag[i]) * hk * complex(o.P.Chop, 0)
			o.sdy[i] = complex(0, -o.ky[i]/o.kmag[i]) * hk * complex(o.P.Chop, 0)
		} else {
			o.sdx[i], o.sdy[i] = 0, 0
		}
	}
	fft.FFT2D(o.spec, n, true)
	fft.FFT2D(o.ssx, n, true)
	fft.FFT2D(o.ssy, n, true)
	fft.FFT2D(o.sdx, n, true)
	fft.FFT2D(o.sdy, n, true)

	// The inverse FFT carries 1/n²; undo it so amplitudes are physical
	// (the spectrum is defined per-mode, not per-cell).
	scale := float64(n) * float64(n)
	for i := range o.H {
		o.H[i] = real(o.spec[i]) * scale
		o.Sx[i] = real(o.ssx[i]) * scale
		o.Sy[i] = real(o.ssy[i]) * scale
		o.Dx[i] = real(o.sdx[i]) * scale
		o.Dy[i] = real(o.sdy[i]) * scale
	}
}

// ImagResidual returns the largest |imaginary part| left in the height
// field — a direct runtime probe of the Hermitian-symmetry identity.
func (o *Ocean) ImagResidual() float64 {
	worst := 0.0
	for _, c := range o.spec {
		if v := math.Abs(imag(c)); v > worst {
			worst = v
		}
	}
	return worst * float64(o.P.N) * float64(o.P.N)
}

func (o *Ocean) bilinear(f []float64, x, y float64) float64 {
	n := o.P.N
	s := float64(n) / o.P.L
	fx, fy := x*s, y*s
	ix, iy := math.Floor(fx), math.Floor(fy)
	tx, ty := fx-ix, fy-iy
	i0 := ((int(ix) % n) + n) % n
	j0 := ((int(iy) % n) + n) % n
	i1, j1 := (i0+1)%n, (j0+1)%n
	a := f[j0*n+i0]*(1-tx) + f[j0*n+i1]*tx
	b := f[j1*n+i0]*(1-tx) + f[j1*n+i1]*tx
	return a*(1-ty) + b*ty
}

// Sample returns height and slopes at world position (x,y), applying one
// fixed-point iteration of the choppy displacement inverse.
func (o *Ocean) Sample(x, y float64) (h, sx, sy float64) {
	dx := o.bilinear(o.Dx, x, y)
	dy := o.bilinear(o.Dy, x, y)
	ux, uy := x-dx, y-dy
	return o.bilinear(o.H, ux, uy), o.bilinear(o.Sx, ux, uy), o.bilinear(o.Sy, ux, uy)
}

// SampleH returns only the height at world position (x,y) — the cheap
// path for ray marching (slopes are fetched once, at the hit point).
func (o *Ocean) SampleH(x, y float64) float64 {
	dx := o.bilinear(o.Dx, x, y)
	dy := o.bilinear(o.Dy, x, y)
	return o.bilinear(o.H, x-dx, y-dy)
}

// SlopeTail implements Surface.
func (o *Ocean) SlopeTail() float64 { return o.SlopeVarTail }

// ScaleAmp rescales the spectrum amplitude in place (used by Cascade for
// global normalization); call Step afterwards to refresh the fields.
func (o *Ocean) ScaleAmp(f float64) {
	c := complex(f, 0)
	for i := range o.h0 {
		o.h0[i] *= c
		o.h0mc[i] *= c
	}
	o.SlopeVarTail *= f * f
	o.SlopeVarGrid *= f * f
}

// MaxAmp returns the current maximum |height| (used by the ray-marcher).
func (o *Ocean) MaxAmp() float64 {
	m := 0.0
	for _, h := range o.H {
		if a := math.Abs(h); a > m {
			m = a
		}
	}
	return m
}
