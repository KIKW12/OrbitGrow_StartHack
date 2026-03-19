"""
sim_control Lambda — start/pause the auto simulation.
POST /sim-control  body: {"action": "start"|"pause"|"reset"}
"""
import os
import json
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
INIT_MISSION_FUNCTION = os.environ.get("INIT_MISSION_FUNCTION", "OrbitGrow-InitMission")

dynamodb = boto3.resource("dynamodb")
lambda_client = boto3.client("lambda")


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
        action = body.get("action", "")

        if action not in ("start", "pause", "reset"):
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": "action must be start, pause, or reset"}),
            }

        ms_table = dynamodb.Table(MISSION_STATE_TABLE)

        if action == "reset":
            # Re-init mission and set sim_running=False
            lambda_client.invoke(
                FunctionName=INIT_MISSION_FUNCTION,
                InvocationType="RequestResponse",
                Payload=json.dumps({}),
            )
            # Update sim_running flag after reset
            ms_resp = ms_table.scan(Limit=1)
            if ms_resp.get("Items"):
                state = _from_decimal(ms_resp["Items"][0])
                state["sim_running"] = False
                state["last_updated"] = datetime.now(timezone.utc).isoformat()
                ms_table.put_item(Item=_to_decimal(state))
            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps({"action": "reset", "sim_running": False}),
            }

        # start or pause
        ms_resp = ms_table.scan(Limit=1)
        if not ms_resp.get("Items"):
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": "No mission found. Call /init-mission first."}),
            }

        state = _from_decimal(ms_resp["Items"][0])
        state["sim_running"] = (action == "start")
        state["last_updated"] = datetime.now(timezone.utc).isoformat()
        ms_table.put_item(Item=_to_decimal(state))

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"action": action, "sim_running": state["sim_running"]}),
        }

    except Exception as exc:
        logger.exception("sim_control failed: %s", exc)
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": str(exc)}),
        }
