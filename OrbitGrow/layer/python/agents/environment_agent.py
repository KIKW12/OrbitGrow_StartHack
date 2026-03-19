"""
Environment Agent — reads sensor state and adjusts greenhouse setpoints.
"""
from agents.mcp_client import MCPClient, HARDCODED_DEFAULTS

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
        sensor_readings, setpoint_adjustments, reasoning, kb_fallback
        """
        # Step 1: Query MCP KB doc "04" for optimal_bands
        kb = self.mcp.query("04", "optimal environmental bands for greenhouse sensors")
        defaults = HARDCODED_DEFAULTS["04"]
        optimal_bands = kb.get("optimal_bands", defaults["optimal_bands"])

        # Step 2 & 3: Check each internal sensor and build setpoint_adjustments
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
                direction = "low"
                action_template = SENSOR_ACTIONS[sensor]["low"]
                action = action_template.format(target=midpoint)
                setpoint_adjustments.append({
                    "sensor": sensor,
                    "current": val,
                    "target": midpoint,
                    "action": action,
                })
            elif val > band_max:
                direction = "high"
                action_template = SENSOR_ACTIONS[sensor]["high"]
                action = action_template.format(target=midpoint)
                setpoint_adjustments.append({
                    "sensor": sensor,
                    "current": val,
                    "target": midpoint,
                    "action": action,
                })

        # Step 4: Build reasoning string
        if setpoint_adjustments:
            parts = []
            for adj in setpoint_adjustments:
                label = SENSOR_LABELS.get(adj["sensor"], adj["sensor"])
                parts.append(
                    f"{label} is {adj['current']:.1f} (out of band [{optimal_bands[adj['sensor']]['min']}, "
                    f"{optimal_bands[adj['sensor']]['max']}]); adjusting to {adj['target']:.1f}."
                )
            reasoning = " ".join(parts)
        else:
            # Step 5: All in band
            reasoning = (
                f"Sol {sol}: All internal sensors are within optimal bands. "
                "No setpoint adjustments required."
            )

        return {
            "sensor_readings": sensor_readings,
            "setpoint_adjustments": setpoint_adjustments,
            "reasoning": reasoning,
            "kb_fallback": kb.get("kb_fallback", False),
        }
