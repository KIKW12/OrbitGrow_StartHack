import os
import json
import decimal
import logging
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

WS_CONNECTIONS_TABLE = os.environ.get("WS_CONNECTIONS_TABLE", "WsConnections")
WEBSOCKET_API_ENDPOINT = os.environ.get("WEBSOCKET_API_ENDPOINT", "")

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
    # Task 7.1: Scan ws_connections table for all active connection IDs
    table = dynamodb.Table(WS_CONNECTIONS_TABLE)
    resp = table.scan()
    connections = resp.get("Items", [])

    # Build the broadcast payload from the event
    payload = {
        "mission_state": event.get("mission_state", {}),
        "environment_state": event.get("environment_state", {}),
        "nutrition_ledger": event.get("nutrition_ledger", {}),
        "crises_active": event.get("crises_active", []),
    }
    payload_str = json.dumps(_from_decimal(payload))

    # Task 7.2: Post to each connection via API Gateway Management API
    # Task 7.3: On GoneException, delete stale connection and continue

    if not WEBSOCKET_API_ENDPOINT:
        logger.warning("WEBSOCKET_API_ENDPOINT not set; skipping broadcast")
        return {"statusCode": 200, "body": "No endpoint configured"}

    apigw = boto3.client(
        "apigatewaymanagementapi",
        endpoint_url=WEBSOCKET_API_ENDPOINT,
    )

    stale_count = 0
    sent_count = 0

    for item in connections:
        connection_id = item.get("connection_id")
        if not connection_id:
            continue
        try:
            apigw.post_to_connection(
                ConnectionId=connection_id,
                Data=payload_str.encode("utf-8"),
            )
            sent_count += 1
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code in ("GoneException", "410"):
                # Task 7.3: Remove stale connection
                logger.info("Removing stale connection: %s", connection_id)
                table.delete_item(Key={"connection_id": connection_id})
                stale_count += 1
            else:
                logger.warning("Failed to post to connection %s: %s", connection_id, e)

    logger.info("Broadcast complete: sent=%d, stale_removed=%d", sent_count, stale_count)
    return {
        "statusCode": 200,
        "body": json.dumps({"sent": sent_count, "stale_removed": stale_count}),
    }
