package render

import "math"

// Vec3 is a minimal 3-vector for the renderer.
type Vec3 struct{ X, Y, Z float64 }

func (a Vec3) Add(b Vec3) Vec3      { return Vec3{a.X + b.X, a.Y + b.Y, a.Z + b.Z} }
func (a Vec3) Sub(b Vec3) Vec3      { return Vec3{a.X - b.X, a.Y - b.Y, a.Z - b.Z} }
func (a Vec3) Scale(s float64) Vec3 { return Vec3{a.X * s, a.Y * s, a.Z * s} }
func (a Vec3) Dot(b Vec3) float64   { return a.X*b.X + a.Y*b.Y + a.Z*b.Z }
func (a Vec3) Len() float64         { return math.Sqrt(a.Dot(a)) }

func (a Vec3) Norm() Vec3 {
	l := a.Len()
	if l == 0 {
		return Vec3{0, 0, 1}
	}
	return a.Scale(1 / l)
}

// MulV is the component-wise (Hadamard) product, used for spectral colors.
func (a Vec3) MulV(b Vec3) Vec3 { return Vec3{a.X * b.X, a.Y * b.Y, a.Z * b.Z} }

// Reflect mirrors incoming direction d (pointing into the surface) about
// normal n: r = d - 2(d·n)n.
func Reflect(d, n Vec3) Vec3 { return d.Sub(n.Scale(2 * d.Dot(n))) }

// Refract bends incoming direction d (unit, pointing into the surface)
// through a surface with normal n (unit, against d) and index ratio
// eta = n1/n2. Returns false on total internal reflection.
func Refract(d, n Vec3, eta float64) (Vec3, bool) {
	cosI := -d.Dot(n)
	sin2T := eta * eta * (1 - cosI*cosI)
	if sin2T > 1 {
		return Vec3{}, false
	}
	cosT := math.Sqrt(1 - sin2T)
	return d.Scale(eta).Add(n.Scale(eta*cosI - cosT)), true
}

func clamp01(x float64) float64 { return math.Max(0, math.Min(1, x)) }

func lerp(a, b, t float64) float64 { return a + (b-a)*t }

func lerpV(a, b Vec3, t float64) Vec3 {
	return Vec3{lerp(a.X, b.X, t), lerp(a.Y, b.Y, t), lerp(a.Z, b.Z, t)}
}

func smoothstep(e0, e1, x float64) float64 {
	t := clamp01((x - e0) / (e1 - e0))
	return t * t * (3 - 2*t)
}
