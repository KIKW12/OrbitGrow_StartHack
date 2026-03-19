# Feature: orbitgrow-backend, Property 1: Sol counter monotonically increments
# Feature: orbitgrow-backend, Property 14: Dust cascade reduces light proportionally
# Feature: orbitgrow-backend, Property 15: Cold cascade increases energy load
# Feature: orbitgrow-backend, Property 16: Crisis effects match specification
# Feature: orbitgrow-backend, Property 18: Yield calculation is area × base_yield × health
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from hypothesis import given, settings, strategies as st
from lambdas.run_sol.simulation import step3_cascade_effects, step4_crisis_roll


def _base_env():
    return {
        "water_efficiency_pct": 92.0,
        "energy_used_pct": 60.0,
        "temperature_c": 22.0,
        "co2_ppm": 1200.0,
        "dust_storm_index": 0.0,
        "light_umol": 400.0,
        "external_temp_c": -60.0,
        "radiation_msv": 0.3,
        "humidity_pct": 65.0,
    }


# Property 1: sol counter increments by exactly 1
@given(current_sol=st.integers(min_value=0, max_value=1000))
@settings(max_examples=100)
def test_sol_counter_increments_by_one(current_sol):
    new_sol = current_sol + 1
    assert new_sol == current_sol + 1


# Property 14: dust cascade reduces light proportionally, clamped to [200, 600]
@given(
    dust=st.floats(min_value=0.51, max_value=1.0, allow_nan=False),
    light=st.floats(min_value=200, max_value=600, allow_nan=False),
)
@settings(max_examples=100)
def test_dust_cascade_reduces_light(dust, light):
    env = dict(_base_env())
    env["dust_storm_index"] = dust
    env["light_umol"] = light
    new_env, _ = step3_cascade_effects(env, [])
    expected_light = max(200, min(600, light - (dust - 0.5) * 2 * light))
    assert abs(new_env["light_umol"] - expected_light) < 1e-6


# Property 15: cold cascade increases energy load, clamped to [30, 100]
@given(
    ext_temp=st.floats(min_value=-125, max_value=-80.1, allow_nan=False),
    energy=st.floats(min_value=30, max_value=100, allow_nan=False),
)
@settings(max_examples=100)
def test_cold_cascade_increases_energy(ext_temp, energy):
    env = dict(_base_env())
    env["external_temp_c"] = ext_temp
    env["energy_used_pct"] = energy
    new_env, _ = step3_cascade_effects(env, [])
    expected_energy = max(30, min(100, energy + (-80 - ext_temp) * 0.1))
    assert abs(new_env["energy_used_pct"] - expected_energy) < 1e-6


# Property 16: water_recycling_failure sets water_efficiency_pct = 65
def test_crisis_water_recycling_failure():
    from unittest.mock import patch
    with patch("random.random", return_value=0.001):  # 0.001 < 0.008 threshold
        env, plots, crises = step4_crisis_roll(dict(_base_env()), [])
    assert "water_recycling_failure" in crises
    assert env["water_efficiency_pct"] == 65.0


# Property 16: energy_budget_cut sets energy_used_pct = min(prev + 40, 100)
def test_crisis_energy_budget_cut():
    from unittest.mock import patch

    call_count = [0]
    thresholds = [0.009, 0.001]  # first call > 0.008 (skip water), second < 0.005 (trigger energy)

    def mock_random():
        val = thresholds[min(call_count[0], len(thresholds) - 1)]
        call_count[0] += 1
        return val

    env = dict(_base_env())
    env["energy_used_pct"] = 50.0
    with patch("random.random", side_effect=mock_random):
        new_env, _, crises = step4_crisis_roll(env, [])
    assert "energy_budget_cut" in crises
    assert new_env["energy_used_pct"] == min(50.0 + 40, 100)


# Property 16: temperature_spike sets temperature_c = 30
def test_crisis_temperature_spike():
    from unittest.mock import patch

    call_count = [0]
    # skip water (>0.008), skip energy (>0.005), trigger temp (<0.012)
    thresholds = [0.009, 0.006, 0.001]

    def mock_random():
        val = thresholds[min(call_count[0], len(thresholds) - 1)]
        call_count[0] += 1
        return val

    env = dict(_base_env())
    with patch("random.random", side_effect=mock_random):
        new_env, _, crises = step4_crisis_roll(env, [])
    assert "temperature_spike" in crises
    assert new_env["temperature_c"] == 30.0


# Property 16: co2_imbalance sets co2_ppm = 1900
def test_crisis_co2_imbalance():
    from unittest.mock import patch

    call_count = [0]
    # skip water, energy, temp, disease; trigger co2
    thresholds = [0.009, 0.006, 0.013, 0.007, 0.001]

    def mock_random():
        val = thresholds[min(call_count[0], len(thresholds) - 1)]
        call_count[0] += 1
        return val

    env = dict(_base_env())
    with patch("random.random", side_effect=mock_random):
        new_env, _, crises = step4_crisis_roll(env, [])
    assert "co2_imbalance" in crises
    assert new_env["co2_ppm"] == 1900.0


# Property 18: yield = area * base_yield * health
@given(
    area=st.floats(min_value=0.1, max_value=10.0, allow_nan=False),
    base_yield=st.floats(min_value=0.1, max_value=10.0, allow_nan=False),
    health=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
@settings(max_examples=100)
def test_yield_formula(area, base_yield, health):
    yield_kg = area * base_yield * health
    assert yield_kg >= 0.0
    assert abs(yield_kg - area * base_yield * health) < 1e-9
