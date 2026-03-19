"""
ws_disconnect Lambda handler — removes WebSocket connection ID on $disconnect.
"""
import os
import json
import logging

import boto3

logger = logging.getLogger(__name__)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Content-Type": "application/json",
}

WS_CONNECTIONS_TABLE = os.environ.get("WS_CONNECTIONS_TABLE", "WsConnections")

dynamodb = boto3.resource("dynamodb")


def lambda_handler(event, context):
    try:
        connection_id = event["requestContext"]["connectionId"]

        table = dynamodb.Table(WS_CONNECTIONS_TABLE)
        table.delete_item(Key={"connection_id": connection_id})

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Disconnected"}),
        }

    except Exception as exc:
        logger.exception("ws_disconnect failed: %s", exc)
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": str(exc)}),
        }
