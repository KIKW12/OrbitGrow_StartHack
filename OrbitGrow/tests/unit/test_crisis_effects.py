import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

import json
from unittest.mock import patch, MagicMock
from lambdas.run_sol.simulation import step4_crisis_roll


def _base_env():
    return {
        "water_efficiency_pct": 92.0, "energy_used_pct": 60.0,
        "temperature_c": 22.0, "co2_ppm": 1200.0, "dust_storm_index": 0.0,
        "light_umol": 400.0, "external_temp_c": -60.0, "radiation_msv": 0.3,
        "humidity_pct": 65.0,
    }


def _force_crisis(crisis_index):
    """Return a mock_random side_effect that triggers only the crisis at crisis_index."""
    call_count = 0

    def side_effect():
        nonlocal call_count
        val = 0.001 if call_count == crisis_index else 0.999
        call_count += 1
        return val

    return side_effect


def test_water_recycling_failure_effect():
    with patch("random.random", side_effect=_force_crisis(0)):
        env, plots, crises = step4_crisis_roll(_base_env(), [])
    assert "water_recycling_failure" in crises
    assert env["water_efficiency_pct"] == 65.0


def test_energy_budget_cut_effect():
    env = _base_env()
    env["energy_used_pct"] = 50.0
    with patch("random.random", side_effect=_force_crisis(1)):
        new_env, plots, crises = step4_crisis_roll(env, [])
    assert "energy_budget_cut" in crises
    assert new_env["energy_used_pct"] == min(50.0 + 40, 100)


def test_temperature_spike_effect():
    with patch("random.random", side_effect=_force_crisis(2)):
        env, plots, crises = step4_crisis_roll(_base_env(), [])
    assert "temperature_spike" in crises
    assert env["temperature_c"] == 30.0


def test_disease_outbreak_effect():
    plots = [
        {"plot_id": f"PLOT#{i}", "crop": "potato", "health": 1.0, "stress_flags": [], "area_m2": 2.5}
        for i in range(20)
    ]
    with patch("random.random", side_effect=_force_crisis(3)):
        with patch("random.randint", return_value=0):  # zone 0 = plots 0-4
            env, updated_plots, crises = step4_crisis_roll(_base_env(), plots)
    assert "disease_outbreak" in crises
    for i in range(5):
        assert updated_plots[i]["health"] <= 0.7  # 1.0 - 0.3
        assert "disease" in updated_plots[i]["stress_flags"]


def test_co2_imbalance_effect():
    with patch("random.random", side_effect=_force_crisis(4)):
        env, plots, crises = step4_crisis_roll(_base_env(), [])
    assert "co2_imbalance" in crises
    assert env["co2_ppm"] == 1900.0


def test_unknown_crisis_type_returns_400():
    from lambdas.inject_crisis.handler import handler as inject_handler
    event = {"body": json.dumps({"type": "alien_invasion"})}
    response = inject_handler(event, None)
    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "Invalid crisis type" in body["message"]
