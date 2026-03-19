import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from unittest.mock import MagicMock, patch
from agents.crisis_agent import CrisisAgent
from agents.nutrition_agent import NutritionAgent
from agents.mcp_client import MCPClient, HARDCODED_DEFAULTS


# CrisisAgent returns no-op report when crises_active is empty
def test_crisis_agent_no_op_when_no_crises():
    mcp = MagicMock()
    agent = CrisisAgent(mcp=mcp)
    report = agent.run(sol=5, crises_active=[])
    assert report["crises_handled"] == []
    assert report["actions_taken"] == []
    assert report["recovery_timeline_sols"] == {}
    assert "No active crises" in report["reasoning"]
    mcp.query.assert_not_called()


# MCP fallback sets kb_fallback: True when endpoint unreachable
def test_mcp_fallback_sets_kb_fallback_flag():
    client = MCPClient()
    with patch.object(client, "_async_query", side_effect=Exception("Connection refused")):
        result = client.query("03", "test query")
    assert result.get("kb_fallback") is True
    assert "nutritional_profiles" in result  # falls back to HARDCODED_DEFAULTS


# Crew health emergency flag appears when any astronaut score < 60
def test_crew_health_emergency_when_score_below_60():
    mcp = MagicMock()
    mcp.query.return_value = {**HARDCODED_DEFAULTS["03"], "kb_fallback": False}

    agent = NutritionAgent(mcp=mcp)

    # Provide prev_crew_health with score of 61 and many deficits to push below 60
    prev_crew_health = [
        {"astronaut": a, "health_score": 61.0}
        for a in ["commander", "scientist", "engineer", "pilot"]
    ]

    # Zero nutrition → all deficits → score drops from 61 by 2*6=12 → 49 < 60
    nutrition_ledger = {
        "kcal": 0.0, "protein_g": 0.0, "vitamin_a": 0.0,
        "vitamin_c": 0.0, "vitamin_k": 0.0, "folate": 0.0,
    }

    report = agent.run(sol=10, nutrition_ledger=nutrition_ledger, prev_crew_health=prev_crew_health)
    assert report["crew_health_emergency"] is True
    # Verify at least one astronaut has score < 60
    assert any(s["health_score"] < 60 for s in report["crew_health_statuses"])
