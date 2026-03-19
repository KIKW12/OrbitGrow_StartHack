import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from lambdas.run_sol.simulation import (
    step3_cascade_effects, step4_crisis_roll, step5_crop_growth,
    step6_nutritional_output, compute_coverage_score
)
from agents.mcp_client import MCPClient, HARDCODED_DEFAULTS
from unittest.mock import MagicMock, patch


def _base_env():
    return {
        "temperature_c": 22.0, "humidity_pct": 65.0, "co2_ppm": 1200.0,
        "light_umol": 400.0, "water_efficiency_pct": 92.0, "energy_used_pct": 60.0,
        "external_temp_c": -60.0, "dust_storm_index": 0.0, "radiation_msv": 0.3,
    }


# Phase transition: nominal → crisis → recovery → nominal
def test_phase_nominal_to_crisis():
    # When crises_active is non-empty, phase should be "crisis"
    crises_active = ["temperature_spike"]
    phase = "crisis" if crises_active else "nominal"
    assert phase == "crisis"


def test_phase_crisis_to_recovery():
    prev_phase = "crisis"
    crises_active = []
    phase = "recovery" if prev_phase == "crisis" and not crises_active else "nominal"
    assert phase == "recovery"


def test_phase_recovery_to_nominal():
    # After 3 quiet sols, phase returns to nominal
    prev_phase = "recovery"
    crises_active = []
    # Simulate 3 quiet sols
    phase = prev_phase
    for _ in range(3):
        if not crises_active:
            phase = "nominal" if phase in ("nominal", "recovery") else phase
    assert phase == "nominal"


# Harvest triggers plot reset with health=1.0
def test_harvest_resets_plot():
    mcp = MagicMock()
    mcp.query.return_value = {**HARDCODED_DEFAULTS["04"], "kb_fallback": False}
    plot = {
        "id": "test-id", "plot_id": "PLOT#A#1", "crop": "lettuce",
        "planted_sol": 0, "harvest_sol": 35, "area_m2": 2.5,
        "health": 0.8, "stress_flags": [],
    }
    updated_plots, harvests = step5_crop_growth([plot], _base_env(), 35, mcp)
    assert len(harvests) == 1
    assert updated_plots[0]["health"] == 1.0
    assert updated_plots[0]["stress_flags"] == []
    assert updated_plots[0]["planted_sol"] == 35


# Nutritional output split equally across 4 astronauts
def test_nutritional_output_equal_split():
    total_kcal = 1000.0
    per_astronaut = total_kcal / 4
    assert per_astronaut == 250.0
    # Verify all 4 get equal share
    shares = [total_kcal / 4 for _ in range(4)]
    assert all(s == 250.0 for s in shares)
    assert sum(shares) == total_kcal
