package wave

import (
	"math"
	"testing"

	"github.com/christian-oudard/claude_tutorial/creek/phys"
)

func TestStationaryWavenumberSolvesDopplerCondition(t *testing.T) {
	// §3.2: rock-locked waves satisfy U·k = -ω₀(k). The solver must return
	// a wavenumber on the capillary branch (k > k_m) whose residual in the
	// stationarity condition is tiny.
	U, depth := 0.5, 0.2
	for _, th := range []float64{0, 0.4, 0.9} {
		k, ok := KStationaryCapillary(U, depth, th)
		if !ok {
			t.Fatalf("no stationary wave at theta=%.1f despite supercritical flow", th)
		}
		if k <= phys.KCross() {
			t.Errorf("theta=%.1f: k=%g not on capillary branch (k_m=%g)", th, k, phys.KCross())
		}
		res := math.Abs(phys.Omega0(k, depth)-k*U*math.Cos(th)) / (k * U)
		if res > 1e-9 {
			t.Errorf("theta=%.1f: stationarity residual %g", th, res)
		}
	}
}

func TestStationaryExistenceGatedByCertifiedCMin(t *testing.T) {
	// The certified minimum phase speed is the existence threshold (§3.2):
	// subcritical flow carries no stationary capillary waves; supercritical
	// flow must carry them. Probe both sides of c_min ≈ 0.2315 m/s.
	depth := 0.2
	if _, ok := KStationaryCapillary(0.9*phys.CMin(), depth, 0); ok {
		t.Error("capillary stationary wave exists below c_min — violates certified threshold")
	}
	if _, ok := KStationaryCapillary(1.5*phys.CMin(), depth, 0); !ok {
		t.Error("no capillary stationary wave above c_min")
	}
	if _, ok := KStationaryGravity(0.9*phys.CMin(), depth, 0); ok {
		t.Error("gravity stationary wave exists below c_min")
	}
	kg, ok := KStationaryGravity(0.5, depth, 0)
	if !ok || kg >= phys.KCross() {
		t.Errorf("gravity branch root missing or off-branch: k=%g", kg)
	}
	kc, _ := KStationaryCapillary(0.5, depth, 0)
	if !(kg < phys.KCross() && phys.KCross() < kc) {
		t.Errorf("branches must straddle the certified k_m: %g, %g, %g",
			kg, phys.KCross(), kc)
	}
	// And obliquely: at angle theta the gate is U cos(theta) vs c_min.
	U := 0.5
	thCrit := math.Acos(phys.CMin() / U)
	if _, ok := KStationaryCapillary(U, depth, thCrit*0.9); !ok {
		t.Error("stationary wave missing inside the critical cone")
	}
	if _, ok := KStationaryCapillary(U, depth, thCrit*1.1); ok {
		t.Error("stationary wave present outside the critical cone")
	}
}

func TestRockFieldLocalizedAndFinite(t *testing.T) {
	rf := NewRockField(0, -0.5, 0.2, 0.0015, Capillary, [][2]float64{{0, 0}})
	// finite everywhere, exactly zero outside the local patch
	h, _, _ := rf.Sample(10, 10)
	if h != 0 {
		t.Error("rock pattern leaks far from the rock")
	}
	peak := 0.0
	for _, v := range rf.h {
		if math.IsNaN(v) {
			t.Fatal("NaN in rock pattern")
		}
		if a := math.Abs(v); a > peak {
			peak = a
		}
	}
	if math.Abs(peak-0.0015) > 1e-12 {
		t.Errorf("peak %g not normalized to amp", peak)
	}
	// The crescents must sit on the UPSTREAM side: flow is -y, so upstream
	// is +y of the rock. Compare energy in the two half-planes.
	var up, down float64
	for _, dy := range []float64{0.04, 0.07, 0.1, 0.15} {
		hu, _, _ := rf.Sample(0, +dy)
		hd, _, _ := rf.Sample(0, -dy)
		up += hu * hu
		down += hd * hd
	}
	if !(up > 4*down) {
		t.Errorf("crescents not upstream-dominant: up=%g down=%g", up, down)
	}
	// The gravity wake sits on the OPPOSITE side (downstream), with the
	// longer wavelength of its branch.
	wake := NewRockField(0, -0.5, 0.2, 0.003, Gravity, [][2]float64{{0, 0}})
	var wUp, wDown float64
	for _, dy := range []float64{0.15, 0.3, 0.5, 0.8} {
		hu, _, _ := wake.Sample(0, +dy)
		hd, _, _ := wake.Sample(0, -dy)
		wUp += hu * hu
		wDown += hd * hd
	}
	if !(wDown > 4*wUp) {
		t.Errorf("wake not downstream-dominant: up=%g down=%g", wUp, wDown)
	}
	// Subcritical flow: empty field.
	rf2 := NewRockField(0, -0.15, 0.2, 0.0015, Capillary, [][2]float64{{0, 0}})
	for _, v := range rf2.h {
		if v != 0 {
			t.Fatal("subcritical rock field should be empty")
		}
	}
}
