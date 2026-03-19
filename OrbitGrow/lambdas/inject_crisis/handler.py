"""
inject_crisis Lambda handler — manually injects a crisis into the current Sol.
"""
import os
import json
import decimal
import random
import logging
from datetime import datetime, timezone

import boto3

logger = logging.getLogger(__name__)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Content-Type": "application/json",
}

VALID_CRISIS_TYPES = [
    "water_recycling_failure",
    "energy_budget_cut",
    "temperature_spike",
    "disease_outbreak",
    "co2_imbalance",
]

MISSION_STATE_TABLE = os.environ.get("MISSION_STATE_TABLE", "MissionState")
GREENHOUSE_PLOTS_TABLE = os.environ.get("GREENHOUSE_PLOTS_TABLE", "GreenhousePlot")
ENVIRONMENT_STATE_TABLE = os.environ.get("ENVIRONMENT_STATE_TABLE", "EnvironmentState")
SOL_REPORTS_TABLE = os.environ.get("SOL_REPORTS_TABLE", "SolReport")

dynamodb = boto3.resource("dynamodb")


def _to_decimal(obj):
    if isinstance(obj, float):
        return decimal.Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_decimal(i) for i in obj]
    return obj


def _from_decimal(obj):
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _from_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_from_decimal(i) for i in obj]
    return obj


def lambda_handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
        crisis_type = body.get("type", "")

        if crisis_type not in VALID_CRISIS_TYPES:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({
                    "message": f"Invalid crisis type. Must be one of: {', '.join(VALID_CRISIS_TYPES)}"
                }),
            }

        # --- Read current environment_state ---
        env_table = dynamodb.Table(ENVIRONMENT_STATE_TABLE)
        env_resp = env_table.scan()
        env_items = sorted(
            [_from_decimal(i) for i in env_resp.get("Items", [])],
            key=lambda x: int(x.get("sol", 0)),
            reverse=True,
        )
        env = env_items[0] if env_items else {}

        # --- Read all greenhouse_plots ---
        gp_table = dynamodb.Table(GREENHOUSE_PLOTS_TABLE)
        gp_resp = gp_table.scan()
        plots = [_from_decimal(i) for i in gp_resp.get("Items", [])]

        # --- Apply crisis effects ---
        affected_plots = []

        if crisis_type == "water_recycling_failure":
            env["water_efficiency_pct"] = 65.0

        elif crisis_type == "energy_budget_cut":
            env["energy_used_pct"] = min(env.get("energy_used_pct", 60.0) + 40.0, 100.0)

        elif crisis_type == "temperature_spike":
            env["temperature_c"] = 30.0

        elif crisis_type == "disease_outbreak":
            zone = random.randint(0, 4)
            start = zone * 4
            end = start + 4
            for i in range(start, min(end, len(plots))):
                plots[i]["health"] = max(0.0, plots[i].get("health", 1.0) - 0.3)
                flags = list(plots[i].get("stress_flags", []))
                if "disease" not in flags:
                    flags.append("disease")
                plots[i]["stress_flags"] = flags
                affected_plots.append(plots[i])

        elif crisis_type == "co2_imbalance":
            env["co2_ppm"] = 1900.0

        # --- Update environment_state in DynamoDB ---
        if env.get("id"):
            env_table.put_item(Item=_to_decimal(env))

        # --- Update affected greenhouse_plots in DynamoDB ---
        for plot in affected_plots:
            gp_table.put_item(Item=_to_decimal(plot))

        # --- Update mission_state.phase to "crisis" ---
        ms_table = dynamodb.Table(MISSION_STATE_TABLE)
        ms_resp = ms_table.scan(Limit=1)
        mission_state = _from_decimal(ms_resp["Items"][0]) if ms_resp.get("Items") else {
            "id": "MISSION",
            "current_sol": 0,
            "phase": "nominal",
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        current_sol = int(mission_state.get("current_sol", 0))
        mission_state["phase"] = "crisis"
        mission_state["last_updated"] = datetime.now(timezone.utc).isoformat()
        ms_table.put_item(Item=_to_decimal(mission_state))

        # --- Update current sol's sol_report crises_active ---
        sr_table = dynamodb.Table(SOL_REPORTS_TABLE)
        sr_resp = sr_table.scan()
        sol_reports = [_from_decimal(i) for i in sr_resp.get("Items", [])]
        current_report = next(
            (r for r in sol_reports if int(r.get("sol", -1)) == current_sol),
            None,
        )
        if current_report:
            crises = list(current_report.get("crises_active", []))
            if crisis_type not in crises:
                crises.append(crisis_type)
            current_report["crises_active"] = crises
            sr_table.put_item(Item=_to_decimal(current_report))
        else:
            import uuid
            sr_table.put_item(Item=_to_decimal({
                "id": str(uuid.uuid4()),
                "sol": current_sol,
                "nutrition_score": 0.0,
                "kcal_produced": 0.0,
                "protein_g": 0.0,
                "water_efficiency": env.get("water_efficiency_pct", 92.0),
                "energy_used": env.get("energy_used_pct", 60.0),
                "agent_decisions": "{}",
                "crises_active": [crisis_type],
            }))

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({
                "injected_crisis": crisis_type,
                "mission_state": mission_state,
            }),
        }

    except Exception as exc:
        logger.exception("inject_crisis failed: %s", exc)
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": str(exc)}),
        }
