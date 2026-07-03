package fft

import (
	"math"
	"math/cmplx"
	"math/rand"
	"testing"
)

// naive O(n²) DFT as the reference implementation.
func dft(a []complex128, inverse bool) []complex128 {
	n := len(a)
	out := make([]complex128, n)
	sign := -1.0
	if inverse {
		sign = 1.0
	}
	for k := 0; k < n; k++ {
		var s complex128
		for j := 0; j < n; j++ {
			ang := sign * 2 * math.Pi * float64(k*j) / float64(n)
			s += a[j] * cmplx.Exp(complex(0, ang))
		}
		if inverse {
			s /= complex(float64(n), 0)
		}
		out[k] = s
	}
	return out
}

func TestFFTMatchesDFT(t *testing.T) {
	rng := rand.New(rand.NewSource(7))
	for _, n := range []int{1, 2, 8, 64, 256} {
		a := make([]complex128, n)
		for i := range a {
			a[i] = complex(rng.NormFloat64(), rng.NormFloat64())
		}
		want := dft(a, false)
		got := append([]complex128(nil), a...)
		FFT(got, false)
		for i := range got {
			if cmplx.Abs(got[i]-want[i]) > 1e-9*float64(n) {
				t.Fatalf("n=%d: FFT[%d]=%v want %v", n, i, got[i], want[i])
			}
		}
	}
}

func TestRoundTripAndParseval(t *testing.T) {
	rng := rand.New(rand.NewSource(11))
	n := 128
	a := make([]complex128, n)
	var timeEnergy float64
	for i := range a {
		a[i] = complex(rng.NormFloat64(), rng.NormFloat64())
		timeEnergy += real(a[i])*real(a[i]) + imag(a[i])*imag(a[i])
	}
	f := append([]complex128(nil), a...)
	FFT(f, false)
	var freqEnergy float64
	for i := range f {
		freqEnergy += real(f[i])*real(f[i]) + imag(f[i])*imag(f[i])
	}
	// Parseval: Σ|x|² = (1/n) Σ|X|² for the unnormalized forward transform.
	if math.Abs(freqEnergy/float64(n)-timeEnergy) > 1e-9*timeEnergy {
		t.Fatalf("Parseval violated: %g vs %g", freqEnergy/float64(n), timeEnergy)
	}
	FFT(f, true)
	for i := range f {
		if cmplx.Abs(f[i]-a[i]) > 1e-12 {
			t.Fatalf("round trip failed at %d", i)
		}
	}
}

func TestFFT2DRoundTrip(t *testing.T) {
	rng := rand.New(rand.NewSource(13))
	n := 64
	a := make([]complex128, n*n)
	for i := range a {
		a[i] = complex(rng.NormFloat64(), rng.NormFloat64())
	}
	f := append([]complex128(nil), a...)
	FFT2D(f, n, false)
	FFT2D(f, n, true)
	for i := range f {
		if cmplx.Abs(f[i]-a[i]) > 1e-11 {
			t.Fatalf("2D round trip failed at %d", i)
		}
	}
}
