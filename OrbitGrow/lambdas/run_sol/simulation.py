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
# Task 4.5 — step4_crisis_roll  (PERSISTENT CRISES with severity)
#
# active_crises is a dict persisted across Sols:
#   { "water_recycling_failure": {"start_sol": 21, "recovery_sol": 24, "severity": 0.7}, ... }
#
# Each Sol:
#   1. Re-apply ongoing crisis effects (crises don't vanish after 1 Sol)
#   2. Roll for NEW crises (can't trigger a type that's already active)
#   3. Remove resolved crises (sol >= recovery_sol)
# ---------------------------------------------------------------------------

# severity range: (min, max) — randomly chosen on trigger
_CRISIS_DEFINITIONS = {
    "water_recycling_failure": {
        "probability": 0.008,
        "severity_range": (0.4, 1.0),
        "base_recovery_sols": 3,
    },
    "energy_budget_cut": {
        "probability": 0.005,
        "severity_range": (0.3, 0.8),
        "base_recovery_sols": 2,
    },
    "temperature_spike": {
        "probability": 0.012,
        "severity_range": (0.5, 1.0),
        "base_recovery_sols": 2,
    },
    "disease_outbreak": {
        "probability": 0.006,
        "severity_range": (0.3, 0.9),
        "base_recovery_sols": 5,
    },
    "co2_imbalance": {
        "probability": 0.009,
        "severity_range": (0.4, 0.8),
        "base_recovery_sols": 2,
    },
}


def _apply_crisis_effect(crisis_type: str, severity: float, env: dict, plots: list):
    """Apply the ongoing per-Sol effect of an active crisis."""
    if crisis_type == "water_recycling_failure":
        # Water efficiency drops proportional to severity
        target_eff = 92.0 - severity * 35.0  # range: 57–92%
        env["water_efficiency_pct"] = min(env["water_efficiency_pct"], target_eff)

    elif crisis_type == "energy_budget_cut":
        # Energy usage spikes proportional to severity
        spike = severity * 30.0  # up to +30%
        env["energy_used_pct"] = min(100, env["energy_used_pct"] + spike * 0.3)

    elif crisis_type == "temperature_spike":
        # Temperature pushed toward 30°C proportional to severity
        target_temp = 22.0 + severity * 10.0  # up to 32°C
        env["temperature_c"] = env["temperature_c"] + 0.3 * (target_temp - env["temperature_c"])

    elif crisis_type == "disease_outbreak":
        # Diseased plots keep losing health each Sol
        for plot in plots:
            if "disease" in plot.get("stress_flags", []):
                plot["health"] = max(0.0, plot["health"] - 0.03 * severity)

    elif crisis_type == "co2_imbalance":
        # CO2 pushed toward dangerous levels proportional to severity
        target_co2 = 1200 + severity * 800  # up to 2000
        env["co2_ppm"] = env["co2_ppm"] + 0.2 * (target_co2 - env["co2_ppm"])


def step4_crisis_roll(env: dict, plots: list, sol: int,
                      active_crises: dict = None) -> tuple:
    """
    Returns (env, plots, active_crises_dict, newly_triggered_list).
    active_crises persists across Sols. newly_triggered is the list of
    crisis types that fired THIS Sol (for the Crisis Agent to respond to).
    """
    env = dict(env)
    plots = [dict(p) for p in plots]
    active_crises = dict(active_crises or {})
    newly_triggered = []

    # 1. Apply ongoing effects of all active crises
    for crisis_type, info in list(active_crises.items()):
        _apply_crisis_effect(crisis_type, info["severity"], env, plots)

    # 2. Roll for NEW crises (skip types already active)
    for crisis_type, defn in _CRISIS_DEFINITIONS.items():
        if crisis_type in active_crises:
            continue
        if random.random() < defn["probability"]:
            severity = random.uniform(*defn["severity_range"])
            # Higher severity = longer recovery
            recovery_sols = max(1, round(defn["base_recovery_sols"] * (0.5 + severity)))
            active_crises[crisis_type] = {
                "start_sol": sol,
                "recovery_sol": sol + recovery_sols,
                "severity": round(severity, 2),
            }
            newly_triggered.append(crisis_type)

            # Apply immediate trigger effects
            if crisis_type == "disease_outbreak":
                zone = random.randint(0, 3)
                start_idx = zone * 5
                end_idx = start_idx + 5
                for i in range(start_idx, min(end_idx, len(plots))):
                    plots[i]["health"] = max(0.0, plots[i]["health"] - 0.3 * severity)
                    flags = list(plots[i].get("stress_flags", []))
                    if "disease" not in flags:
                        flags.append("disease")
                    plots[i]["stress_flags"] = flags

    # 3. Remove resolved crises
    resolved = [ct for ct, info in active_crises.items() if sol >= info["recovery_sol"]]
    for ct in resolved:
        del active_crises[ct]
        # Clean up disease flags when disease resolves
        if ct == "disease_outbreak":
            for plot in plots:
                flags = list(plot.get("stress_flags", []))
                if "disease" in flags:
                    flags.remove("disease")
                plot["stress_flags"] = flags

    return env, plots, active_crises, newly_triggered


# ---------------------------------------------------------------------------
# Task 4.6 — step5_crop_growth
# ---------------------------------------------------------------------------

def step5_crop_growth(plots: list, env: dict, sol: int, mcp,
                      planting_allocation: dict = None) -> tuple:
    """
    Advance crop growth by 1 Sol.  On harvest, replant using planting_allocation
    (from previous Sol's PlannerAgent) if available, otherwise replant same crop.
    """
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

            # Decide what to replant: use planner allocation or same crop
            new_crop = crop
            if planting_allocation:
                suggested = pick_replant_crop(plots, planting_allocation)
                if suggested and suggested in harvest_cycles_sol:
                    new_crop = suggested

            # Reset plot with new crop
            plot["crop"] = new_crop
            plot["planted_sol"] = sol
            plot["harvest_sol"] = sol + harvest_cycles_sol.get(new_crop, 30)
            plot["health"] = 1.0
            plot["stress_flags"] = []

    return plots, harvests


# ---------------------------------------------------------------------------
# Task 4.7 — step6_nutritional_output (stockpile model)
#
# Stored food from Earth provides kcal and protein but limited fresh vitamins.
# The greenhouse is the primary source of micronutrients (vitamins A, C, K,
# folate).  This creates meaningful coverage variation even while stored
# food lasts — the AI agents must optimize the greenhouse for micronutrients.
# ---------------------------------------------------------------------------

NUTRIENT_KEYS = ["kcal", "protein_g", "vitamin_a", "vitamin_c", "vitamin_k", "folate"]
_VITAMINS = ["vitamin_a", "vitamin_c", "vitamin_k", "folate"]

_DAILY_TARGETS = STRUCTURED_DATA["nutrition"]["daily_targets"]

# Aged (pre-packaged) food: max fraction of daily vitamin target it can provide.
# Supplements and fortified rations cover a baseline — greenhouse tops it up.
AGED_FOOD_COVERAGE = {
    "vitamin_a": 0.50,
    "vitamin_c": 0.35,  # degrades fastest in storage, but supplements help
    "vitamin_k": 0.45,
    "folate": 0.40,
}

# Fresh food decay: fraction lost per sol. Controls how long harvest vitamins
# stay "fresh" before degrading to aged storage.
# ~6%/sol → half-life ~11 sols → meaningful for ~25 sols after harvest
FRESH_DECAY_RATE = 0.06


def step6_nutritional_output(harvests: list, mcp, prev_food_storage: dict = None, sol: int = 0) -> dict:
    """
    Two-tier vitamin model:
      - FRESH: recently harvested greenhouse produce (100% bioavailable)
      - AGED:  pre-packaged or old stored food (capped bioavailability)

    Fresh vitamins decay each sol (produce wilts, vitamins oxidise).
    This creates natural oscillation: coverage spikes at harvest, declines between.
    """
    profiles = STRUCTURED_DATA["nutrition"]["nutritional_profiles"]
    prev = prev_food_storage or {}

    # Restore storage + fresh pools from previous sol
    storage = {k: prev.get(k, 0.0) for k in NUTRIENT_KEYS}
    fresh = {v: prev.get(f"_fresh_{v}", 0.0) for v in _VITAMINS}

    # Add harvest to both storage and fresh pool
    harvest_added = {k: 0.0 for k in NUTRIENT_KEYS}
    for harvest in harvests:
        crop = harvest["crop"]
        yield_kg = harvest["yield_kg"]
        profile = profiles.get(crop, {})
        for key in NUTRIENT_KEYS:
            amount = profile.get(f"{key}_per_kg", 0) * yield_kg
            storage[key] += amount
            harvest_added[key] += amount
            if key in _VITAMINS:
                fresh[key] += amount

    # Decay fresh pool each sol (produce degrades)
    for v in _VITAMINS:
        fresh[v] *= (1.0 - FRESH_DECAY_RATE)

    # --- Consumption ---
    daily_consumption = {}
    for key in NUTRIENT_KEYS:
        target = _DAILY_TARGETS.get(key, 0)
        if storage[key] <= 0:
            daily_consumption[key] = 0.0
            continue

        if key in ("kcal", "protein_g"):
            consumed = min(target, storage[key])
        elif key in _VITAMINS:
            # 1) Fresh food: full vitamin value
            avail_fresh = min(target, fresh[key])
            remaining = max(0.0, target - avail_fresh)

            # 2) Aged food: capped vitamin extraction
            aged_pool = max(0.0, storage[key] - fresh[key])
            base_cap = AGED_FOOD_COVERAGE.get(key, 0.2)
            # Aged vitamins also lose potency over mission time
            time_factor = max(0.30, 1.0 - sol * 0.0012)
            max_from_aged = base_cap * time_factor * target
            from_aged = min(remaining, max_from_aged, aged_pool)

            consumed = avail_fresh + from_aged

            # Deplete fresh pool by what was consumed from it
            fresh[key] = max(0.0, fresh[key] - avail_fresh)
        else:
            consumed = min(target, storage[key])

        daily_consumption[key] = consumed
        # Total storage depletes by daily target (unconsumed portion spoils/expires)
        storage[key] = max(0.0, storage[key] - min(target, storage[key]))

    # Ensure fresh never exceeds total storage
    for v in _VITAMINS:
        fresh[v] = min(fresh[v], max(0.0, storage[v]))

    # Persist fresh tracking inside the storage dict
    for v in _VITAMINS:
        storage[f"_fresh_{v}"] = fresh[v]

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
# Task 4.10 — apply_environment_adjustments
# ---------------------------------------------------------------------------

def apply_environment_adjustments(env: dict, environment_report: dict) -> dict:
    env = dict(env)
    for adj in environment_report.get("setpoint_adjustments", []):
        sensor = adj["sensor"]
        target = adj["target"]
        if sensor in env and env[sensor] is not None:
            current = env[sensor]
            env[sensor] = current + 0.5 * (target - current)
    return env


# ---------------------------------------------------------------------------
# Task 4.11 — apply_crisis_containment
# ---------------------------------------------------------------------------

_NOMINAL_VALUES = {
    "water_efficiency_pct": 92.0,
    "energy_used_pct": 60.0,
}

_CONTAINMENT_ACTIONS = {
    "reduce_irrigation_by_30pct": {},
    "activate_backup_water_reserve": {"water_efficiency_pct": ("restore", 10.0)},
    "reduce_lighting_to_minimum": {"light_umol": ("set", 300)},
    "lower_temperature_setpoint": {"temperature_c": ("set", 18)},
    "activate_cooling_system": {"temperature_c": ("move_toward", 22.0, 0.6)},
    "increase_ventilation": {"humidity_pct": ("move_toward", 65.0, 0.4),
                             "temperature_c": ("move_toward", 22.0, 0.3)},
    "adjust_co2_scrubbers": {"co2_ppm": ("move_toward", 1150.0, 0.5)},
    "increase_plant_density": {},
    "isolate_affected_zone": {},
    "apply_biological_controls": {"_plots_heal": 0.05},
}


def apply_crisis_containment(env: dict, plots: list, crisis_report: dict) -> tuple:
    env = dict(env)
    plots = [dict(p) for p in plots]

    for action_name in crisis_report.get("actions_taken", []):
        effects = _CONTAINMENT_ACTIONS.get(action_name, {})

        for key, spec in effects.items():
            if key == "_plots_heal":
                for plot in plots:
                    if "disease" in plot.get("stress_flags", []):
                        plot["health"] = min(1.0, plot["health"] + spec)
                continue

            if key not in env:
                continue

            if spec[0] == "set":
                env[key] = spec[1]
            elif spec[0] == "restore":
                nominal = _NOMINAL_VALUES.get(key, env[key])
                step = spec[1]
                if env[key] < nominal:
                    env[key] = min(nominal, env[key] + step)
                elif env[key] > nominal:
                    env[key] = max(nominal, env[key] - step)
            elif spec[0] == "move_toward":
                target = spec[1]
                factor = spec[2]
                env[key] = env[key] + factor * (target - env[key])

    return env, plots


# ---------------------------------------------------------------------------
# Task 4.12 — apply_planting_plan (on replant)
# ---------------------------------------------------------------------------

def pick_replant_crop(plots: list, planting_allocation: dict) -> str:
    if not planting_allocation:
        return None

    total = len(plots) or 1
    current_counts = {}
    for p in plots:
        c = p.get("crop", "potato")
        current_counts[c] = current_counts.get(c, 0) + 1

    biggest_deficit = -999
    best_crop = None
    for crop, target_frac in planting_allocation.items():
        target_count = target_frac * total
        actual_count = current_counts.get(crop, 0)
        deficit = target_count - actual_count
        if deficit > biggest_deficit:
            biggest_deficit = deficit
            best_crop = crop

    return best_crop


# ---------------------------------------------------------------------------
# Task 4.9 — compute_coverage_score
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
