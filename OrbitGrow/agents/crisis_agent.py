"""
Crisis Agent — applies KB playbooks to active crises.
Uses Syngenta KB data + Claude reasoning for containment decisions.
"""
import json
import logging

from agents.mcp_client import MCPClient, STRUCTURED_DATA

logger = logging.getLogger(__name__)

_CRISIS = STRUCTURED_DATA["crisis"]


class CrisisAgent:
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

    def run(self, sol: int, crises_active: list, active_crises_detail: dict = None) -> dict:
        """
        Returns CrisisReport with KB-grounded containment decisions.
        """
        if not crises_active:
            return {
                "crises_handled": [],
                "actions_taken": [],
                "recovery_timeline_sols": {},
                "reasoning": "No active crises.",
                "kb_fallback": False,
                "kb_context": "",
            }

        active_crises_detail = active_crises_detail or {}

        # 1. Query Syngenta MCP KB for crisis management guidance
        crisis_names = " ".join(c.replace("_", " ") for c in crises_active)
        kb = self.mcp.query_kb(
            f"crisis response containment recovery {crisis_names} greenhouse Mars "
            "system resilience operational scenarios emergency protocol",
            max_results=3,
        )
        kb_context = "\n---\n".join(kb["chunks"]) if kb["chunks"] else ""
        kb_fallback = kb.get("kb_fallback", True)

        # 2. Try LLM-grounded crisis response with KB data
        if kb_context and not kb_fallback:
            try:
                result = self._decide_with_kb(sol, crises_active, active_crises_detail, kb_context)
                result["kb_fallback"] = False
                result["kb_context"] = kb_context
                return result
            except Exception as exc:
                logger.warning("LLM crisis decision failed: %s — using playbook fallback", exc)

        # 3. Fallback: hardcoded playbooks
        return self._decide_playbooks(sol, crises_active, active_crises_detail, kb_context, kb_fallback)

    def _decide_with_kb(self, sol, crises_active, active_crises_detail, kb_context):
        """Use Strands Agent + Syngenta KB for crisis containment decisions."""
        agent = self._get_strands_agent()

        crises_desc = []
        for crisis in crises_active:
            detail = active_crises_detail.get(crisis, {})
            severity = detail.get("severity", 0.5)
            remaining = detail.get("recovery_sol", sol + 1) - sol
            crises_desc.append(f"- {crisis}: severity {severity:.0%}, {remaining} Sol(s) remaining")

        # Available containment actions the system can execute
        available_actions = [
            "reduce_irrigation_by_30pct", "activate_backup_water_reserve",
            "reduce_lighting_to_minimum", "lower_temperature_setpoint",
            "activate_cooling_system", "increase_ventilation",
            "isolate_affected_zone", "apply_biological_controls",
            "adjust_co2_scrubbers", "increase_plant_density",
        ]

        prompt = f"""You are the Crisis Agent for a Mars greenhouse feeding 4 astronauts.

## Syngenta Knowledge Base Data
{kb_context}

## Active Crises (Sol {sol})
{chr(10).join(crises_desc)}

## Available Containment Actions
{', '.join(available_actions)}

Based on the Syngenta KB data about system resilience and crisis scenarios, recommend containment actions for each active crisis. Reference specific KB recommendations.

Respond in this exact JSON format:
{{
  "crises_handled": ["crisis_type_1"],
  "actions_taken": ["action_1", "action_2"],
  "recovery_timeline_sols": {{"crisis_type_1": 3}},
  "reasoning": "Based on KB scenario guidance: [specific reasoning]"
}}

Only select actions from the available list. Only return JSON."""

        response = agent(prompt)
        text = str(response).strip()
        parsed = self._parse_json(text)

        # Validate: only allow known actions
        valid_actions = set(available_actions)
        actions = [a for a in parsed.get("actions_taken", []) if a in valid_actions]

        return {
            "crises_handled": parsed.get("crises_handled", crises_active),
            "actions_taken": actions,
            "recovery_timeline_sols": parsed.get("recovery_timeline_sols", {}),
            "reasoning": parsed.get("reasoning", "KB-grounded crisis response."),
        }

    def _decide_playbooks(self, sol, crises_active, active_crises_detail, kb_context, kb_fallback):
        """Fallback: hardcoded playbook logic."""
        playbooks = _CRISIS["playbooks"]
        crises_handled = []
        actions_taken = []
        recovery_timeline_sols = {}
        reasoning_parts = []

        for crisis in crises_active:
            playbook = playbooks.get(crisis)
            detail = active_crises_detail.get(crisis, {})
            severity = detail.get("severity", 0.5)
            remaining = detail.get("recovery_sol", sol + 1) - sol

            if not playbook:
                reasoning_parts.append(f"No playbook for '{crisis}'.")
                continue

            containment = playbook.get("containment", [])
            crises_handled.append(crisis)
            actions_taken.extend(containment)
            recovery_timeline_sols[crisis] = remaining

            reasoning_parts.append(
                f"Crisis '{crisis}' (severity {severity:.0%}, {remaining}d remaining): "
                f"applied [{', '.join(containment)}]."
            )

        return {
            "crises_handled": crises_handled,
            "actions_taken": actions_taken,
            "recovery_timeline_sols": recovery_timeline_sols,
            "reasoning": " ".join(reasoning_parts) or "All crises processed.",
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
