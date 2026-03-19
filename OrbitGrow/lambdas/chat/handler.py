"""
chat Lambda handler — natural language chat with mission context.
"""
import os
import json
import decimal
import logging
import threading

import boto3

from agents.orchestrator import OrchestratorAgent

logger = logging.getLogger(__name__)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Content-Type": "application/json",
}

MISSION_STATE_TABLE = os.environ.get("MISSION_STATE_TABLE", "MissionState")
SOL_REPORTS_TABLE = os.environ.get("SOL_REPORTS_TABLE", "SolReport")
NUTRITION_LEDGER_TABLE = os.environ.get("NUTRITION_LEDGER_TABLE", "NutritionLedger")
ENVIRONMENT_STATE_TABLE = os.environ.get("ENVIRONMENT_STATE_TABLE", "EnvironmentState")
CREW_HEALTH_TABLE = os.environ.get("CREW_HEALTH_TABLE", "CrewHealth")

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
        body = json.loads(event.get("body") or "{}")
        message = body.get("message", "")

        # Validate message length
        if not message or len(message) == 0 or len(message) > 2000:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": "Message must be between 1 and 2000 characters."}),
            }

        # --- Fetch mission_state ---
        ms_table = dynamodb.Table(MISSION_STATE_TABLE)
        ms_resp = ms_table.scan(Limit=1)
        mission_state = _from_decimal(ms_resp["Items"][0]) if ms_resp.get("Items") else {
            "current_sol": 0,
            "phase": "nominal",
        }
        current_sol = int(mission_state.get("current_sol", 0))

        # --- Fetch latest sol_report ---
        sr_table = dynamodb.Table(SOL_REPORTS_TABLE)
        sr_resp = sr_table.scan()
        sr_items = sorted(
            [_from_decimal(i) for i in sr_resp.get("Items", [])],
            key=lambda x: int(x.get("sol", 0)),
            reverse=True,
        )
        latest_sol_report = sr_items[0] if sr_items else {}

        # --- Fetch latest nutrition_ledger ---
        nl_table = dynamodb.Table(NUTRITION_LEDGER_TABLE)
        nl_resp = nl_table.scan()
        nl_items = sorted(
            [_from_decimal(i) for i in nl_resp.get("Items", [])],
            key=lambda x: int(x.get("sol", 0)),
            reverse=True,
        )
        nutrition_ledger = nl_items[0] if nl_items else {}

        # --- Fetch latest environment_state ---
        env_table = dynamodb.Table(ENVIRONMENT_STATE_TABLE)
        env_resp = env_table.scan()
        env_items = sorted(
            [_from_decimal(i) for i in env_resp.get("Items", [])],
            key=lambda x: int(x.get("sol", 0)),
            reverse=True,
        )
        environment_state = env_items[0] if env_items else {}

        # --- Fetch 4 crew_health records for current sol ---
        ch_table = dynamodb.Table(CREW_HEALTH_TABLE)
        ch_resp = ch_table.scan()
        crew_health = [
            _from_decimal(i) for i in ch_resp.get("Items", [])
            if int(i.get("sol", -1)) == current_sol
        ]

        # --- Build mission_context ---
        crises_active = latest_sol_report.get("crises_active", [])
        mission_context = {
            "sol": current_sol,
            "nutrition_ledger": nutrition_ledger,
            "environment_state": environment_state,
            "crises_active": crises_active,
            "sol_reports": latest_sol_report,
            "crew_health": crew_health,
        }

        # --- Invoke OrchestratorAgent with 30s timeout ---
        orchestrator = OrchestratorAgent()
        result = [None]
        error = [None]

        def run_agent():
            try:
                result[0] = orchestrator.chat(message, mission_context)
            except Exception as e:
                error[0] = e

        thread = threading.Thread(target=run_agent)
        thread.start()
        thread.join(timeout=30)

        if thread.is_alive():
            return {
                "statusCode": 503,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": "Agent request timed out"}),
            }

        if error[0] is not None:
            raise error[0]

        chat_result = result[0] or {"response": "", "reasoning": ""}

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({
                "response": chat_result.get("response", ""),
                "reasoning": chat_result.get("reasoning", ""),
            }),
        }

    except Exception as exc:
        logger.exception("chat failed: %s", exc)
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": str(exc)}),
        }
