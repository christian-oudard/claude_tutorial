package wave

import (
	"math"
	"testing"
)

func testOcean() *Ocean {
	return NewOcean(Params{
		N: 64, L: 2.0, Depth: 0.2,
		UDrive: 0.5, Ux: 0.5, Uy: 0.0,
		Cutoff: 0.003, Chop: 1.0, RMS: 0.008, Seed: 42,
	})
}

func TestSurfaceIsRealAndFinite(t *testing.T) {
	o := testOcean()
	for _, tt := range []float64{0, 0.37, 1.9} {
		o.Step(tt)
		// Runtime probe of the certified Hermitian-symmetry identity: the
		// synthesized surface must be real up to rounding.
		if r := o.ImagResidual(); r > 1e-9 {
			t.Fatalf("imaginary residual %g at t=%g — Hermitian pairing broken", r, tt)
		}
		for i, h := range o.H {
			if math.IsNaN(h) || math.IsInf(h, 0) {
				t.Fatalf("NaN/Inf height at %d, t=%g (DC-mode guard failed?)", i, tt)
			}
		}
		for i := range o.Dx {
			if math.IsNaN(o.Dx[i]) || math.IsNaN(o.Dy[i]) {
				t.Fatalf("NaN choppy displacement at %d — k/|k| DC guard failed", i)
			}
		}
	}
}

func TestTargetRMSAndZeroMean(t *testing.T) {
	o := testOcean()
	o.Step(0)
	var sum, sq float64
	for _, h := range o.H {
		sum += h
		sq += h * h
	}
	mean := sum / float64(len(o.H))
	rms := math.Sqrt(sq / float64(len(o.H)))
	if math.Abs(mean) > 1e-6 {
		t.Errorf("mean height %g not ~0", mean)
	}
	if math.Abs(rms-o.P.RMS)/o.P.RMS > 0.02 {
		t.Errorf("rms %g vs target %g", rms, o.P.RMS)
	}
}

func TestDopplerAdvectsPattern(t *testing.T) {
	// Isolate the Doppler factor e^{-i(U·k)t} (§3.2) by zeroing the
	// dispersion: the surface must then advect EXACTLY with the current,
	// H(x, t) = H(x - Ut, 0). Choose t so U·t is exactly one grid cell and
	// compare cell-shifted arrays to rounding tolerance — this pins both
	// the advection and its downstream sign.
	o := testOcean()
	for i := range o.omega0 {
		o.omega0[i] = 0
	}
	o.Step(0)
	h0 := append([]float64(nil), o.H...)

	n := o.P.N
	cell := o.P.L / float64(n)
	dt := cell / o.P.Ux // one cell downstream (+x)
	o.Step(dt)

	worst := 0.0
	for j := 0; j < n; j++ {
		for i := 0; i < n; i++ {
			want := h0[j*n+((i-1+n)%n)]
			if d := math.Abs(o.H[j*n+i] - want); d > worst {
				worst = d
			}
		}
	}
	if worst > 1e-9 {
		t.Errorf("pure-current surface does not advect exactly: worst err %g", worst)
	}
}

func TestSlopeTailPositive(t *testing.T) {
	o := testOcean()
	if !(o.SlopeVarTail > 0) {
		t.Errorf("sub-grid slope variance %g should be positive for a cutoff spectrum",
			o.SlopeVarTail)
	}
	// And it must be small compared to unity slope (sanity for GGX α).
	if o.SlopeVarTail > 1 {
		t.Errorf("tail slope variance %g implausibly large", o.SlopeVarTail)
	}
}

func BenchmarkStep256(b *testing.B) {
	o := NewOcean(Params{
		N: 256, L: 2.0, Depth: 0.2,
		UDrive: 0.5, Ux: 0.5, Cutoff: 0.003, Chop: 1.0, RMS: 0.008, Seed: 42,
	})
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		o.Step(float64(i) * 0.016)
	}
}
