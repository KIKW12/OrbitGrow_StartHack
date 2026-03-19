"""
Planner Agent — produces a PlantingPlan each Sol.
Uses Syngenta KB data + Claude reasoning for crop allocation decisions.
"""
import json
import logging

from agents.mcp_client import MCPClient, STRUCTURED_DATA

logger = logging.getLogger(__name__)

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

    def _get_strands_agent(self):
        from strands import Agent
        from strands.models import BedrockModel
        model = BedrockModel(
            model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            region_name="us-west-2",
        )
        return Agent(model=model)

    def run(self, nutrition_report: dict, environment_report: dict, crisis_report: dict) -> dict:
        """
        Returns PlantingPlan with KB-grounded crop allocation.
        """
        # 1. Query Syngenta MCP KB for planting guidance
        kb = self.mcp.query_kb(
            "crop selection planting strategy Mars greenhouse yield optimization "
            "nutritional balance potato beans lettuce radish herbs allocation",
            max_results=3,
        )
        kb_context = "\n---\n".join(kb["chunks"]) if kb["chunks"] else ""
        kb_fallback = kb.get("kb_fallback", True)

        # 2. Try LLM-grounded planning with KB data
        if kb_context and not kb_fallback:
            try:
                result = self._plan_with_kb(nutrition_report, environment_report, crisis_report, kb_context)
                result["kb_fallback"] = False
                result["kb_context"] = kb_context
                return result
            except Exception as exc:
                logger.warning("LLM planner decision failed: %s — using rule-based fallback", exc)

        # 3. Fallback: rule-based allocation
        return self._plan_rules(nutrition_report, environment_report, crisis_report, kb_context, kb_fallback)

    def _plan_with_kb(self, nutrition_report, environment_report, crisis_report, kb_context):
        """Use Strands Agent + Syngenta KB for planting decisions."""
        agent = self._get_strands_agent()

        deficit_summary = nutrition_report.get("deficit_summary", "N/A")
        coverage = nutrition_report.get("coverage_score", 0)
        env_reasoning = environment_report.get("reasoning", "N/A")
        crisis_reasoning = crisis_report.get("reasoning", "N/A")

        crew_statuses = nutrition_report.get("crew_health_statuses", [])
        all_flags = []
        for s in crew_statuses:
            all_flags.extend(s.get("deficit_flags", []))
        unique_flags = list(set(all_flags))

        prompt = f"""You are the Planner Agent for a Mars greenhouse with 20 plots feeding 4 astronauts.

## Syngenta Knowledge Base Data
{kb_context}

## Current Mission Status
- Coverage score: {coverage:.1f}%
- Deficit summary: {deficit_summary}
- Active deficit flags: {unique_flags or 'none'}
- Environment: {env_reasoning}
- Crises: {crisis_reasoning}

## Available Crops
- potato: high kcal (770/kg), low vitamins, 120 Sol harvest cycle
- beans: high protein (90g/kg), high kcal (1470/kg), 65 Sol cycle
- lettuce: high vitamin A (7405/kg), vitamin K (1026/kg), 35 Sol cycle
- radish: moderate vitamin C (147/kg), 30 Sol cycle
- herbs: high vitamin A, C, K, 45 Sol cycle

## Baseline Allocation
potato 45%, beans 25%, lettuce 18%, radish 6%, herbs 6%

Based on the Syngenta KB data and current nutritional deficits, recommend an optimized allocation (must sum to ~100%). Reference KB data in your reasoning.

Respond in this exact JSON format:
{{
  "allocation": {{"potato": 0.45, "beans": 0.25, "lettuce": 0.18, "radish": 0.06, "herbs": 0.06}},
  "rationale": "Based on KB nutritional strategy: [specific reasoning referencing KB data]"
}}

Only return JSON."""

        response = agent(prompt)
        text = str(response).strip()
        parsed = self._parse_json(text)

        allocation = parsed.get("allocation", dict(BASELINE_ALLOCATION))
        rationale = parsed.get("rationale", "KB-grounded allocation.")

        # Validate allocation: must have all 5 crops, sum ≈ 1.0
        valid_crops = {"potato", "beans", "lettuce", "radish", "herbs"}
        if not all(c in allocation for c in valid_crops):
            allocation = dict(BASELINE_ALLOCATION)
            rationale = "LLM allocation invalid; using baseline. " + rationale

        # Normalize to sum to 1.0
        total = sum(allocation.values())
        if total > 0:
            allocation = {c: v / total for c, v in allocation.items()}

        plot_assignments = _allocation_to_plots(allocation)

        projected = min(100.0, (allocation.get("potato", 0) * 0.9 + allocation.get("beans", 0) * 0.7) * 0.40 + (allocation.get("beans", 0) * 0.9 + allocation.get("potato", 0) * 0.3) * 0.35 + 0.25) * 100

        return {
            "plot_assignments": plot_assignments,
            "rationale": rationale,
            "projected_coverage_score_next_sol": round(projected, 2),
        }

    def _plan_rules(self, nutrition_report, environment_report, crisis_report, kb_context, kb_fallback):
        """Fallback: rule-based allocation."""
        allocation = dict(BASELINE_ALLOCATION)

        crew_statuses = nutrition_report.get("crew_health_statuses", [])
        all_flags = []
        for s in crew_statuses:
            all_flags.extend(s.get("deficit_flags", []))

        rationale_parts = ["Baseline: 45% potato, 25% beans, 18% lettuce, 6% radish, 6% herbs."]

        has_protein = "protein_low" in all_flags
        has_kcal = "kcal_low" in all_flags

        if has_protein and has_kcal:
            allocation["beans"] += 0.05
            allocation["potato"] += 0.05
            allocation["lettuce"] -= 0.05
            allocation["radish"] -= 0.025
            allocation["herbs"] -= 0.025
            rationale_parts.append("Shifted +5pp to beans and potato for protein/kcal deficits.")
        elif has_protein:
            allocation["beans"] += 0.05
            allocation["potato"] -= 0.05
            rationale_parts.append("Shifted +5pp to beans for protein deficit.")
        elif has_kcal:
            allocation["potato"] += 0.05
            allocation["beans"] -= 0.05
            rationale_parts.append("Shifted +5pp to potato for kcal deficit.")
        else:
            rationale_parts.append("No deficits; maintaining baseline.")

        plot_assignments = _allocation_to_plots(allocation)
        projected = min(100.0, (allocation["potato"] * 0.9 + allocation["beans"] * 0.7) * 0.40 + (allocation["beans"] * 0.9 + allocation["potato"] * 0.3) * 0.35 + 0.25) * 100

        return {
            "plot_assignments": plot_assignments,
            "rationale": " ".join(rationale_parts),
            "projected_coverage_score_next_sol": round(projected, 2),
            "kb_fallback": kb_fallback,
            "kb_context": kb_context,
        }

    def _parse_json(self, text):
        text = text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        return {}
