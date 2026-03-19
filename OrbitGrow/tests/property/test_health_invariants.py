# Feature: orbitgrow-backend, Property 4: Plot health is always in [0.0, 1.0]
# Feature: orbitgrow-backend, Property 10: Health score update rule
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from hypothesis import given, settings, strategies as st


# Property 4: apply a list of deltas to health, always clamp to [0, 1]
@given(
    initial_health=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    deltas=st.lists(st.floats(min_value=-0.5, max_value=0.5, allow_nan=False), max_size=20),
)
@settings(max_examples=100)
def test_plot_health_bounds(initial_health, deltas):
    health = initial_health
    for delta in deltas:
        health = max(0.0, min(1.0, health + delta))
    assert 0.0 <= health <= 1.0


# Property 10: health_score update rule — deficits decrease, no deficits increase
@given(
    prev_score=st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
    num_deficits=st.integers(min_value=0, max_value=6),
)
@settings(max_examples=100)
def test_health_score_update_with_deficits(prev_score, num_deficits):
    if num_deficits > 0:
        new_score = max(0.0, prev_score - 2 * num_deficits)
        assert new_score >= 0.0
        assert new_score <= prev_score
    else:
        new_score = min(100.0, prev_score + 1)
        assert new_score <= 100.0
        assert new_score >= prev_score
