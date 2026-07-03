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

	t0 := time.Now()
	ocean := wave.NewOcean(wave.Params{
		N: *n, L: 2.0, Depth: 0.2,
		UDrive: 0.5, // creek current drives the spectrum (§3.3: current, not wind)
		Ux:     0.5, Uy: 0.0,
		Cutoff: 0.004, Chop: 1.1, RMS: 0.006, Seed: 20260703,
	})
	fmt.Printf("  ocean init (%dx%d): %v   sub-grid slope var: %.4g (GGX alpha %.3f)\n",
		*n, *n, time.Since(t0).Round(time.Microsecond), ocean.SlopeVarTail,
		math.Max(0.02, math.Sqrt(2*ocean.SlopeVarTail)))

	cam := render.LookAt(
		render.Vec3{X: 0.0, Y: -1.15, Z: 0.42},
		render.Vec3{X: 0.0, Y: 1.2, Z: -0.05},
		58,
	)
	scene := render.NewScene(ocean, cam, render.Vec3{X: 0.12, Y: 0.78, Z: 0.52})

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
