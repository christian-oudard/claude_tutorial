package spec

// T1 (numeric): every number the specification quotes, recomputed from its
// own formula. Mirrors creek_equations.py so cross-language drift between
// the two suites is a test failure, not a surprise.
//
// The two documentation discrepancies found by the Python suite are pinned
// here as expected-discrepancy tests: if the document is ever corrected
// (or the formula changes), these fail and force the ledger to be updated.

import (
	"math"
	"testing"

	"github.com/christian-oudard/claude_tutorial/creek/phys"
)

func approx(t *testing.T, name string, computed, stated, reltol float64) {
	t.Helper()
	rel := math.Abs(computed-stated) / math.Abs(stated)
	if rel > reltol {
		t.Errorf("%s: computed %.6g vs stated %.6g (rel %.2g > %.2g)",
			name, computed, stated, rel, reltol)
	}
}

func TestQuotedNumbers(t *testing.T) {
	const (
		U, h = 0.5, 0.2 // bulk creek scales (§2)
	)

	// §2 scale analysis
	approx(t, "nu_w = mu/rho", phys.NuWater, 1.0e-6, 0.05)
	Re := U * h / phys.NuWater
	approx(t, "Re ~ 1e5", Re, 1e5, 0.10)

	N := math.Pow(Re, 2.25)
	if N < 1e11 || N > 1e12 {
		t.Errorf("DNS cell count Re^{9/4} = %.3g outside quoted [1e11,1e12]", N)
	}

	eps := U * U * U / h
	eta := math.Pow(phys.NuWater*phys.NuWater*phys.NuWater/eps, 0.25)
	if eta < 10e-6 || eta > 100e-6 {
		t.Errorf("Kolmogorov eta = %.3g m outside order-of-magnitude band", eta)
	}

	// §3.1 wave theory
	approx(t, "lambda_m ~ 1.7 cm", phys.LambdaCross(), 0.017, 0.05)
	approx(t, "c_min ~ 0.23 m/s", phys.CMin(), 0.23, 0.05)

	// §4.2 Nwogu
	za := -0.531
	alphaNwogu := za*za/2 + za
	approx(t, "Nwogu alpha (z=-0.531h)", alphaNwogu, -0.39, 0.03)

	// §6 optics
	approx(t, "critical angle 48.6 deg", phys.CriticalAngle()*180/math.Pi, 48.6, 0.01)
	approx(t, "Brewster angle 53.1 deg", phys.BrewsterAngle()*180/math.Pi, 53.1, 0.01)
	approx(t, "R0 ~ 0.02", phys.R0(), 0.02, 0.05)
	approx(t, "sun solid angle ~ 6.8e-5 sr", phys.SunSolidAngle(), 6.8e-5, 0.05)
}

func TestDocumentedDiscrepancies(t *testing.T) {
	// Discrepancy 1 (§2): the capillary CFL at dx = 100 um is ~33 us, not
	// the quoted ~1 us; ~1 us corresponds to dx ~ 10 um. The FORMULA is
	// dimensionally sound (see dims test); the annotation is off ~30x.
	dx := 100e-6
	dtSigma := math.Sqrt((phys.RhoWater + phys.RhoAir) * dx * dx * dx /
		(4 * math.Pi * phys.SigmaWater))
	approx(t, "dt_sigma(100um) is ~33 us (not ~1 us)", dtSigma, 33e-6, 0.05)
	if math.Abs(dtSigma-1e-6)/1e-6 < 1.0 {
		t.Error("dt_sigma suddenly matches the quoted 1 us — document/formula changed, update ledger")
	}
	// dx that actually yields 1 us:
	dx1us := math.Cbrt(1e-12 * 4 * math.Pi * phys.SigmaWater / (phys.RhoWater + phys.RhoAir))
	approx(t, "dx for dt_sigma = 1 us is ~10 um", dx1us, 10e-6, 0.10)

	// Discrepancy 2 (§2): eps ~ U^3/h gives eta ~ 36 um, ~2x below the
	// quoted 50-100 um band (same order; the estimate is order-of-magnitude).
	eps := 0.5 * 0.5 * 0.5 / 0.2
	eta := math.Pow(phys.NuWater*phys.NuWater*phys.NuWater/eps, 0.25)
	approx(t, "eta ~ 36 um from eps=U^3/h", eta, 35.6e-6, 0.05)
	if eta >= 50e-6 {
		t.Error("eta now inside the quoted 50-100 um band — update ledger")
	}
}
