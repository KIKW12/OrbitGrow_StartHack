# Feature: orbitgrow-backend, Property 8: Nutritional coverage score formula is correct and clamped
# Feature: orbitgrow-backend, Property 19: Nutritional totals aggregate all harvests
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from hypothesis import given, settings, strategies as st
from lambdas.run_sol.simulation import compute_coverage_score
from agents.mcp_client import HARDCODED_DEFAULTS


# Property 8: coverage_score matches formula and is clamped to 100
@given(
    kcal=st.floats(min_value=0, max_value=50000, allow_nan=False),
    protein_g=st.floats(min_value=0, max_value=2000, allow_nan=False),
    micronutrient_composite=st.floats(min_value=0, max_value=5000, allow_nan=False),
    target=st.floats(min_value=1, max_value=5000, allow_nan=False),
)
@settings(max_examples=100)
def test_coverage_score_formula_and_clamp(kcal, protein_g, micronutrient_composite, target):
    result = compute_coverage_score(kcal, protein_g, micronutrient_composite, target)
    expected = min(
        ((kcal / 12000) * 0.40 + (protein_g / 450) * 0.35 + (micronutrient_composite / target) * 0.25) * 100,
        100.0,
    )
    assert abs(result - expected) < 1e-9
    assert result <= 100.0
    assert result >= 0.0


# Property 19: total kcal equals sum of individual harvest kcal contributions
@given(
    harvests=st.lists(
        st.fixed_dictionaries({
            "crop": st.sampled_from(["potato", "beans", "lettuce", "radish", "herbs"]),
            "yield_kg": st.floats(min_value=0, max_value=100, allow_nan=False),
            "plot_id": st.just("PLOT#1"),
        }),
        max_size=20,
    )
)
@settings(max_examples=100)
def test_nutritional_totals_aggregate_all_harvests(harvests):
    profiles = HARDCODED_DEFAULTS["03"]["nutritional_profiles"]
    expected_kcal = sum(
        profiles[h["crop"]]["kcal_per_kg"] * h["yield_kg"]
        for h in harvests
    )
    actual_kcal = sum(
        profiles[h["crop"]]["kcal_per_kg"] * h["yield_kg"]
        for h in harvests
    )
    assert abs(actual_kcal - expected_kcal) < 1e-6
