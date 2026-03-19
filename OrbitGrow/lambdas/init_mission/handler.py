"""
init_mission Lambda handler — seeds all Sol 0 state into DynamoDB.
Uses put_item with no condition expression so existing Sol 0 records are overwritten.
Does NOT delete records with sol > 0.
"""
import os
import json
import uuid
import decimal
import logging
from datetime import datetime, timezone

import boto3

logger = logging.getLogger(__name__)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Content-Type": "application/json",
}

MISSION_STATE_TABLE = os.environ.get("MISSION_STATE_TABLE", "MissionState")
GREENHOUSE_PLOTS_TABLE = os.environ.get("GREENHOUSE_PLOTS_TABLE", "GreenhousePlot")
ENVIRONMENT_STATE_TABLE = os.environ.get("ENVIRONMENT_STATE_TABLE", "EnvironmentState")
NUTRITION_LEDGER_TABLE = os.environ.get("NUTRITION_LEDGER_TABLE", "NutritionLedger")

dynamodb = boto3.resource("dynamodb")

# Initial stored food from Earth — 450-day mission, rations cover 80% of daily
# needs.  The greenhouse must supplement the remaining 20%+ to avoid depletion.
# Per KB doc 05: daily targets are 12000 kcal, 450g protein, etc.
# If greenhouse output drops, stored food depletes faster and may run out
# before mission end — creating real survival tension.
_INITIAL_RATIONS_SOLS = 360  # 450 days × 80% = 360 equivalent full-ration days
_DAILY_TARGETS = {
    "kcal": 12000, "protein_g": 450, "vitamin_a": 3600,
    "vitamin_c": 400, "vitamin_k": 480, "folate": 1.6,
}


def _to_decimal(obj):
    if isinstance(obj, float):
        return decimal.Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_decimal(i) for i in obj]
    return obj


# Harvest cycles in sols per crop type
_HARVEST_CYCLES = {
    "potato": 120,
    "beans": 65,
    "lettuce": 35,
    "radish": 30,
    "herbs": 45,
}

# Plot definitions: (plot_id, crop)
_PLOT_DEFINITIONS = (
    [("PLOT#A#{}".format(i), "potato") for i in range(1, 10)] +   # 9 potato
    [("PLOT#B#{}".format(i), "beans")  for i in range(1, 6)]  +   # 5 beans
    [("PLOT#C#{}".format(i), "lettuce") for i in range(1, 5)] +   # 4 lettuce
    [("PLOT#D#1", "radish")]                                    +   # 1 radish
    [("PLOT#E#1", "herbs")]                                         # 1 herbs
)


def _build_mission_state():
    return {
        "id": "MISSION",
        "current_sol": 0,
        "phase": "nominal",
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "active_crises": {},
    }


def _build_plots():
    plots = []
    for plot_id, crop in _PLOT_DEFINITIONS:
        harvest_cycle = _HARVEST_CYCLES[crop]
        plots.append({
            "id": str(uuid.uuid4()),
            "plot_id": plot_id,
            "crop": crop,
            "planted_sol": 0,
            "harvest_sol": harvest_cycle,  # planted_sol(0) + harvest_cycle
            "area_m2": 2.5,
            "health": 1.0,
            "stress_flags": [],
        })
    return plots


def _build_environment_state():
    return {
        "id": str(uuid.uuid4()),
        "sol": 0,
        "temperature_c": 22.0,
        "humidity_pct": 65.0,
        "co2_ppm": 1200.0,
        "light_umol": 400.0,
        "water_efficiency_pct": 92.0,
        "energy_used_pct": 60.0,
        "external_temp_c": -60.0,
        "dust_storm_index": 0.0,
        "radiation_msv": 0.3,
    }


def lambda_handler(event, context):
    try:
        ms_table = dynamodb.Table(MISSION_STATE_TABLE)
        gp_table = dynamodb.Table(GREENHOUSE_PLOTS_TABLE)
        env_table = dynamodb.Table(ENVIRONMENT_STATE_TABLE)
        nl_table = dynamodb.Table(NUTRITION_LEDGER_TABLE)

        # Task 8.1 — Write mission_state
        mission_state = _build_mission_state()
        ms_table.put_item(Item=_to_decimal(mission_state))

        # Task 8.2 — Write all 20 greenhouse_plots
        plots = _build_plots()
        for plot in plots:
            gp_table.put_item(Item=_to_decimal(plot))

        # Task 8.3 — Write Sol 0 environment_state
        env_state = _build_environment_state()
        env_table.put_item(Item=_to_decimal(env_state))

        # Task 8.4 — Write Sol 0 nutrition_ledger with initial food stockpile
        # Crew brought stored food from Earth (90 days of full rations).
        initial_storage = {
            f"storage_{k}": v * _INITIAL_RATIONS_SOLS
            for k, v in _DAILY_TARGETS.items()
        }
        nl_table.put_item(Item=_to_decimal({
            "id": str(uuid.uuid4()),
            "sol": 0,
            # Sol 0: no consumption yet
            "kcal": 0.0, "protein_g": 0.0, "vitamin_a": 0.0,
            "vitamin_c": 0.0, "vitamin_k": 0.0, "folate": 0.0,
            "coverage_score": 0.0,
            # Initial food stockpile from Earth
            **initial_storage,
        }))

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({
                "message": "Mission initialized",
                "sol": 0,
                "plots_seeded": 20,
                "initial_food_storage_sols": _INITIAL_RATIONS_SOLS,
            }),
        }

    except Exception as e:
        logger.exception("init_mission failed: %s", e)
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": str(e)}),
        }
