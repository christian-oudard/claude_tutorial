// Package render draws the creek surface (§6): ray-marched heightfield,
// exact-Fresnel-pinned Schlick reflectance, GGX sun glints whose roughness
// comes from the sub-grid slope variance of the wave spectrum (the §6.4
// rule: what the fluid layer does not resolve, the shader carries), and
// Beer–Lambert attenuation of the refracted bed signal (§6.3).
//
// CPU-only, goroutine-parallel scanlines. This is the reference
// implementation of the shading math; a GPU port is a transcription of
// Shade, not a redesign.
package render

import (
	"image"
	"image/color"
	"math"
	"runtime"
	"sync"

	"github.com/christian-oudard/claude_tutorial/creek/phys"
	"github.com/christian-oudard/claude_tutorial/creek/wave"
)

// Camera is a simple perspective pinhole.
type Camera struct {
	Pos     Vec3
	Forward Vec3
	Right   Vec3
	Up      Vec3
	TanHalf float64 // tan of half the horizontal FOV
}

// LookAt builds a camera at pos looking toward target with the given
// horizontal FOV in degrees.
func LookAt(pos, target Vec3, fovDeg float64) Camera {
	f := target.Sub(pos).Norm()
	r := Vec3{f.Y, -f.X, 0}.Norm() // world-up = +z
	u := r.Cross(f)
	return Camera{Pos: pos, Forward: f, Right: r, Up: u,
		TanHalf: math.Tan(fovDeg * math.Pi / 360)}
}

// Cross is the 3D cross product.
func (a Vec3) Cross(b Vec3) Vec3 {
	return Vec3{a.Y*b.Z - a.Z*b.Y, a.Z*b.X - a.X*b.Z, a.X*b.Y - a.Y*b.X}
}

// Scene bundles everything the shader needs.
type Scene struct {
	Ocean  *wave.Ocean
	Cam    Camera
	SunDir Vec3 // toward the sun, unit
	// AlphaG is the GGX roughness: sqrt(2 · sub-grid slope variance),
	// floored for numerical stability. Set by NewScene from the ocean's
	// spectral tail (§6.4).
	AlphaG float64
	// Attenuation c_lambda = a+b per RGB channel, 1/m (§6.3: clear
	// mountain water, red absorbed fastest).
	Atten Vec3
	Depth float64 // mean bed depth below z=0, m
}

// NewScene wires the §6.4 spectral-cutoff → roughness rule.
func NewScene(o *wave.Ocean, cam Camera, sun Vec3) *Scene {
	alpha := math.Sqrt(2 * o.SlopeVarTail)
	if alpha < 0.02 {
		alpha = 0.02
	}
	return &Scene{
		Ocean:  o,
		Cam:    cam,
		SunDir: sun.Norm(),
		AlphaG: alpha,
		Atten:  Vec3{0.45, 0.14, 0.08},
		Depth:  o.P.Depth,
	}
}

const sunRadiance = 1200.0

// sky returns radiance from direction d: a clear-sky gradient plus the
// 0.53° solar disk (§6.4) with a soft edge and mild circumsolar halo.
func (s *Scene) sky(d Vec3) Vec3 {
	t := clamp01(d.Z)
	base := lerpV(Vec3{0.92, 0.88, 0.78}, Vec3{0.30, 0.50, 0.82}, math.Pow(t, 0.45))
	cosSun := clamp01(d.Dot(s.SunDir))
	ang := math.Acos(cosSun)
	const sunHalf = 0.00465 // radians, 0.53°/2
	disk := smoothstep(sunHalf*1.8, sunHalf*0.7, ang)
	halo := 0.10 * math.Exp(-(ang/0.09)*(ang/0.09))
	return base.Add(Vec3{1, 0.96, 0.88}.Scale(sunRadiance*disk + halo*40))
}

// bedZ returns bed elevation below the surface: mean depth plus cobbles.
func (s *Scene) bedZ(x, y float64) float64 {
	stones := 0.05*fbm(x*6, y*6, 4) + 0.02*fbm(x*23, y*19, 3)
	return -s.Depth + stones
}

// bedAlbedo is procedural cobble coloring.
func (s *Scene) bedAlbedo(x, y float64) Vec3 {
	n := fbm(x*6, y*6, 4)
	m := fbm(x*29+7, y*31+3, 3)
	warm := Vec3{0.38, 0.30, 0.22}
	grey := Vec3{0.30, 0.30, 0.29}
	dark := Vec3{0.16, 0.15, 0.13}
	c := lerpV(grey, warm, smoothstep(0.35, 0.7, n))
	c = lerpV(c, dark, smoothstep(0.55, 0.85, m)*0.6)
	return c
}

// ggxD is the §6.4 microfacet NDF; its m=n value 1/(πα²) is certified in
// the spec suite.
func ggxD(cosNM, alpha float64) float64 {
	if cosNM <= 0 {
		return 0
	}
	a2 := alpha * alpha
	d := cosNM*cosNM*(a2-1) + 1
	return a2 / (math.Pi * d * d)
}

// Shade returns the radiance along the primary ray for pixel direction d.
func (s *Scene) Shade(d Vec3) Vec3 {
	// Rays that never come down see sky.
	if d.Z >= -0.005 {
		return s.sky(d)
	}
	hit, p := s.march(d)
	if !hit {
		return s.sky(d)
	}

	_, sx, sy := s.Ocean.Sample(p.X, p.Y)
	n := Vec3{-sx, -sy, 1}.Norm()
	v := d.Scale(-1)
	cosI := clamp01(n.Dot(v))

	// Fresnel split. SchlickR is pinned against exact Fresnel in the spec
	// suite (max abs deviation ≈ 0.059, measured).
	F := phys.SchlickR(cosI)

	// Reflected sky (the "silver" term: R(θ) rising past ~60°, §6.2).
	refl := Reflect(d, n)
	if refl.Z < 0.02 {
		refl.Z = 0.02 // grazing reflections skim the horizon, not the bed
		refl = refl.Norm()
	}
	lr := s.sky(refl)

	// GGX sun glint from unresolved micro-ripples (§6.4): roughness is the
	// spectral tail the wave grid cannot carry.
	h := v.Add(s.SunDir).Norm()
	spec := sunRadiance * phys.SunSolidAngle() *
		phys.SchlickR(clamp01(h.Dot(s.SunDir))) *
		ggxD(n.Dot(h), s.AlphaG) / (4 * math.Max(0.05, cosI))

	// Refracted bed signal with Beer–Lambert attenuation (§6.3).
	var lt Vec3
	if td, ok := Refract(d, n, phys.NAir/phys.NWater); ok {
		bz := s.bedZ(p.X, p.Y)
		pathLen := (p.Z - bz) / math.Max(0.05, -td.Z)
		bx := p.X + td.X*pathLen
		by := p.Y + td.Y*pathLen
		alb := s.bedAlbedo(bx, by)
		trans := Vec3{
			math.Exp(-s.Atten.X * pathLen),
			math.Exp(-s.Atten.Y * pathLen),
			math.Exp(-s.Atten.Z * pathLen),
		}
		// Downwelling sky light on the bed, diffusely reflected, attenuated
		// on the way down and back up (double path, folded into one exp).
		lt = alb.MulV(trans).Scale(1.15)
	}

	c := lr.Scale(F).Add(lt.Scale(1 - F))
	return c.Add(Vec3{1, 0.97, 0.9}.Scale(spec))
}

// march finds the first surface crossing along ray d from the camera.
func (s *Scene) march(d Vec3) (bool, Vec3) {
	maxAmp := 0.05
	o := s.Cam.Pos

	// Fast-forward to just above the wave band.
	t := 0.0
	if o.Z > maxAmp {
		t = (o.Z - maxAmp) / -d.Z * 0.98
	}
	const tMax = 60.0
	prev := t
	prevS := o.Add(d.Scale(t)).Z - s.heightAt(o.Add(d.Scale(t)))
	for t < tMax {
		dt := 0.004 + t*0.01
		t += dt
		p := o.Add(d.Scale(t))
		sv := p.Z - s.heightAt(p)
		if sv < 0 {
			// bisect [prev, t]
			lo, hi := prev, t
			for i := 0; i < 18; i++ {
				mid := (lo + hi) / 2
				pm := o.Add(d.Scale(mid))
				if pm.Z-s.heightAt(pm) < 0 {
					hi = mid
				} else {
					lo = mid
				}
			}
			return true, o.Add(d.Scale((lo + hi) / 2))
		}
		prev, prevS = t, sv
		_ = prevS
	}
	return false, Vec3{}
}

func (s *Scene) heightAt(p Vec3) float64 {
	h, _, _ := s.Ocean.Sample(p.X, p.Y)
	return h
}

// Render draws a w×h frame with ss×ss supersampling per pixel, parallel
// across scanlines. Supersampling is the cheap stand-in for the §6.4
// slope-PDF integral over the pixel footprint; a production renderer
// would fold the pixel-scale spectrum band into AlphaG instead.
func (s *Scene) Render(w, h, ss int) *image.RGBA {
	if ss < 1 {
		ss = 1
	}
	img := image.NewRGBA(image.Rect(0, 0, w, h))
	aspect := float64(h) / float64(w)
	workers := runtime.GOMAXPROCS(0)
	rows := make(chan int, h)
	var wg sync.WaitGroup
	inv := 1 / float64(ss)
	for wk := 0; wk < workers; wk++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for y := range rows {
				for x := 0; x < w; x++ {
					var acc Vec3
					for sy := 0; sy < ss; sy++ {
						for sx := 0; sx < ss; sx++ {
							px := float64(x) + (float64(sx)+0.5)*inv
							py := float64(y) + (float64(sy)+0.5)*inv
							u := (2*px/float64(w) - 1) * s.Cam.TanHalf
							vv := (1 - 2*py/float64(h)) * s.Cam.TanHalf * aspect
							dir := s.Cam.Forward.Add(s.Cam.Right.Scale(u)).
								Add(s.Cam.Up.Scale(vv)).Norm()
							acc = acc.Add(s.Shade(dir))
						}
					}
					img.SetRGBA(x, y, toneMap(acc.Scale(inv*inv)))
				}
			}
		}()
	}
	for y := 0; y < h; y++ {
		rows <- y
	}
	close(rows)
	wg.Wait()
	return img
}

// toneMap applies Reinhard compression and gamma 2.2.
func toneMap(c Vec3) color.RGBA {
	f := func(v float64) uint8 {
		v = v / (1 + v)
		v = math.Pow(clamp01(v), 1/2.2)
		return uint8(v*255 + 0.5)
	}
	return color.RGBA{f(c.X), f(c.Y), f(c.Z), 255}
}
