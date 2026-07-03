// Package fft implements an in-place radix-2 Cooley–Tukey FFT and a
// goroutine-parallel 2D transform. Pure Go, zero allocations per call in
// the 1D path — the hot loop of the spectral surface (§3.3).
package fft

import (
	"math"
	"math/bits"
	"runtime"
	"sync"
)

// FFT performs an in-place transform of a; len(a) must be a power of two.
// inverse applies the conjugate transform and 1/n normalization, so
// FFT(FFT(a, false), true) is the identity up to rounding.
func FFT(a []complex128, inverse bool) {
	n := len(a)
	if n == 0 || n&(n-1) != 0 {
		panic("fft: length must be a power of two")
	}
	logn := bits.TrailingZeros(uint(n))
	// bit-reversal permutation
	shift := 64 - uint(logn)
	for i := 1; i < n; i++ {
		j := int(bits.Reverse64(uint64(i)) >> shift)
		if j > i {
			a[i], a[j] = a[j], a[i]
		}
	}
	for size := 2; size <= n; size <<= 1 {
		ang := 2 * math.Pi / float64(size)
		if !inverse {
			ang = -ang
		}
		wstep := complex(math.Cos(ang), math.Sin(ang))
		half := size / 2
		for start := 0; start < n; start += size {
			w := complex(1, 0)
			for k := 0; k < half; k++ {
				u := a[start+k]
				v := a[start+k+half] * w
				a[start+k] = u + v
				a[start+k+half] = u - v
				w *= wstep
			}
		}
	}
	if inverse {
		inv := complex(1/float64(n), 0)
		for i := range a {
			a[i] *= inv
		}
	}
}

// FFT2D transforms an n×n row-major grid in place, parallelizing rows and
// columns across GOMAXPROCS workers.
func FFT2D(a []complex128, n int, inverse bool) {
	if len(a) != n*n {
		panic("fft: grid size mismatch")
	}
	workers := runtime.GOMAXPROCS(0)
	if workers > n {
		workers = n
	}

	var wg sync.WaitGroup
	rows := make(chan int, n)
	for w := 0; w < workers; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for r := range rows {
				FFT(a[r*n:(r+1)*n], inverse)
			}
		}()
	}
	for r := 0; r < n; r++ {
		rows <- r
	}
	close(rows)
	wg.Wait()

	cols := make(chan int, n)
	wg = sync.WaitGroup{}
	for w := 0; w < workers; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			buf := make([]complex128, n)
			for c := range cols {
				for r := 0; r < n; r++ {
					buf[r] = a[r*n+c]
				}
				FFT(buf, inverse)
				for r := 0; r < n; r++ {
					a[r*n+c] = buf[r]
				}
			}
		}()
	}
	for c := 0; c < n; c++ {
		cols <- c
	}
	close(cols)
	wg.Wait()
}
