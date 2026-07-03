package render

import "math"

// Deterministic hash-based value noise for the creek bed. Not physics —
// texture only.

func hash2(ix, iy int64) float64 {
	h := uint64(ix)*0x9E3779B97F4A7C15 ^ uint64(iy)*0xC2B2AE3D27D4EB4F
	h ^= h >> 29
	h *= 0xBF58476D1CE4E5B9
	h ^= h >> 32
	return float64(h&0xFFFFFFFF) / float64(0xFFFFFFFF)
}

func valueNoise(x, y float64) float64 {
	ix, iy := math.Floor(x), math.Floor(y)
	tx, ty := x-ix, y-iy
	sx := tx * tx * (3 - 2*tx)
	sy := ty * ty * (3 - 2*ty)
	i, j := int64(ix), int64(iy)
	a := hash2(i, j)
	b := hash2(i+1, j)
	c := hash2(i, j+1)
	d := hash2(i+1, j+1)
	return lerp(lerp(a, b, sx), lerp(c, d, sx), sy)
}

func fbm(x, y float64, octaves int) float64 {
	sum, amp, freq, norm := 0.0, 1.0, 1.0, 0.0
	for o := 0; o < octaves; o++ {
		sum += amp * valueNoise(x*freq, y*freq)
		norm += amp
		amp *= 0.5
		freq *= 2.03
	}
	return sum / norm
}
