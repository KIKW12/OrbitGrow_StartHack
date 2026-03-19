# Feature: orbitgrow-backend, Property 23: Planner adjusts allocation on deficit
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from hypothesis import given, settings, strategies as st
from agents.planner_agent import PlannerAgent, BASELINE_ALLOCATION
from agents.mcp_client import MCPClient

BASELINE_BEANS = BASELINE_ALLOCATION["beans"]    # 0.25
BASELINE_POTATO = BASELINE_ALLOCATION["potato"]  # 0.45


def _count_crop(plot_assignments, crop):
    """Return fraction of plots assigned to the given crop."""
    return sum(1 for p in plot_assignments if p["crop"] == crop) / 20.0


def _make_planner():
    planner = PlannerAgent.__new__(PlannerAgent)
    planner.mcp = MCPClient.__new__(MCPClient)
    return planner


# Property 23a: protein deficit → beans allocation ≥ baseline + 5pp
@given(prev_score=st.floats(min_value=0, max_value=100, allow_nan=False))
@settings(max_examples=100)
def test_protein_deficit_increases_beans(prev_score):
    nutrition_report = {
        "crew_health_statuses": [
            {"astronaut": a, "deficit_flags": ["protein_low"], "health_score": prev_score}
            for a in ["commander", "scientist", "engineer", "pilot"]
        ]
    }
    planner = _make_planner()
    plan = PlannerAgent.run(planner, nutrition_report, {}, {})
    beans_fraction = _count_crop(plan["plot_assignments"], "beans")
    assert beans_fraction >= BASELINE_BEANS + 0.05 - 0.01  # small tolerance for integer rounding


# Property 23b: kcal deficit → potato allocation ≥ baseline + 5pp
@given(prev_score=st.floats(min_value=0, max_value=100, allow_nan=False))
@settings(max_examples=100)
def test_kcal_deficit_increases_potato(prev_score):
    nutrition_report = {
        "crew_health_statuses": [
            {"astronaut": a, "deficit_flags": ["kcal_low"], "health_score": prev_score}
            for a in ["commander", "scientist", "engineer", "pilot"]
        ]
    }
    planner = _make_planner()
    plan = PlannerAgent.run(planner, nutrition_report, {}, {})
    potato_fraction = _count_crop(plan["plot_assignments"], "potato")
    assert potato_fraction >= BASELINE_POTATO + 0.05 - 0.01
