// Command creek renders the spectral creek surface and reports timings.
//
// The math it runs is certified by `go test ./...`: the spec package
// checks dimensional consistency, exact algebraic identities, the quoted
// numbers, and pins the float64 runtime layer (phys) against the exact
// kernel. Run the tests first; then run this.
package main

import (
	"flag"
	"fmt"
	"image/png"
	"math"
	"os"
	"path/filepath"
	"time"

	"github.com/christian-oudard/claude_tutorial/creek/phys"
	"github.com/christian-oudard/claude_tutorial/creek/render"
	"github.com/christian-oudard/claude_tutorial/creek/wave"
)

func main() {
	var (
		n      = flag.Int("n", 256, "wave grid resolution (power of two)")
		w      = flag.Int("w", 960, "image width")
		h      = flag.Int("h", 540, "image height")
		frames = flag.Int("frames", 3, "number of frames")
		dt     = flag.Float64("dt", 0.4, "time step between frames, s")
		ss     = flag.Int("ss", 2, "supersamples per pixel side")
		out    = flag.String("out", "out", "output directory")
	)
	flag.Parse()

	fmt.Println("creek: spectral surface, constants derived from the verified layer")
	fmt.Printf("  lambda_m = %.4f m   c_min = %.4f m/s   R0 = %.5f   Omega_sun = %.3g sr\n",
		phys.LambdaCross(), phys.CMin(), phys.R0(), phys.SunSolidAngle())

	// Multiscale cascade (§7.2, spectral form): three bands partition
	// k-space so the same wave carries ~10 cm chop, centimeter ripples
	// around the certified crossover, and millimeter capillary texture.
	// Splits in rad/m: [0,250) / [250,1000) / [1000,∞).
	base := wave.Params{
		Depth:  0.2,
		UDrive: 0.5,           // creek current drives the spectrum (§3.3: current, not wind)
		Ux:     0.0, Uy: -0.5, // flow toward the camera
		CapAmp: 0.7, // ripple bump anchored at the certified k_m
	}
	bandA := base // gravity chop: 2 m patch, cell 7.8 mm
	bandA.N, bandA.L, bandA.KHi, bandA.Chop, bandA.Seed = *n, 2.0, 250, 1.1, 20260703
	bandB := base // crossover ripples: 0.5 m patch, cell 2 mm
	bandB.N, bandB.L, bandB.KLo, bandB.KHi, bandB.Chop, bandB.Cutoff, bandB.Spread, bandB.Seed =
		*n, 0.5, 250, 1000, 0.7, 0.0016, 0.3, 20260704
	bandC := base // capillary texture: 0.15 m patch, cell 0.6 mm
	bandC.N, bandC.L, bandC.KLo, bandC.Chop, bandC.Cutoff, bandC.Spread, bandC.Seed =
		*n, 0.15, 1000, 0.4, 0.0009, 0.4, 20260705

	t0 := time.Now()
	ocean := wave.NewCascade([]wave.Params{bandA, bandB, bandC}, 0.0028)

	// §3.2 rock-locked stationary waves, both branches of the certified
	// dispersion relation (existence gated by c_min = 0.2315 m/s < U):
	// the 16 cm gravity wake downstream, the 2 mm capillary crescents
	// upstream of each rock.
	rocks := [][2]float64{{0.05, 0.10}, {-0.55, 0.55}, {0.45, 1.15}, {-0.15, 2.0}}
	ocean.Rocks = []*wave.RockField{
		wave.NewRockField(base.Ux, base.Uy, base.Depth, 0.007, wave.Gravity, rocks),
		wave.NewRockField(base.Ux, base.Uy, base.Depth, 0.0018, wave.Capillary, rocks),
	}
	if k, ok := wave.KStationaryGravity(0.5, base.Depth, 0); ok {
		fmt.Printf("  stationary gravity wake: lambda = %.1f cm (solved from certified dispersion)\n",
			200*math.Pi/k)
	}
	if k, ok := wave.KStationaryCapillary(0.5, base.Depth, 0); ok {
		fmt.Printf("  stationary capillary crescents: lambda = %.2f mm\n", 2000*math.Pi/k)
	}
	fmt.Printf("  cascade init (3 x %dx%d): %v   sub-grid slope var: %.4g (GGX alpha %.3f)\n",
		*n, *n, time.Since(t0).Round(time.Microsecond), ocean.SlopeTail(),
		math.Max(0.02, math.Sqrt(2*ocean.SlopeTail())))
	for _, b := range ocean.Bands {
		hi := "inf"
		if b.P.KHi > 0 {
			hi = fmt.Sprintf("%.0f", b.P.KHi)
		}
		fmt.Printf("    band L=%.2fm cell=%.2gmm window=[%.0f,%s) rad/m  slopeVar=%.4g\n",
			b.P.L, 1000*b.P.L/float64(b.P.N), b.P.KLo, hi, b.SlopeVarGrid)
	}

	cam := render.LookAt(
		render.Vec3{X: 0.0, Y: -1.0, Z: 0.32},
		render.Vec3{X: 0.0, Y: 1.4, Z: -0.06},
		58,
	)
	scene := render.NewScene(ocean, 0.2, cam, render.Vec3{X: 0.12, Y: 0.78, Z: 0.52})
	scene.RockPos = rocks

	// §7.1 GSD check: is the pixel footprint small enough for the finest band?
	gsdNear := 0.5 * 2 * math.Tan(29*math.Pi/180) / float64(*w)
	fmt.Printf("  GSD at 0.5 m: %.2f mm/px (finest band cell %.2f mm)\n",
		gsdNear*1000, 1000*bandC.L/float64(bandC.N))

	if err := os.MkdirAll(*out, 0o755); err != nil {
		panic(err)
	}
	for f := 0; f < *frames; f++ {
		tSim := time.Now()
		ocean.Step(float64(f) * *dt)
		simMS := time.Since(tSim)

		tRen := time.Now()
		img := scene.Render(*w, *h, *ss)
		renMS := time.Since(tRen)

		name := filepath.Join(*out, fmt.Sprintf("frame_%02d.png", f))
		file, err := os.Create(name)
		if err != nil {
			panic(err)
		}
		if err := png.Encode(file, img); err != nil {
			panic(err)
		}
		file.Close()
		fmt.Printf("  frame %d: sim %v  render %v  -> %s\n",
			f, simMS.Round(time.Microsecond), renMS.Round(time.Millisecond), name)
	}
}
