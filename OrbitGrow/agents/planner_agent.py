"""
Planner Agent — produces a PlantingPlan each Sol based on nutritional and environmental state.
"""
from agents.mcp_client import MCPClient

# Baseline allocation percentages (20 plots: 9 potato, 5 beans, 4 lettuce, 1 radish, 1 herbs)
BASELINE_ALLOCATION = {
    "potato": 0.45,
    "beans": 0.25,
    "lettuce": 0.18,
    "radish": 0.06,
    "herbs": 0.06,
}

TOTAL_PLOTS = 20


def _allocation_to_plots(allocation: dict) -> list:
    """Convert fractional allocation to a list of 20 crop assignments."""
    plots = []
    remaining = TOTAL_PLOTS
    crops = list(allocation.keys())

    # Assign integer counts, distributing rounding to the largest crop
    counts = {}
    for crop in crops[:-1]:
        count = round(allocation[crop] * TOTAL_PLOTS)
        counts[crop] = count
        remaining -= count
    counts[crops[-1]] = remaining

    plot_num = 1
    for crop, count in counts.items():
        for _ in range(count):
            plots.append({"plot_id": f"PLOT#{plot_num}", "crop": crop})
            plot_num += 1

    return plots


class PlannerAgent:
    def __init__(self, mcp: MCPClient = None):
        self.mcp = mcp or MCPClient()

    def run(self, nutrition_report: dict, environment_report: dict, crisis_report: dict) -> dict:
        """
        Returns PlantingPlan dict with keys:
        plot_assignments, rationale, projected_coverage_score_next_sol
        """
        allocation = dict(BASELINE_ALLOCATION)

        # Collect all deficit flags across all astronauts
        crew_health_statuses = nutrition_report.get("crew_health_statuses", [])
        all_deficit_flags = []
        for status in crew_health_statuses:
            all_deficit_flags.extend(status.get("deficit_flags", []))

        rationale_parts = ["Baseline allocation: 45% potato, 25% beans, 18% lettuce, 6% radish, 6% herbs."]
        adjustments_made = []

        has_protein_low = "protein_low" in all_deficit_flags
        has_kcal_low = "kcal_low" in all_deficit_flags

        if has_protein_low and has_kcal_low:
            allocation["beans"] = min(1.0, allocation["beans"] + 0.05)
            allocation["potato"] = min(1.0, allocation["potato"] + 0.05)
            allocation["lettuce"] = max(0.0, allocation["lettuce"] - 0.05)
            allocation["radish"] = max(0.0, allocation["radish"] - 0.025)
            allocation["herbs"] = max(0.0, allocation["herbs"] - 0.025)
            adjustments_made.append("protein deficit: beans +5pp")
            adjustments_made.append("kcal deficit: potato +5pp")
        elif has_protein_low:
            shift = min(0.05, allocation["potato"])
            allocation["beans"] = allocation["beans"] + shift
            allocation["potato"] = allocation["potato"] - shift
            adjustments_made.append("protein deficit detected: beans +5pp (shifted from potato)")
        elif has_kcal_low:
            shift = min(0.05, allocation["beans"])
            allocation["potato"] = allocation["potato"] + shift
            allocation["beans"] = allocation["beans"] - shift
            adjustments_made.append("kcal deficit detected: potato +5pp (shifted from beans)")

        if adjustments_made:
            rationale_parts.append("Adjustments: " + "; ".join(adjustments_made) + ".")
        else:
            rationale_parts.append("No nutritional deficits active; maintaining baseline allocation.")

        plot_assignments = _allocation_to_plots(allocation)

        # Projected coverage score estimate
        projected_kcal_factor = allocation["potato"] * 0.9 + allocation["beans"] * 0.7
        projected_protein_factor = allocation["beans"] * 0.9 + allocation["potato"] * 0.3
        projected_coverage_score_next_sol = min(
            100.0,
            (projected_kcal_factor * 0.40 + projected_protein_factor * 0.35 + 0.25) * 100
        )

        rationale = " ".join(rationale_parts)

        return {
            "plot_assignments": plot_assignments,
            "rationale": rationale,
            "projected_coverage_score_next_sol": round(projected_coverage_score_next_sol, 2),
        }
