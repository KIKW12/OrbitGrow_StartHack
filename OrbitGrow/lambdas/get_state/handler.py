"""
get_state Lambda — returns full current mission state in one call.
"""
import os
import json
import decimal
import logging

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
CREW_HEALTH_TABLE = os.environ.get("CREW_HEALTH_TABLE", "CrewHealth")
SOL_REPORTS_TABLE = os.environ.get("SOL_REPORTS_TABLE", "SolReport")

dynamodb = boto3.resource("dynamodb")


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
        # Mission state
        ms = dynamodb.Table(MISSION_STATE_TABLE).scan(Limit=1)
        mission_state = _from_decimal(ms["Items"][0]) if ms.get("Items") else {}
        current_sol = int(mission_state.get("current_sol", 0))

        # Latest environment
        env_items = sorted(
            [_from_decimal(i) for i in dynamodb.Table(ENVIRONMENT_STATE_TABLE).scan().get("Items", [])],
            key=lambda x: int(x.get("sol", 0)), reverse=True,
        )
        environment_state = env_items[0] if env_items else {}

        # Latest nutrition ledger
        nl_items = sorted(
            [_from_decimal(i) for i in dynamodb.Table(NUTRITION_LEDGER_TABLE).scan().get("Items", [])],
            key=lambda x: int(x.get("sol", 0)), reverse=True,
        )
        nutrition_ledger = nl_items[0] if nl_items else {}

        # All greenhouse plots
        plots = [_from_decimal(i) for i in dynamodb.Table(GREENHOUSE_PLOTS_TABLE).scan().get("Items", [])]

        # Crew health for current sol
        crew_health = [
            _from_decimal(i) for i in dynamodb.Table(CREW_HEALTH_TABLE).scan().get("Items", [])
            if int(i.get("sol", -1)) == current_sol
        ]

        # Last 30 sol reports for charts
        sr_items = sorted(
            [_from_decimal(i) for i in dynamodb.Table(SOL_REPORTS_TABLE).scan().get("Items", [])],
            key=lambda x: int(x.get("sol", 0)),
        )
        sol_history = sr_items[-30:]

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({
                "mission_state": mission_state,
                "environment_state": environment_state,
                "nutrition_ledger": nutrition_ledger,
                "greenhouse_plots": plots,
                "crew_health": crew_health,
                "sol_history": sol_history,
            }),
        }

    except Exception as exc:
        logger.exception("get_state failed: %s", exc)
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": str(exc)}),
        }
