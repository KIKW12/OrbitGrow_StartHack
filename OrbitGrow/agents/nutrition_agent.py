"""
Nutrition Agent — computes nutritional coverage and per-astronaut health,
using Syngenta KB data + Claude reasoning for deficit analysis.
"""
import json
import logging

from agents.mcp_client import MCPClient, STRUCTURED_DATA

logger = logging.getLogger(__name__)

ASTRONAUTS = ["commander", "scientist", "engineer", "pilot"]

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

    def _get_strands_agent(self):
        from strands import Agent
        from strands.models import BedrockModel
        model = BedrockModel(
            model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            region_name="us-west-2",
        )
        return Agent(model=model)

    def run(self, sol: int, nutrition_ledger: dict, prev_crew_health: list = None) -> dict:
        """
        Returns NutritionReport with KB-grounded reasoning.
        """
        # 1. Query Syngenta MCP KB for nutritional guidance
        kb = self.mcp.query_kb(
            "daily nutritional targets crew protein vitamin calorie Mars "
            "greenhouse astronaut health micronutrient deficiency",
            max_results=3,
        )
        kb_context = "\n---\n".join(kb["chunks"]) if kb["chunks"] else ""
        kb_fallback = kb.get("kb_fallback", True)

        # Extract current nutrition
        kcal = nutrition_ledger.get("kcal", 0.0)
        protein_g = nutrition_ledger.get("protein_g", 0.0)
        vitamin_a = nutrition_ledger.get("vitamin_a", 0.0)
        vitamin_c = nutrition_ledger.get("vitamin_c", 0.0)
        vitamin_k = nutrition_ledger.get("vitamin_k", 0.0)
        folate = nutrition_ledger.get("folate", 0.0)

        coverage_score = compute_coverage_score(kcal, protein_g, vitamin_a, vitamin_c, vitamin_k, folate)

        # Build per-astronaut health
        prev_health_map = {}
        if prev_crew_health:
            for record in prev_crew_health:
                a = record.get("astronaut")
                if a:
                    prev_health_map[a] = record.get("health_score", 100)

        crew_health_statuses = []
        crew_health_emergency = False
        all_deficit_flags = []

        for astronaut in ASTRONAUTS:
            astro_kcal = kcal / 4
            astro_protein = protein_g / 4
            astro_va = vitamin_a / 4
            astro_vc = vitamin_c / 4
            astro_vk = vitamin_k / 4
            astro_folate = folate / 4

            # Deficit flags: severe deficits only (below 30% of target)
            deficit_flags = []
            threshold = 0.30
            if astro_kcal < _DAILY_TARGETS["kcal"] / 4 * threshold:
                deficit_flags.append("kcal_low")
            if astro_protein < _DAILY_TARGETS["protein_g"] / 4 * threshold:
                deficit_flags.append("protein_low")
            if astro_va < _DAILY_TARGETS["vitamin_a"] / 4 * threshold:
                deficit_flags.append("vitamin_a_low")
            if astro_vc < _DAILY_TARGETS["vitamin_c"] / 4 * threshold:
                deficit_flags.append("vitamin_c_low")
            if astro_vk < _DAILY_TARGETS["vitamin_k"] / 4 * threshold:
                deficit_flags.append("vitamin_k_low")
            if astro_folate < _DAILY_TARGETS["folate"] / 4 * threshold:
                deficit_flags.append("folate_low")

            # Health score driven by coverage
            prev_score = prev_health_map.get(astronaut, 100)
            if coverage_score >= 85:
                delta = 1.0 + (coverage_score - 85) * 0.2
            elif coverage_score >= 75:
                delta = (coverage_score - 80) * 0.1
            else:
                delta = -1.5 - (75 - coverage_score) * 0.15
            health_score = max(10, min(100, prev_score + delta))

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

        # 2. Try LLM-grounded deficit analysis with KB data
        deficit_summary = ""
        if kb_context and not kb_fallback:
            try:
                deficit_summary = self._analyze_with_kb(
                    sol, kcal, protein_g, vitamin_a, vitamin_c, vitamin_k, folate,
                    coverage_score, unique_deficits, kb_context
                )
            except Exception as exc:
                logger.warning("LLM nutrition analysis failed: %s", exc)

        if not deficit_summary:
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
            "kb_fallback": kb_fallback,
            "kb_context": kb_context,
        }

    def _analyze_with_kb(self, sol, kcal, protein_g, vitamin_a, vitamin_c, vitamin_k, folate,
                         coverage_score, deficit_flags, kb_context):
        """Use Strands Agent + Syngenta KB for nutritional analysis."""
        agent = self._get_strands_agent()

        targets = _DAILY_TARGETS
        prompt = f"""You are the Nutrition Agent for a Mars greenhouse feeding 4 astronauts.

## Syngenta Knowledge Base Data
{kb_context}

## Current Nutritional Status (Sol {sol})
- kcal: {kcal:.0f} / {targets['kcal']} target ({kcal/targets['kcal']*100:.0f}%)
- Protein: {protein_g:.0f}g / {targets['protein_g']}g target ({protein_g/targets['protein_g']*100:.0f}%)
- Vitamin A: {vitamin_a:.0f} / {targets['vitamin_a']} target ({vitamin_a/targets['vitamin_a']*100:.0f}%)
- Vitamin C: {vitamin_c:.0f} / {targets['vitamin_c']} target ({vitamin_c/targets['vitamin_c']*100:.0f}%)
- Vitamin K: {vitamin_k:.0f} / {targets['vitamin_k']} target ({vitamin_k/targets['vitamin_k']*100:.0f}%)
- Folate: {folate:.3f} / {targets['folate']} target ({folate/targets['folate']*100:.0f}%)
- Coverage Score: {coverage_score:.1f}%
- Severe Deficit Flags: {deficit_flags or 'none'}

Analyze the crew's nutritional status using the Syngenta KB data. Reference specific KB recommendations.
Provide a 2-3 sentence assessment of current deficits and what crops should be prioritized.
Only return the assessment text, no JSON."""

        response = agent(prompt)
        return str(response).strip()[:500]
