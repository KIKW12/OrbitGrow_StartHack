"""
Environment Agent — reads sensor state and adjusts greenhouse setpoints.
"""
from agents.mcp_client import MCPClient, STRUCTURED_DATA

_ENV = STRUCTURED_DATA["environment"]

INTERNAL_SENSORS = ["temperature_c", "humidity_pct", "co2_ppm", "light_umol"]

SENSOR_LABELS = {
    "temperature_c": "Temperature",
    "humidity_pct": "Humidity",
    "co2_ppm": "CO2",
    "light_umol": "Light",
}

SENSOR_ACTIONS = {
    "temperature_c": {
        "low": "Increase heating setpoint to {target:.1f}°C",
        "high": "Decrease cooling setpoint to {target:.1f}°C",
    },
    "humidity_pct": {
        "low": "Increase humidification to {target:.1f}%",
        "high": "Increase dehumidification to {target:.1f}%",
    },
    "co2_ppm": {
        "low": "Increase CO2 enrichment to {target:.0f} ppm",
        "high": "Activate CO2 scrubbers to reduce to {target:.0f} ppm",
    },
    "light_umol": {
        "low": "Increase LED photoperiod to {target:.0f} µmol/m²/s",
        "high": "Reduce LED intensity to {target:.0f} µmol/m²/s",
    },
}


class EnvironmentAgent:
    def __init__(self, mcp: MCPClient = None):
        self.mcp = mcp or MCPClient()

    def run(self, sol: int, environment_state: dict) -> dict:
        """
        Returns EnvironmentReport dict with keys:
        sensor_readings, setpoint_adjustments, reasoning, kb_fallback, kb_context
        """
        # Query KB for context text
        kb = self.mcp.query_kb(
            "optimal environmental bands temperature humidity CO2 light greenhouse Mars",
            max_results=2,
        )
        kb_context = "\n---\n".join(kb["chunks"]) if kb["chunks"] else ""

        optimal_bands = _ENV["optimal_bands"]

        # Check each internal sensor and build setpoint_adjustments
        sensor_readings = {s: environment_state.get(s) for s in INTERNAL_SENSORS}
        setpoint_adjustments = []

        for sensor in INTERNAL_SENSORS:
            val = environment_state.get(sensor)
            if val is None:
                continue
            band = optimal_bands.get(sensor)
            if not band:
                continue

            band_min = band["min"]
            band_max = band["max"]
            midpoint = (band_min + band_max) / 2

            if val < band_min:
                action = SENSOR_ACTIONS[sensor]["low"].format(target=midpoint)
                setpoint_adjustments.append({
                    "sensor": sensor,
                    "current": val,
                    "target": midpoint,
                    "action": action,
                })
            elif val > band_max:
                action = SENSOR_ACTIONS[sensor]["high"].format(target=midpoint)
                setpoint_adjustments.append({
                    "sensor": sensor,
                    "current": val,
                    "target": midpoint,
                    "action": action,
                })

        # Build reasoning string
        if setpoint_adjustments:
            parts = []
            for adj in setpoint_adjustments:
                label = SENSOR_LABELS.get(adj["sensor"], adj["sensor"])
                band = optimal_bands[adj["sensor"]]
                parts.append(
                    f"{label} is {adj['current']:.1f} (out of band [{band['min']}, "
                    f"{band['max']}]); adjusting to {adj['target']:.1f}."
                )
            reasoning = " ".join(parts)
        else:
            reasoning = (
                f"Sol {sol}: All internal sensors are within optimal bands. "
                "No setpoint adjustments required."
            )

        return {
            "sensor_readings": sensor_readings,
            "setpoint_adjustments": setpoint_adjustments,
            "reasoning": reasoning,
            "kb_fallback": kb.get("kb_fallback", False),
            "kb_context": kb_context,
        }
