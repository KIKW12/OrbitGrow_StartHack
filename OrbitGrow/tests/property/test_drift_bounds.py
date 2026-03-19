# Feature: orbitgrow-backend, Property 13: Drift keeps all sensor values within hard bounds
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from hypothesis import given, settings, strategies as st
from lambdas.run_sol.simulation import apply_drift

# Test all 9 sensor configs: (name, drift, hard_min, hard_max)
SENSOR_CONFIGS = [
    ("external_temp_c", 8, -125, 20),
    ("dust_storm_index", 0.05, 0.0, 1.0),
    ("radiation_msv", 0.05, 0.1, 0.7),
    ("temperature_c", 1.5, 10, 35),
    ("humidity_pct", 3, 30, 95),
    ("co2_ppm", 80, 400, 2000),
    ("light_umol", 20, 200, 600),
    ("water_efficiency_pct", 1.5, 50, 99),
    ("energy_used_pct", 2, 30, 100),
]


@given(
    current=st.floats(min_value=-125, max_value=20, allow_nan=False, allow_infinity=False),
    delta=st.floats(min_value=-16, max_value=16, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_drift_bounds_external_temp_c(current, delta):
    result = apply_drift(current, abs(delta), hard_min=-125, hard_max=20)
    assert -125 <= result <= 20


@given(
    current=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    delta=st.floats(min_value=-0.1, max_value=0.1, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_drift_bounds_dust_storm_index(current, delta):
    result = apply_drift(current, abs(delta), hard_min=0.0, hard_max=1.0)
    assert 0.0 <= result <= 1.0


@given(
    current=st.floats(min_value=0.1, max_value=0.7, allow_nan=False, allow_infinity=False),
    delta=st.floats(min_value=-0.1, max_value=0.1, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_drift_bounds_radiation_msv(current, delta):
    result = apply_drift(current, abs(delta), hard_min=0.1, hard_max=0.7)
    assert 0.1 <= result <= 0.7


@given(
    current=st.floats(min_value=10, max_value=35, allow_nan=False, allow_infinity=False),
    delta=st.floats(min_value=-3.0, max_value=3.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_drift_bounds_temperature_c(current, delta):
    result = apply_drift(current, abs(delta), hard_min=10, hard_max=35)
    assert 10 <= result <= 35


@given(
    current=st.floats(min_value=30, max_value=95, allow_nan=False, allow_infinity=False),
    delta=st.floats(min_value=-6, max_value=6, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_drift_bounds_humidity_pct(current, delta):
    result = apply_drift(current, abs(delta), hard_min=30, hard_max=95)
    assert 30 <= result <= 95


@given(
    current=st.floats(min_value=400, max_value=2000, allow_nan=False, allow_infinity=False),
    delta=st.floats(min_value=-160, max_value=160, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_drift_bounds_co2_ppm(current, delta):
    result = apply_drift(current, abs(delta), hard_min=400, hard_max=2000)
    assert 400 <= result <= 2000


@given(
    current=st.floats(min_value=200, max_value=600, allow_nan=False, allow_infinity=False),
    delta=st.floats(min_value=-40, max_value=40, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_drift_bounds_light_umol(current, delta):
    result = apply_drift(current, abs(delta), hard_min=200, hard_max=600)
    assert 200 <= result <= 600


@given(
    current=st.floats(min_value=50, max_value=99, allow_nan=False, allow_infinity=False),
    delta=st.floats(min_value=-3.0, max_value=3.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_drift_bounds_water_efficiency_pct(current, delta):
    result = apply_drift(current, abs(delta), hard_min=50, hard_max=99)
    assert 50 <= result <= 99


@given(
    current=st.floats(min_value=30, max_value=100, allow_nan=False, allow_infinity=False),
    delta=st.floats(min_value=-4, max_value=4, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_drift_bounds_energy_used_pct(current, delta):
    result = apply_drift(current, abs(delta), hard_min=30, hard_max=100)
    assert 30 <= result <= 100
