"""
auto_sim Lambda — triggered by EventBridge every minute.
Loops internally to advance one Sol every SOL_INTERVAL_SECONDS (default 10s),
giving ~6 sols per minute without hitting EventBridge's 1-minute minimum.
"""
import os
import json
import time
import logging

import boto3

logger = logging.getLogger(__name__)

MISSION_STATE_TABLE = os.environ.get("MISSION_STATE_TABLE", "MissionState")
RUN_SOL_FUNCTION = os.environ.get("RUN_SOL_FUNCTION", "OrbitGrow-RunSol")
SOL_INTERVAL_SECONDS = int(os.environ.get("SOL_INTERVAL_SECONDS", "10"))
# How many sols to attempt per invocation (leave buffer before Lambda timeout)
SOLS_PER_TICK = int(os.environ.get("SOLS_PER_TICK", "5"))

dynamodb = boto3.resource("dynamodb")
lambda_client = boto3.client("lambda")


def _is_running():
    ms_resp = dynamodb.Table(MISSION_STATE_TABLE).scan(Limit=1)
    if not ms_resp.get("Items"):
        return False
    return bool(ms_resp["Items"][0].get("sim_running", False))


def lambda_handler(event, context):
    try:
        advanced = 0
        for i in range(SOLS_PER_TICK):
            if not _is_running():
                logger.info("sim_running=False, stopping after %d sols", advanced)
                break

            resp = lambda_client.invoke(
                FunctionName=RUN_SOL_FUNCTION,
                InvocationType="RequestResponse",
                Payload=json.dumps({}),
            )
            result = json.loads(resp["Payload"].read())
            status = result.get("statusCode", 500)
            logger.info("Sol %d advanced, status=%s", advanced + 1, status)
            advanced += 1

            # Sleep between sols (skip sleep after last iteration)
            if i < SOLS_PER_TICK - 1:
                time.sleep(SOL_INTERVAL_SECONDS)

        return {"statusCode": 200, "body": f"advanced {advanced} sols"}

    except Exception as exc:
        logger.exception("auto_sim failed: %s", exc)
        return {"statusCode": 500, "body": str(exc)}
