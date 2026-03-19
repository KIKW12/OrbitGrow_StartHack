"""
Vision Agent — interprets CV analysis results and provides KB-grounded
plant health recommendations, treatment plans, and mission impact assessments.

Two entry points:
  run()                     — called each Sol after CV batch analysis (Step 4.6)
  analyze_image_with_agent()— called on demand when a real image is uploaded
"""
import json
import logging

from agents.mcp_client import MCPClient

logger = logging.getLogger(__name__)

# Rule-based first-response actions per stress flag (always available, no LLM needed)
_FLAG_ACTIONS = {
    "disease": {
        "action": "isolate_and_treat",
        "description": "Isolate affected plot. Apply biological fungicide controls. Monitor adjacent plots daily for spread.",
        "priority": "high",
    },
    "water_stress": {
        "action": "increase_targeted_irrigation",
        "description": "Increase drip irrigation to this plot by 20%. Verify water recycling efficiency > 85%.",
        "priority": "medium",
    },
    "radiation_shielding": {
        "action": "deploy_radiation_shield",
        "description": "Activate plot-level radiation shielding panels. If health < 50% consider early harvest.",
        "priority": "high",
    },
    "nutrient_deficiency": {
        "action": "supplement_nutrients",
        "description": "Apply soluble nutrient supplement. Increase grow-light intensity by 10% for 3 Sols.",
        "priority": "medium",
    },
}

# Rough % of daily crew nutrition a single plot provides
_CROP_NUTRITION_IMPACT = {
    "potato": 12.0,
    "beans":  8.0,
    "lettuce": 4.0,
    "radish":  3.0,
    "herbs":   2.0,
}


class VisionAgent:
    def __init__(self, mcp: MCPClient = None):
        self.mcp = mcp or MCPClient()

    def _get_strands_agent(self):
        from strands import Agent
        from strands.models import BedrockModel
        return Agent(model=BedrockModel(
            model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            region_name="us-west-2",
        ))

    # ------------------------------------------------------------------
    # Sol-loop entry point
    # ------------------------------------------------------------------

    def run(self, sol: int, cv_results: dict, plots: list, env: dict) -> dict:
        """
        Called each Sol after batch CV analysis.  Identifies at-risk plots and
        returns KB-grounded recommendations for the Sol report.

        Returns:
          {
            "plots_at_risk":       list[dict],
            "recommended_actions": list[dict],
            "summary":             str,
            "detailed_reasoning":  str,
            "kb_fallback":         bool,
          }
        """
        if not cv_results:
            return {
                "plots_at_risk": [],
                "recommended_actions": [],
                "summary": "No CV data available this Sol.",
                "detailed_reasoning": "",
                "kb_fallback": True,
            }

        # 1. Triage — collect plots that need attention
        plots_at_risk = []
        for pid, result in cv_results.items():
            if result.get("kb_fallback"):
                continue
            health = result.get("health_score", 1.0)
            flags  = result.get("stress_flags", [])
            if health < 0.6 or flags:
                plot_ctx = next((p for p in plots if p["plot_id"] == pid), {})
                plots_at_risk.append({
                    "plot_id":     pid,
                    "crop":        plot_ctx.get("crop", "unknown"),
                    "health_score": round(health, 3),
                    "confidence":  result.get("confidence", 0.0),
                    "stress_flags": flags,
                    "cv_reasoning": result.get("cv_reasoning", ""),
                    "priority":    "high" if health < 0.4 or "disease" in flags else "medium",
                })

        # 2. Rule-based recommended actions (always available)
        recommended_actions = []
        seen = set()
        for at_risk in plots_at_risk:
            for flag in at_risk["stress_flags"]:
                key = f"{at_risk['plot_id']}:{flag}"
                if key not in seen and flag in _FLAG_ACTIONS:
                    seen.add(key)
                    recommended_actions.append({
                        "plot_id": at_risk["plot_id"],
                        "crop":    at_risk["crop"],
                        **_FLAG_ACTIONS[flag],
                    })
            if at_risk["health_score"] < 0.4:
                key = f"{at_risk['plot_id']}:critical"
                if key not in seen:
                    seen.add(key)
                    recommended_actions.append({
                        "plot_id": at_risk["plot_id"],
                        "crop":    at_risk["crop"],
                        "action":  "emergency_harvest",
                        "description": (
                            f"Health critically low ({at_risk['health_score']:.0%}). "
                            "Harvest immediately to salvage yield before total loss."
                        ),
                        "priority": "high",
                    })

        if not plots_at_risk:
            n = len(cv_results)
            return {
                "plots_at_risk": [],
                "recommended_actions": [],
                "summary": f"Sol {sol}: All {n} scanned plots healthy. No intervention needed.",
                "detailed_reasoning": "",
                "kb_fallback": False,
            }

        # 3. KB query for grounded reasoning
        all_flags = list({f for r in cv_results.values() for f in r.get("stress_flags", [])})
        kb = self.mcp.query_kb(
            f"plant health disease treatment water stress nutrient deficiency "
            f"Mars greenhouse {' '.join(all_flags)} crop recovery intervention",
            max_results=3,
        )
        kb_context  = "\n---\n".join(kb["chunks"]) if kb["chunks"] else ""
        kb_fallback = kb.get("kb_fallback", True)

        if kb_context and not kb_fallback:
            try:
                return self._reason_with_kb(
                    sol, plots_at_risk, recommended_actions, kb_context, env
                )
            except Exception as exc:
                logger.warning("VisionAgent sol-loop LLM failed: %s", exc)

        # Fallback summary
        n_high = sum(1 for p in plots_at_risk if p["priority"] == "high")
        summary = (
            f"Sol {sol}: {len(plots_at_risk)} plot(s) require attention "
            f"({n_high} high-priority). "
            f"Conditions: {', '.join(all_flags) or 'low health'}."
        )
        return {
            "plots_at_risk":       plots_at_risk,
            "recommended_actions": recommended_actions,
            "summary":             summary,
            "detailed_reasoning":  "",
            "kb_fallback":         kb_fallback,
        }

    def _reason_with_kb(self, sol, plots_at_risk, recommended_actions, kb_context, env):
        agent = self._get_strands_agent()
        risk_desc = "\n".join(
            f"- {p['plot_id']} ({p['crop']}): health {p['health_score']:.0%}, "
            f"flags={p['stress_flags'] or 'none'} — {p['cv_reasoning']}"
            for p in plots_at_risk
        )
        env_line = (
            f"temp={env.get('temperature_c','?')}°C  "
            f"humidity={env.get('humidity_pct','?')}%  "
            f"CO2={env.get('co2_ppm','?')}ppm  "
            f"light={env.get('light_umol','?')}µmol/m²/s"
        )
        prompt = f"""You are the Vision Agent for a Mars greenhouse supporting 4 astronauts.

## Syngenta Knowledge Base
{kb_context}

## Visual Analysis Results — Sol {sol}
{risk_desc}

## Current Environment
{env_line}

Respond ONLY in this JSON format:
{{
  "summary": "2-3 sentence overview of greenhouse visual health and priority actions",
  "detailed_reasoning": "KB-grounded explanation of detected conditions and recommended interventions"
}}"""
        response = agent(prompt)
        parsed   = self._parse_json(str(response))
        return {
            "plots_at_risk":       plots_at_risk,
            "recommended_actions": recommended_actions,
            "summary":             parsed.get("summary", ""),
            "detailed_reasoning":  parsed.get("detailed_reasoning", ""),
            "kb_fallback":         False,
        }

    # ------------------------------------------------------------------
    # On-demand entry point (real image upload)
    # ------------------------------------------------------------------

    def analyze_image_with_agent(
        self,
        cv_result: dict,
        plot: dict,
        env: dict,
        sol: int,
    ) -> dict:
        """
        Deep analysis of a single uploaded image.
        Returns a full health advisory with KB-grounded treatment plan and
        mission impact suitable for display in the frontend modal.

        Returns:
          {
            "health_assessment":  str,
            "immediate_actions":  list[dict],
            "treatment_plan":     str,
            "mission_impact":     str,
            "kb_grounded_advice": str,
            "confidence":         float,
            "kb_fallback":        bool,
          }
        """
        crop       = plot.get("crop", "unknown")
        health     = cv_result.get("health_score", 1.0)
        confidence = cv_result.get("confidence", 0.0)
        flags      = cv_result.get("stress_flags", [])
        reasoning  = cv_result.get("cv_reasoning", "")

        # Rule-based immediate actions (always computed as fallback)
        immediate_actions = []
        if health < 0.4:
            immediate_actions.append({
                "condition":   "critical_health",
                "action":      "emergency_harvest",
                "description": f"Health critically low ({health:.0%}). Harvest immediately to salvage yield.",
                "priority":    "high",
            })
        for flag in flags:
            if flag in _FLAG_ACTIONS:
                immediate_actions.append({"condition": flag, **_FLAG_ACTIONS[flag]})

        # KB query
        kb_query = (
            f"plant health treatment {' '.join(flags) or 'general care'} "
            f"{crop} Mars greenhouse recovery intervention"
        )
        kb = self.mcp.query_kb(kb_query, max_results=4)
        kb_context  = "\n---\n".join(kb["chunks"]) if kb["chunks"] else ""
        kb_fallback = kb.get("kb_fallback", True)

        if kb_context and not kb_fallback:
            try:
                return self._deep_analysis_with_kb(
                    cv_result, plot, env, sol, kb_context, immediate_actions
                )
            except Exception as exc:
                logger.warning("VisionAgent deep analysis failed: %s", exc)

        # Fallback: rule-based assessment
        if health >= 0.8:
            severity = "Excellent"
        elif health >= 0.6:
            severity = "Moderate stress detected"
        elif health >= 0.4:
            severity = "Significant stress — action required"
        else:
            severity = "Critical — immediate intervention needed"

        impact_pct = _CROP_NUTRITION_IMPACT.get(crop, 5.0)
        return {
            "health_assessment":  f"{severity}: {crop} at {health:.0%} health. {reasoning}",
            "immediate_actions":  immediate_actions,
            "treatment_plan":     "Apply standard care protocols per mission handbook. Re-scan after 3 Sols.",
            "mission_impact":     (
                f"This {crop} plot contributes ~{impact_pct:.0f}% of daily crew nutrition. "
                f"{'Failure would significantly impact food security.' if impact_pct >= 8 else 'Manageable if other plots remain healthy.'}"
            ),
            "kb_grounded_advice": "Knowledge base unavailable — using standard protocols.",
            "confidence":         confidence,
            "kb_fallback":        True,
        }

    def _deep_analysis_with_kb(self, cv_result, plot, env, sol, kb_context, immediate_actions):
        agent      = self._get_strands_agent()
        crop       = plot.get("crop", "unknown")
        health     = cv_result.get("health_score", 1.0)
        flags      = cv_result.get("stress_flags", [])
        reasoning  = cv_result.get("cv_reasoning", "")
        confidence = cv_result.get("confidence", 0.0)
        env_line   = (
            f"temp={env.get('temperature_c','?')}°C  "
            f"humidity={env.get('humidity_pct','?')}%  "
            f"CO2={env.get('co2_ppm','?')}ppm"
        )
        impact_pct = _CROP_NUTRITION_IMPACT.get(crop, 5.0)

        prompt = f"""You are the OrbitGrow Vision Agent — a plant health specialist for a Mars greenhouse.

## Syngenta Knowledge Base
{kb_context}

## Plant Image Analysis
- Crop: {crop}
- Sol: {sol}
- Health score: {health:.0%} (confidence: {confidence:.0%})
- Detected conditions: {flags or 'none'}
- Visual observation: {reasoning}
- Environment: {env_line}
- Mission context: This plot contributes ~{impact_pct:.0f}% of daily crew nutrition

Provide a comprehensive plant health advisory grounded in the Syngenta KB. Respond ONLY in JSON:
{{
  "health_assessment": "Clinical 2-3 sentence assessment of what you see and what it means for the crew",
  "immediate_actions": [
    {{"condition": "...", "action": "...", "description": "specific step the crew should take", "priority": "high|medium|low"}}
  ],
  "treatment_plan": "Step-by-step treatment sequence over the next 5-10 Sols",
  "mission_impact": "Concrete nutritional impact on the 4-person crew if this plot fails",
  "kb_grounded_advice": "Specific guidance from the Syngenta Knowledge Base relevant to these symptoms"
}}"""

        response = agent(prompt)
        parsed   = self._parse_json(str(response))

        # Use LLM actions if provided, otherwise keep rule-based
        llm_actions = parsed.get("immediate_actions", [])
        return {
            "health_assessment":  parsed.get("health_assessment", ""),
            "immediate_actions":  llm_actions if llm_actions else immediate_actions,
            "treatment_plan":     parsed.get("treatment_plan", ""),
            "mission_impact":     parsed.get("mission_impact", ""),
            "kb_grounded_advice": parsed.get("kb_grounded_advice", ""),
            "confidence":         confidence,
            "kb_fallback":        False,
        }

    @staticmethod
    def _parse_json(text: str) -> dict:
        text = text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        return {}
