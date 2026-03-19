import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from unittest.mock import patch, MagicMock
from lambdas.init_mission.handler import lambda_handler, _build_mission_state, _build_plots, _build_environment_state


def test_mission_state_sol_0():
    state = _build_mission_state()
    assert state["current_sol"] == 0
    assert state["phase"] == "nominal"
    assert state["id"] == "MISSION"
    assert "last_updated" in state


def test_plots_count_is_20():
    plots = _build_plots()
    assert len(plots) == 20


def test_plots_crop_distribution():
    plots = _build_plots()
    from collections import Counter
    counts = Counter(p["crop"] for p in plots)
    assert counts["potato"] == 9
    assert counts["beans"] == 5
    assert counts["lettuce"] == 4
    assert counts["radish"] == 1
    assert counts["herbs"] == 1


def test_plots_initial_health_and_flags():
    plots = _build_plots()
    for plot in plots:
        assert plot["health"] == 1.0
        assert plot["stress_flags"] == []
        assert plot["planted_sol"] == 0


def test_environment_state_sol_0():
    env = _build_environment_state()
    assert env["sol"] == 0
    assert env["temperature_c"] == 22.0
    assert env["humidity_pct"] == 65.0
    assert env["co2_ppm"] == 1200.0
    assert env["light_umol"] == 400.0
    assert env["water_efficiency_pct"] == 92.0
    assert env["energy_used_pct"] == 60.0
    assert env["external_temp_c"] == -60.0
    assert env["dust_storm_index"] == 0.0
    assert env["radiation_msv"] == 0.3


def test_lambda_handler_returns_200():
    with patch("lambdas.init_mission.handler.dynamodb") as mock_ddb:
        mock_table = MagicMock()
        mock_ddb.Table.return_value = mock_table
        response = lambda_handler({}, None)
    assert response["statusCode"] == 200
    import json
    body = json.loads(response["body"])
    assert body["plots_seeded"] == 20
    assert body["sol"] == 0
