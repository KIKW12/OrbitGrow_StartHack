"""
Simulation engine for OrbitGrow — executes Sol-by-Sol greenhouse state steps.
"""
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from agents.mcp_client import HARDCODED_DEFAULTS


# ---------------------------------------------------------------------------
# Task 4.1 — apply_drift
# ---------------------------------------------------------------------------

def apply_drift(current: float, drift_magnitude: float, hard_min: float, hard_max: float) -> float:
    return max(hard_min, min(hard_max, current + random.uniform(-drift_magnitude, drift_magnitude)))


# ---------------------------------------------------------------------------
# Task 4.2 — step1_mars_external_drift
# ---------------------------------------------------------------------------

def step1_mars_external_drift(env: dict) -> dict:
    env = dict(env)
    env["external_temp_c"] = apply_drift(env["external_temp_c"], 8, -125, 20)
    env["dust_storm_index"] = apply_drift(env["dust_storm_index"], 0.05, 0.0, 1.0)
    env["radiation_msv"] = apply_drift(env["radiation_msv"], 0.05, 0.1, 0.7)
    return env


# ---------------------------------------------------------------------------
# Task 4.3 — step2_internal_sensor_drift
# ---------------------------------------------------------------------------

def step2_internal_sensor_drift(env: dict) -> dict:
    env = dict(env)
    env["temperature_c"] = apply_drift(env["temperature_c"], 1.5, 10, 35)
    env["humidity_pct"] = apply_drift(env["humidity_pct"], 3, 30, 95)
    env["co2_ppm"] = apply_drift(env["co2_ppm"], 80, 400, 2000)
    env["light_umol"] = apply_drift(env["light_umol"], 20, 200, 600)
    env["water_efficiency_pct"] = apply_drift(env["water_efficiency_pct"], 1.5, 50, 99)
    env["energy_used_pct"] = apply_drift(env["energy_used_pct"], 2, 30, 100)
    return env


# ---------------------------------------------------------------------------
# Task 4.4 — step3_cascade_effects
# ---------------------------------------------------------------------------

def step3_cascade_effects(env: dict, plots: list) -> tuple:
    env = dict(env)
    plots = [dict(p) for p in plots]

    # Dust storm reduces light
    if env["dust_storm_index"] > 0.5:
        reduction = (env["dust_storm_index"] - 0.5) * 2 * env["light_umol"]
        env["light_umol"] = max(200, min(600, env["light_umol"] - reduction))

    # Cold external temp increases energy load
    if env["external_temp_c"] < -80:
        env["energy_used_pct"] = max(30, min(100, env["energy_used_pct"] + (-80 - env["external_temp_c"]) * 0.1))

    # High radiation damages unshielded plots
    if env["radiation_msv"] > 0.6:
        for plot in plots:
            if "radiation_shielding" not in plot.get("stress_flags", []):
                plot["health"] = max(0.0, min(1.0, plot["health"] - 0.02))

    return env, plots


# ---------------------------------------------------------------------------
# Task 4.5 — step4_crisis_roll
# ---------------------------------------------------------------------------

def step4_crisis_roll(env: dict, plots: list) -> tuple:
    env = dict(env)
    plots = [dict(p) for p in plots]
    crises_active = []

    if random.random() < 0.008:
        env["water_efficiency_pct"] = 65
        crises_active.append("water_recycling_failure")

    if random.random() < 0.005:
        env["energy_used_pct"] = min(env["energy_used_pct"] + 40, 100)
        crises_active.append("energy_budget_cut")

    if random.random() < 0.012:
        env["temperature_c"] = 30
        crises_active.append("temperature_spike")

    if random.random() < 0.006:
        zone = random.randint(0, 3)
        start = zone * 5
        end = start + 5
        for i in range(start, min(end, len(plots))):
            plots[i]["health"] = max(0.0, plots[i]["health"] - 0.3)
            flags = list(plots[i].get("stress_flags", []))
            if "disease" not in flags:
                flags.append("disease")
            plots[i]["stress_flags"] = flags
        crises_active.append("disease_outbreak")

    if random.random() < 0.009:
        env["co2_ppm"] = 1900
        crises_active.append("co2_imbalance")

    return env, plots, crises_active


# ---------------------------------------------------------------------------
# Task 4.6 — step5_crop_growth
# ---------------------------------------------------------------------------

def step5_crop_growth(plots: list, env: dict, sol: int, mcp) -> tuple:
    kb = mcp.query("04", "crop growth stress multipliers and base yields")
    defaults = HARDCODED_DEFAULTS["04"]

    stress_multipliers = kb.get("stress_multipliers", defaults["stress_multipliers"])
    base_yields_per_m2 = kb.get("base_yields_per_m2", defaults["base_yields_per_m2"])
    harvest_cycles_sol = kb.get("harvest_cycles_sol", defaults["harvest_cycles_sol"])
    optimal_bands = kb.get("optimal_bands", defaults["optimal_bands"])

    plots = [dict(p) for p in plots]
    harvests = []

    sensor_band_map = [
        ("temperature_c", "temperature_out_of_band"),
        ("humidity_pct", "humidity_out_of_band"),
        ("co2_ppm", "co2_out_of_band"),
        ("light_umol", "light_out_of_band"),
    ]

    for plot in plots:
        crop = plot["crop"]

        # Apply stress multipliers for out-of-band sensors
        for sensor_key, multiplier_key in sensor_band_map:
            band = optimal_bands.get(sensor_key)
            if band and (env[sensor_key] < band["min"] or env[sensor_key] > band["max"]):
                multiplier = stress_multipliers.get(multiplier_key, 1.0)
                plot["health"] = max(0.0, min(1.0, plot["health"] * multiplier))

        # Check for harvest
        if sol >= plot["harvest_sol"]:
            yield_kg = plot["area_m2"] * base_yields_per_m2.get(crop, 1.0) * plot["health"]
            harvests.append({
                "crop": crop,
                "yield_kg": yield_kg,
                "plot_id": plot.get("plot_id", plot.get("id", "")),
            })
            # Reset plot
            plot["planted_sol"] = sol
            plot["harvest_sol"] = sol + harvest_cycles_sol.get(crop, 30)
            plot["health"] = 1.0
            plot["stress_flags"] = []

    return plots, harvests


# ---------------------------------------------------------------------------
# Task 4.7 — step6_nutritional_output
# ---------------------------------------------------------------------------

def step6_nutritional_output(harvests: list, mcp) -> dict:
    zero = {
        "kcal": 0.0,
        "protein_g": 0.0,
        "vitamin_a": 0.0,
        "vitamin_c": 0.0,
        "vitamin_k": 0.0,
        "folate": 0.0,
    }

    if not harvests:
        return zero

    kb = mcp.query("03", "nutritional profiles per kg")
    defaults = HARDCODED_DEFAULTS["03"]
    profiles = kb.get("nutritional_profiles", defaults["nutritional_profiles"])

    totals = dict(zero)
    for harvest in harvests:
        crop = harvest["crop"]
        yield_kg = harvest["yield_kg"]
        profile = profiles.get(crop, {})
        totals["kcal"] += profile.get("kcal_per_kg", 0) * yield_kg
        totals["protein_g"] += profile.get("protein_g_per_kg", 0) * yield_kg
        totals["vitamin_a"] += profile.get("vitamin_a_per_kg", 0) * yield_kg
        totals["vitamin_c"] += profile.get("vitamin_c_per_kg", 0) * yield_kg
        totals["vitamin_k"] += profile.get("vitamin_k_per_kg", 0) * yield_kg
        totals["folate"] += profile.get("folate_per_kg", 0) * yield_kg

    return totals


# ---------------------------------------------------------------------------
# Task 4.8 — step7_resource_consumption
# ---------------------------------------------------------------------------

WATER_PER_M2_BY_CROP = {
    "potato": 2.5,
    "beans": 2.0,
    "lettuce": 3.0,
    "radish": 1.5,
    "herbs": 1.8,
}


def step7_resource_consumption(plots: list, env: dict) -> dict:
    water_efficiency = env["water_efficiency_pct"] / 100
    total_water = sum(
        plot["area_m2"] * WATER_PER_M2_BY_CROP.get(plot["crop"], 2.0)
        for plot in plots
    )
    total_water *= water_efficiency
    return {
        "water_used_l": total_water,
        "water_efficiency": env["water_efficiency_pct"],
        "energy_used": env["energy_used_pct"],
    }


# ---------------------------------------------------------------------------
# Task 4.9 — compute_coverage_score
# ---------------------------------------------------------------------------

def compute_coverage_score(kcal: float, protein_g: float, micronutrient_composite: float, target: float) -> float:
    score = ((kcal / 12000) * 0.40 + (protein_g / 450) * 0.35 + (micronutrient_composite / target) * 0.25) * 100
    return min(score, 100.0)
