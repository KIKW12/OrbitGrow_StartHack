"""
Nutrition Agent — computes nutritional coverage and per-astronaut health scores.
"""
from agents.mcp_client import MCPClient, STRUCTURED_DATA

ASTRONAUTS = ["commander", "scientist", "engineer", "pilot"]

# Pull targets from structured data so there's one source of truth
_NUTRITION = STRUCTURED_DATA["nutrition"]
_DAILY_TARGETS = _NUTRITION["daily_targets"]


def compute_coverage_score(kcal: float, protein_g: float, vitamin_a: float,
                           vitamin_c: float, vitamin_k: float, folate: float) -> float:
    """
    Weighted coverage score (0–100).
    Each nutrient normalized to its daily target, then weighted:
      kcal 40%, protein 35%, micronutrients 25% (avg of 4 vitamins).
    """
    t = _DAILY_TARGETS
    micro = (
        min(1.0, vitamin_a / t["vitamin_a"] if t["vitamin_a"] else 0) +
        min(1.0, vitamin_c / t["vitamin_c"] if t["vitamin_c"] else 0) +
        min(1.0, vitamin_k / t["vitamin_k"] if t["vitamin_k"] else 0) +
        min(1.0, folate / t["folate"] if t["folate"] else 0)
    ) / 4

    score = (
        min(1.0, kcal / t["kcal"]) * 0.40 +
        min(1.0, protein_g / t["protein_g"]) * 0.35 +
        micro * 0.25
    ) * 100
    return min(score, 100.0)


class NutritionAgent:
    def __init__(self, mcp: MCPClient = None, dynamodb=None):
        self.mcp = mcp or MCPClient()
        self.dynamodb = dynamodb

    def run(self, sol: int, nutrition_ledger: dict, prev_crew_health: list = None) -> dict:
        """
        Returns NutritionReport dict with keys:
        coverage_score, kcal_produced, protein_g, crew_health_statuses,
        deficit_summary, crew_health_emergency, kb_context
        """
        # Query KB for context text (used in reasoning, not for parameters)
        kb = self.mcp.query_kb("daily nutritional targets crew protein vitamin Mars greenhouse", max_results=2)
        kb_context = "\n---\n".join(kb["chunks"]) if kb["chunks"] else ""

        targets = _DAILY_TARGETS

        # Extract current nutrition from ledger
        kcal = nutrition_ledger.get("kcal", 0.0)
        protein_g = nutrition_ledger.get("protein_g", 0.0)
        vitamin_a = nutrition_ledger.get("vitamin_a", 0.0)
        vitamin_c = nutrition_ledger.get("vitamin_c", 0.0)
        vitamin_k = nutrition_ledger.get("vitamin_k", 0.0)
        folate = nutrition_ledger.get("folate", 0.0)

        # Compute coverage score
        coverage_score = compute_coverage_score(
            kcal, protein_g, vitamin_a, vitamin_c, vitamin_k, folate
        )

        # Per-astronaut health computation
        prev_health_map = {}
        if prev_crew_health:
            for record in prev_crew_health:
                astronaut = record.get("astronaut")
                if astronaut:
                    prev_health_map[astronaut] = record.get("health_score", 100)

        crew_health_statuses = []
        crew_health_emergency = False
        all_deficit_flags = []

        for astronaut in ASTRONAUTS:
            # Per-astronaut share (divide by 4)
            astro_kcal = kcal / 4
            astro_protein = protein_g / 4
            astro_va = vitamin_a / 4
            astro_vc = vitamin_c / 4
            astro_vk = vitamin_k / 4
            astro_folate = folate / 4

            # Compute deficit flags
            deficit_flags = []
            if astro_kcal < targets["kcal"] / 4:
                deficit_flags.append("kcal_low")
            if astro_protein < targets["protein_g"] / 4:
                deficit_flags.append("protein_low")
            if astro_va < targets["vitamin_a"] / 4:
                deficit_flags.append("vitamin_a_low")
            if astro_vc < targets["vitamin_c"] / 4:
                deficit_flags.append("vitamin_c_low")
            if astro_vk < targets["vitamin_k"] / 4:
                deficit_flags.append("vitamin_k_low")
            if astro_folate < targets["folate"] / 4:
                deficit_flags.append("folate_low")

            # Update health_score
            prev_score = prev_health_map.get(astronaut, 100)
            if not deficit_flags:
                health_score = min(100, prev_score + 1)
            else:
                health_score = max(0, prev_score - 2 * len(deficit_flags))

            if health_score < 60:
                crew_health_emergency = True

            all_deficit_flags.extend(deficit_flags)

            crew_health_statuses.append({
                "astronaut": astronaut,
                "sol": sol,
                "kcal_received": astro_kcal,
                "protein_g": astro_protein,
                "vitamin_a": astro_va,
                "vitamin_c": astro_vc,
                "vitamin_k": astro_vk,
                "folate": astro_folate,
                "health_score": health_score,
                "deficit_flags": deficit_flags,
            })

        unique_deficits = list(set(all_deficit_flags))
        deficit_summary = (
            f"Active deficits: {', '.join(unique_deficits)}" if unique_deficits
            else "All nutritional targets met."
        )

        return {
            "coverage_score": coverage_score,
            "kcal_produced": kcal,
            "protein_g": protein_g,
            "crew_health_statuses": crew_health_statuses,
            "deficit_summary": deficit_summary,
            "crew_health_emergency": crew_health_emergency,
            "kb_fallback": kb.get("kb_fallback", False),
            "kb_context": kb_context,
        }
