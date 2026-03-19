"""
Simulation engine for OrbitGrow — executes Sol-by-Sol greenhouse state steps.
"""
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from agents.mcp_client import STRUCTURED_DATA, HARDCODED_DEFAULTS


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
# Task 4.7 — step6_nutritional_output (stockpile model)
#
# Harvested food goes into storage.  Each Sol the crew consumes their daily
# needs from storage.  "daily_consumption" is what the crew actually ate
# (capped by what's available).  "food_storage" is carried to the next Sol.
# ---------------------------------------------------------------------------

NUTRIENT_KEYS = ["kcal", "protein_g", "vitamin_a", "vitamin_c", "vitamin_k", "folate"]

# Daily targets — crew tries to consume this much per Sol
_DAILY_TARGETS = STRUCTURED_DATA["nutrition"]["daily_targets"]


def step6_nutritional_output(harvests: list, mcp, prev_food_storage: dict = None) -> dict:
    """
    Returns {
        "daily_consumption": {kcal, protein_g, ...},   # what crew ate this Sol
        "food_storage":      {kcal, protein_g, ...},   # remaining stockpile
        "harvest_added":     {kcal, protein_g, ...},   # what harvests contributed
    }
    """
    profiles = STRUCTURED_DATA["nutrition"]["nutritional_profiles"]

    # Start from previous storage (or zero)
    storage = {k: (prev_food_storage or {}).get(k, 0.0) for k in NUTRIENT_KEYS}

    # Add harvest nutrition to storage
    harvest_added = {k: 0.0 for k in NUTRIENT_KEYS}
    for harvest in harvests:
        crop = harvest["crop"]
        yield_kg = harvest["yield_kg"]
        profile = profiles.get(crop, {})
        for key in NUTRIENT_KEYS:
            amount = profile.get(f"{key}_per_kg", 0) * yield_kg
            storage[key] += amount
            harvest_added[key] += amount

    # Crew consumes daily targets (or whatever is available)
    daily_consumption = {}
    for key in NUTRIENT_KEYS:
        target = _DAILY_TARGETS.get(key, 0)
        consumed = min(target, storage[key])
        daily_consumption[key] = consumed
        storage[key] -= consumed

    return {
        "daily_consumption": daily_consumption,
        "food_storage": storage,
        "harvest_added": harvest_added,
    }


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
# Uses the canonical formula from nutrition_agent.py.
# ---------------------------------------------------------------------------

def compute_coverage_score(kcal: float, protein_g: float, vitamin_a: float,
                           vitamin_c: float, vitamin_k: float, folate: float) -> float:
    """
    Weighted coverage score (0–100).
    Each nutrient normalized to its daily target, then weighted:
      kcal 40%, protein 35%, micronutrients 25% (avg of 4 vitamins).
    """
    t = STRUCTURED_DATA["nutrition"]["daily_targets"]
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
