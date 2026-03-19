"""
ws_connect Lambda handler — stores WebSocket connection ID on $connect.
"""
import os
import json
import logging
from datetime import datetime, timezone

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
        connected_at = datetime.now(timezone.utc).isoformat()

        table = dynamodb.Table(WS_CONNECTIONS_TABLE)
        table.put_item(Item={
            "connection_id": connection_id,
            "connected_at": connected_at,
        })

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Connected"}),
        }

    except Exception as exc:
        logger.exception("ws_connect failed: %s", exc)
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": str(exc)}),
        }
