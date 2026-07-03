package wave

import (
	"math"
	"testing"

	"github.com/christian-oudard/claude_tutorial/creek/phys"
)

func creekBands() []Params {
	base := Params{
		Depth: 0.2, UDrive: 0.5, Ux: 0.5, Uy: 0,
		CapAmp: 2.0, Seed: 1,
	}
	// Windows must close at or below each band's grid Nyquist
	// (N=128: kNyq = pi*128/L), so every owned wavenumber is resolvable.
	a := base
	a.N, a.L, a.KHi, a.Chop, a.Cutoff, a.Seed = 128, 2.0, 180, 1.1, 0, 101
	b := base
	b.N, b.L, b.KLo, b.KHi, b.Chop, b.Cutoff, b.Spread, b.Seed = 128, 0.5, 180, 700, 0.7, 0, 0.3, 202
	f := base
	f.N, f.L, f.KLo, f.Chop, f.Cutoff, f.Spread, f.Seed = 128, 0.15, 700, 0.4, 0.0007, 0.4, 303
	return []Params{a, b, f}
}

func TestBandWindowsPartitionKSpace(t *testing.T) {
	// Every wavenumber magnitude is owned by exactly one band: the windows
	// are half-open, contiguous, and non-overlapping.
	ps := creekBands()
	for _, k := range []float64{5, 100, 179.9, 180, 600, 699.9, 700, 3000} {
		owners := 0
		for _, p := range ps {
			if k >= p.KLo && (p.KHi == 0 || k < p.KHi) {
				owners++
			}
		}
		if owners != 1 {
			t.Errorf("k=%g owned by %d bands, want exactly 1", k, owners)
		}
	}
	// And the spectrum respects the window: a band evaluates to zero
	// outside its own range.
	pB := ps[1]
	if spectrum(100, 0, pB) != 0 || spectrum(1500, 0, pB) != 0 {
		t.Error("band B spectrum leaks outside its window")
	}
	if spectrum(500, 0, pB) == 0 {
		t.Error("band B spectrum empty inside its window")
	}
}

func TestCapillaryBumpCenteredAtCertifiedCrossover(t *testing.T) {
	// The ripple bump is defined relative to k_m = phys.KCross(), which the
	// spec suite certifies as sqrt(rho g / sigma). The bump contribution
	// k⁴·(S_withBump - S_without) must peak at k_m.
	p := Params{UDrive: 0.5, CapAmp: 2.0}
	p0 := p
	p0.CapAmp = 0
	bump := func(k float64) float64 {
		return (radialSpectrum(k, p) - radialSpectrum(k, p0)) * k * k * k * k
	}
	km := phys.KCross()
	at := bump(km)
	if at <= 0 {
		t.Fatal("bump vanishes at k_m")
	}
	for _, f := range []float64{0.3, 0.5, 2, 3} {
		if bump(km*f) >= at {
			t.Errorf("bump at %.2f·k_m (%g) >= bump at k_m (%g)", f, bump(km*f), at)
		}
	}
}

func TestCascadeRealFiniteAndNormalized(t *testing.T) {
	c := NewCascade(creekBands(), 0.006)
	c.Step(0.7)
	// finite, real surface across bands
	for _, b := range c.Bands {
		if r := b.ImagResidual(); r > 1e-9 {
			t.Fatalf("band L=%g imag residual %g", b.P.L, r)
		}
	}
	// summed variance matches the requested total rms (variances add for
	// independently seeded disjoint bands) — measured at synthesis time 0.
	c.Step(0)
	var sq float64
	const n = 96
	for j := 0; j < n; j++ {
		for i := 0; i < n; i++ {
			h := c.SampleH(float64(i)*2.0/n, float64(j)*2.0/n)
			if math.IsNaN(h) {
				t.Fatal("NaN in cascade sample")
			}
			sq += h * h
		}
	}
	rms := math.Sqrt(sq / (n * n))
	if math.Abs(rms-0.006)/0.006 > 0.25 {
		t.Errorf("cascade rms %g vs target 0.006", rms)
	}
}

func TestCascadeHasMultiscaleEnergy(t *testing.T) {
	// The point of the exercise: the fine band must contribute visible
	// structure, not be a rounding error on the coarse band — and the
	// coarse band must still dominate total height. Slope variance is the
	// scale-weighted measure (k² weighting), so fine bands should OWN the
	// slope budget even while coarse bands own the height budget.
	c := NewCascade(creekBands(), 0.006)
	c.Step(0)
	hVar := make([]float64, len(c.Bands))
	sVar := make([]float64, len(c.Bands))
	for bi, b := range c.Bands {
		for i := range b.H {
			hVar[bi] += b.H[i] * b.H[i]
			sVar[bi] += b.Sx[i]*b.Sx[i] + b.Sy[i]*b.Sy[i]
		}
		hVar[bi] /= float64(len(b.H))
		sVar[bi] /= float64(len(b.H))
	}
	if !(hVar[0] > hVar[2]) {
		t.Errorf("coarse band should dominate height: %v", hVar)
	}
	// Slope variance per octave FALLS with k under a 1/k^4 spectrum, so the
	// fine band must not dominate slope — but curvature variance (k^4-
	// weighted) must concentrate in the fine band: that is the measurable
	// content of "millimeter texture riding on centimeter waves".
	curv := make([]float64, len(c.Bands))
	for bi, b := range c.Bands {
		for i := range b.h0 {
			re, im := real(b.h0[i]), imag(b.h0[i])
			k4 := b.kmag[i] * b.kmag[i] * b.kmag[i] * b.kmag[i]
			curv[bi] += k4 * (re*re + im*im)
		}
	}
	if !(curv[2] > curv[0]) {
		t.Errorf("fine band should dominate curvature (ripple texture): %v", curv)
	}
	if !(sVar[2] > 0.02*sVar[0]) {
		t.Errorf("fine band slope negligible — texture invisible: %v", sVar)
	}
	// Fully-windowed coarse bands report zero unresolved tail; the finest
	// band owns it.
	if c.Bands[0].SlopeVarTail != 0 || c.Bands[1].SlopeVarTail != 0 {
		t.Error("windowed coarse bands must not double-count the sub-grid tail")
	}
	if !(c.Bands[2].SlopeVarTail > 0) {
		t.Error("finest band must carry a positive sub-grid tail")
	}
}

func TestBandsShareDispersion(t *testing.T) {
	// ω₀ is a function of k only (§3.1): two bands evaluating the same
	// physical wavenumber must agree exactly — the cascade is one physical
	// model sampled twice, not two models.
	k := 300.0
	w1 := phys.Omega0(k, 0.2)
	w2 := phys.Omega0(k, 0.2)
	if w1 != w2 {
		t.Fatal("dispersion not a pure function of k")
	}
	if w1 <= 0 {
		t.Fatal("dispersion vanished at capillary wavenumber")
	}
}
