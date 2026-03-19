"""
Environment Agent — reads sensor state, queries Syngenta KB for optimal bands,
and uses Claude (via Strands) to reason over KB data and recommend adjustments.
"""
import json
import logging

from agents.mcp_client import MCPClient, STRUCTURED_DATA

logger = logging.getLogger(__name__)

_ENV = STRUCTURED_DATA["environment"]

INTERNAL_SENSORS = ["temperature_c", "humidity_pct", "co2_ppm", "light_umol"]

SENSOR_LABELS = {
    "temperature_c": "Temperature (°C)",
    "humidity_pct": "Humidity (%)",
    "co2_ppm": "CO₂ (ppm)",
    "light_umol": "Light (µmol/m²/s)",
}


class EnvironmentAgent:
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

    def run(self, sol: int, environment_state: dict) -> dict:
        """
        Returns EnvironmentReport with KB-grounded reasoning and setpoint adjustments.
        """
        # 1. Query Syngenta MCP KB for real environmental guidance
        kb = self.mcp.query_kb(
            "optimal environmental conditions temperature humidity CO2 light "
            "greenhouse Mars crop growth stress thresholds",
            max_results=3,
        )
        kb_context = "\n---\n".join(kb["chunks"]) if kb["chunks"] else ""
        kb_fallback = kb.get("kb_fallback", True)

        sensor_readings = {s: environment_state.get(s) for s in INTERNAL_SENSORS}

        # 2. Try LLM-grounded decision-making with KB data
        if kb_context and not kb_fallback:
            try:
                result = self._decide_with_kb(sol, environment_state, sensor_readings, kb_context)
                result["kb_fallback"] = False
                result["kb_context"] = kb_context
                return result
            except Exception as exc:
                logger.warning("LLM environment decision failed: %s — using rule-based fallback", exc)

        # 3. Fallback: rule-based logic with hardcoded bands
        return self._decide_rules(sol, environment_state, sensor_readings, kb_context, kb_fallback)

    def _decide_with_kb(self, sol, environment_state, sensor_readings, kb_context):
        """Use Strands Agent + Syngenta KB to make environment decisions."""
        agent = self._get_strands_agent()

        prompt = f"""You are the Environment Agent for a Mars greenhouse feeding 4 astronauts.

## Syngenta Knowledge Base Data
{kb_context}

## Current Sensor Readings (Sol {sol})
- Temperature: {sensor_readings.get('temperature_c', 'N/A')}°C
- Humidity: {sensor_readings.get('humidity_pct', 'N/A')}%
- CO₂: {sensor_readings.get('co2_ppm', 'N/A')} ppm
- Light: {sensor_readings.get('light_umol', 'N/A')} µmol/m²/s
- Water efficiency: {environment_state.get('water_efficiency_pct', 'N/A')}%
- Energy used: {environment_state.get('energy_used_pct', 'N/A')}%
- External temp: {environment_state.get('external_temp_c', 'N/A')}°C
- Dust storm index: {environment_state.get('dust_storm_index', 'N/A')}
- Radiation: {environment_state.get('radiation_msv', 'N/A')} mSv

Based on the Syngenta KB data above, identify which sensors are out of optimal range and what adjustments are needed. Reference specific KB data points in your reasoning.

Respond in this exact JSON format:
{{
  "setpoint_adjustments": [
    {{"sensor": "temperature_c", "current": 28.5, "target": 22.0, "action": "Reduce temperature to 22°C — KB specifies optimal range 18-26°C for Mars crops"}},
  ],
  "reasoning": "Based on Syngenta KB document on Mars environmental constraints: [specific reasoning referencing KB data]"
}}

If all sensors are within optimal range per the KB, return an empty setpoint_adjustments array.
Only return the JSON, nothing else."""

        response = agent(prompt)
        text = str(response).strip()

        # Parse JSON from LLM response
        parsed = self._parse_json(text)

        adjustments = parsed.get("setpoint_adjustments", [])
        reasoning = parsed.get("reasoning", "KB-grounded analysis complete.")

        return {
            "sensor_readings": sensor_readings,
            "setpoint_adjustments": adjustments,
            "reasoning": reasoning,
        }

    def _decide_rules(self, sol, environment_state, sensor_readings, kb_context, kb_fallback):
        """Fallback: rule-based logic using hardcoded optimal bands."""
        optimal_bands = _ENV["optimal_bands"]
        setpoint_adjustments = []

        for sensor in INTERNAL_SENSORS:
            val = environment_state.get(sensor)
            if val is None:
                continue
            band = optimal_bands.get(sensor)
            if not band:
                continue

            midpoint = (band["min"] + band["max"]) / 2

            if val < band["min"]:
                setpoint_adjustments.append({
                    "sensor": sensor,
                    "current": val,
                    "target": midpoint,
                    "action": f"Increase {SENSOR_LABELS.get(sensor, sensor)} to {midpoint:.1f}",
                })
            elif val > band["max"]:
                setpoint_adjustments.append({
                    "sensor": sensor,
                    "current": val,
                    "target": midpoint,
                    "action": f"Decrease {SENSOR_LABELS.get(sensor, sensor)} to {midpoint:.1f}",
                })

        if setpoint_adjustments:
            parts = [f"{SENSOR_LABELS.get(a['sensor'], a['sensor'])} at {a['current']:.1f}, adjusting to {a['target']:.1f}" for a in setpoint_adjustments]
            reasoning = "Rule-based: " + "; ".join(parts) + "."
        else:
            reasoning = f"Sol {sol}: All sensors within optimal bands."

        return {
            "sensor_readings": sensor_readings,
            "setpoint_adjustments": setpoint_adjustments,
            "reasoning": reasoning,
            "kb_fallback": kb_fallback,
            "kb_context": kb_context,
        }

    def _parse_json(self, text):
        """Extract JSON from LLM response (handles markdown code blocks)."""
        text = text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        # Find first { to last }
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        return {}
