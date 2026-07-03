package wave

import "math"

// Cascade is the multiscale surface (§7.2, spectral form): several Ocean
// bands at different patch sizes whose k-windows partition wavenumber
// space. Summing them yields centimeter chop carrying millimeter ripples
// in the same wave — each band evolving under the same certified
// capillary–gravity dispersion relation, just sampled where its grid can
// afford to resolve it.
//
// The dk factor in each band's mode amplitudes makes the bands mutually
// consistent samples of ONE continuous spectrum, so a single global
// normalization sets the overall height scale without distorting the
// energy balance between scales.
type Cascade struct {
	Bands []*Ocean

	// Rocks optionally adds the §3.2 rock-locked stationary patterns
	// (gravity wake + capillary crescents) — the coherent, non-Gaussian
	// structure a spectral sea cannot carry.
	Rocks []*RockField
}

// NewCascade builds the bands (each with per-band normalization disabled)
// and rescales them together to the target total rms height. Bands are
// assumed spectrally disjoint (enforced by their windows) and seeded
// independently, so variances add.
func NewCascade(ps []Params, totalRMS float64) *Cascade {
	c := &Cascade{}
	var totalVar float64
	for _, p := range ps {
		p.RMS = 0 // global normalization below
		b := NewOcean(p)
		var sq float64
		for _, h := range b.H {
			sq += h * h
		}
		totalVar += sq / float64(len(b.H))
		c.Bands = append(c.Bands, b)
	}
	if totalVar > 0 && totalRMS > 0 {
		f := totalRMS / math.Sqrt(totalVar)
		for _, b := range c.Bands {
			b.ScaleAmp(f)
			b.Step(0)
		}
	}
	return c
}

// Step advances every band to time t.
func (c *Cascade) Step(t float64) {
	for _, b := range c.Bands {
		b.Step(t)
	}
}

// Sample sums height and slopes across bands (plus rock crescents).
func (c *Cascade) Sample(x, y float64) (h, sx, sy float64) {
	for _, b := range c.Bands {
		bh, bsx, bsy := b.Sample(x, y)
		h += bh
		sx += bsx
		sy += bsy
	}
	for _, rf := range c.Rocks {
		rh, rsx, rsy := rf.Sample(x, y)
		h += rh
		sx += rsx
		sy += rsy
	}
	return
}

// SampleH sums heights only (ray-march fast path).
func (c *Cascade) SampleH(x, y float64) float64 {
	h := 0.0
	for _, b := range c.Bands {
		h += b.SampleH(x, y)
	}
	for _, rf := range c.Rocks {
		rh, _, _ := rf.Sample(x, y)
		h += rh
	}
	return h
}

// SlopeTail returns the unresolved slope variance of the cascade — the
// sum over bands, which in a well-formed cascade is carried entirely by
// the finest band (coarser bands' tails are owned by finer bands and
// report zero).
func (c *Cascade) SlopeTail() float64 {
	s := 0.0
	for _, b := range c.Bands {
		s += b.SlopeVarTail
	}
	return s
}

// SampleLOD samples the surface for a pixel whose ground footprint is
// the given size (m): bands whose cells the pixel can no longer resolve
// are faded out of the geometric normal and their slope variance is
// returned as unresolved roughness instead. This moves the §6.4
// grid-cutoff rule to where it belongs — the camera: the boundary
// between "geometry" and "microfacet statistics" tracks the pixel, so
// near water shows resolved millimeter ripples while far water carries
// the identical energy as Cox–Munk-style gloss, with no aliasing band
// in between.
func (c *Cascade) SampleLOD(x, y, footprint float64) (h, sx, sy, unresolved float64) {
	for _, b := range c.Bands {
		cell := b.P.L / float64(b.P.N)
		// fade over footprint ∈ [2·cell, 4·cell] (Nyquist to comfortably lost)
		w := (footprint - 2*cell) / (2 * cell)
		if w < 0 {
			w = 0
		}
		if w >= 1 {
			unresolved += b.SlopeVarGrid
			continue
		}
		bh, bsx, bsy := b.Sample(x, y)
		g := 1 - w
		h += bh * g
		sx += bsx * g
		sy += bsy * g
		// slope variance removed from the geometric normal is w(2-w)·var
		// (since amplitudes scale by 1-w); conserve it as roughness.
		unresolved += b.SlopeVarGrid * w * (2 - w)
	}
	for _, rf := range c.Rocks {
		cell := rf.CellSize
		w := (footprint - 2*cell) / (2 * cell)
		if w < 0 {
			w = 0
		}
		if w < 1 {
			rh, rsx, rsy := rf.Sample(x, y)
			g := 1 - w
			h += rh * g
			sx += rsx * g
			sy += rsy * g
		}
	}
	unresolved += c.SlopeTail()
	return
}

// MaxAmp bounds the summed surface height.
func (c *Cascade) MaxAmp() float64 {
	m := 0.0
	for _, b := range c.Bands {
		m += b.MaxAmp()
	}
	return m
}
