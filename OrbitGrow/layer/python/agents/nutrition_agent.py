"""
Nutrition Agent — computes nutritional coverage and per-astronaut health scores.
"""
from agents.mcp_client import MCPClient, HARDCODED_DEFAULTS
from simulation import compute_coverage_score

ASTRONAUTS = ["commander", "scientist", "engineer", "pilot"]


class NutritionAgent:
    def __init__(self, mcp: MCPClient = None, dynamodb=None):
        self.mcp = mcp or MCPClient()
        self.dynamodb = dynamodb  # boto3 DynamoDB resource, optional

    def run(self, sol: int, nutrition_ledger: dict, prev_crew_health: list = None) -> dict:
        """
        Returns NutritionReport dict with keys:
        coverage_score, kcal_produced, protein_g, crew_health_statuses,
        deficit_summary, crew_health_emergency
        """
        # Step 1: Query MCP KB doc "03" for daily_targets
        kb = self.mcp.query("03", "daily nutritional targets for crew")
        defaults = HARDCODED_DEFAULTS["03"]
        daily_targets = kb.get("daily_targets", defaults["daily_targets"])

        # Step 2: Get targets
        target_kcal = daily_targets.get("kcal", 12000)
        target_protein_g = daily_targets.get("protein_g", 450)
        target_vitamin_a = daily_targets.get("vitamin_a", 3600)
        target_vitamin_c = daily_targets.get("vitamin_c", 400)
        target_vitamin_k = daily_targets.get("vitamin_k", 480)
        target_folate = daily_targets.get("folate", 1.6)

        # Step 3: Compute micronutrient_composite (simple average normalized)
        kcal = nutrition_ledger.get("kcal", 0.0)
        protein_g = nutrition_ledger.get("protein_g", 0.0)
        vitamin_a = nutrition_ledger.get("vitamin_a", 0.0)
        vitamin_c = nutrition_ledger.get("vitamin_c", 0.0)
        vitamin_k = nutrition_ledger.get("vitamin_k", 0.0)
        folate = nutrition_ledger.get("folate", 0.0)

        # Normalize each micronutrient to its target, then average
        micronutrient_composite = (
            (vitamin_a / target_vitamin_a if target_vitamin_a else 0) +
            (vitamin_c / target_vitamin_c if target_vitamin_c else 0) +
            (vitamin_k / target_vitamin_k if target_vitamin_k else 0) +
            (folate * 1000 / (target_folate * 1000) if target_folate else 0)
        ) / 4 * 1000  # scale to match target=1000 in compute_coverage_score

        # Step 4: Compute coverage_score
        coverage_score = compute_coverage_score(kcal, protein_g, micronutrient_composite, target=1000)

        # Step 5: Per-astronaut health computation
        # Build prev health lookup
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
            astro_protein_g = protein_g / 4
            astro_vitamin_a = vitamin_a / 4
            astro_vitamin_c = vitamin_c / 4
            astro_vitamin_k = vitamin_k / 4
            astro_folate = folate / 4

            # Compute deficit flags
            deficit_flags = []
            if astro_kcal < target_kcal / 4:
                deficit_flags.append("kcal_low")
            if astro_protein_g < target_protein_g / 4:
                deficit_flags.append("protein_low")
            if astro_vitamin_a < target_vitamin_a / 4:
                deficit_flags.append("vitamin_a_low")
            if astro_vitamin_c < target_vitamin_c / 4:
                deficit_flags.append("vitamin_c_low")
            if astro_vitamin_k < target_vitamin_k / 4:
                deficit_flags.append("vitamin_k_low")
            if astro_folate < (target_folate / 4):
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
                "protein_g": astro_protein_g,
                "vitamin_a": astro_vitamin_a,
                "vitamin_c": astro_vitamin_c,
                "vitamin_k": astro_vitamin_k,
                "folate": astro_folate,
                "health_score": health_score,
                "deficit_flags": deficit_flags,
            })

        # Build deficit summary
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
        }
