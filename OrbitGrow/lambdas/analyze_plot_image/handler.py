"""
analyze_plot_image Lambda handler — on-demand CV scan of a greenhouse plot.

Reads the plot from DynamoDB, runs VisionService (Claude Vision via Bedrock),
writes the updated health / stress_flags back to GreenhousePlot, and returns
the analysis JSON.

On any failure the current simulation health is returned unchanged so the
frontend never sees an error for a non-critical operation.
"""
import os
import json
import logging
import decimal

import boto3

logger = logging.getLogger(__name__)

GREENHOUSE_PLOTS_TABLE  = os.environ.get("GREENHOUSE_PLOTS_TABLE", "GreenhousePlot")
ENVIRONMENT_STATE_TABLE = os.environ.get("ENVIRONMENT_STATE_TABLE", "EnvironmentState")

CORS_HEADERS = {
    "Access-Control-Allow-Origin":  "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Content-Type":                 "application/json",
}

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
        body    = json.loads(event.get("body") or "{}")
        plot_id = body.get("plot_id", "")

        if not plot_id:
            return {
                "statusCode": 400,
                "headers":    CORS_HEADERS,
                "body":       json.dumps({"error": "plot_id is required"}),
            }

        # --- Read plot from DynamoDB ---
        gp_table = dynamodb.Table(GREENHOUSE_PLOTS_TABLE)
        resp     = gp_table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr("plot_id").eq(plot_id)
        )
        items = resp.get("Items", [])
        if not items:
            return {
                "statusCode": 404,
                "headers":    CORS_HEADERS,
                "body":       json.dumps({"error": f"Plot '{plot_id}' not found"}),
            }
        plot = _from_decimal(items[0])

        # --- Read latest environment_state ---
        env_table = dynamodb.Table(ENVIRONMENT_STATE_TABLE)
        env_resp  = env_table.scan()
        env_items = sorted(
            [_from_decimal(i) for i in env_resp.get("Items", [])],
            key=lambda x: int(x.get("sol", 0)),
            reverse=True,
        )
        env = env_items[0] if env_items else {
            "temperature_c": 22.0, "humidity_pct": 65.0,
            "co2_ppm": 1200.0, "light_umol": 400.0,
        }

        # --- Run CV analysis ---
        from agents.vision_service import VisionService
        vs     = VisionService()
        result = vs.analyze_plot(plot, env)

        # --- Write updated plot back to DynamoDB ---
        if not result.get("kb_fallback", True):
            conf      = result.get("confidence", 0.0)
            cv_health = result.get("health_score", plot["health"])
            blend_weight  = min(conf, 0.7)
            updated_health = round(
                max(0.0, min(1.0, blend_weight * cv_health + (1 - blend_weight) * float(plot["health"]))),
                4,
            )
            existing   = set(plot.get("stress_flags", []))
            cv_flags   = set(result.get("stress_flags", []))
            plot.update({
                "health":               updated_health,
                "stress_flags":         list(existing | cv_flags),
                "last_cv_analysis_sol": plot.get("last_cv_analysis_sol", -1),
                "cv_confidence":        round(conf, 3),
            })
            gp_table.put_item(Item=_to_decimal(plot))

        return {
            "statusCode": 200,
            "headers":    CORS_HEADERS,
            "body":       json.dumps(result),
        }

    except Exception as exc:
        logger.exception("analyze_plot_image failed: %s", exc)
        return {
            "statusCode": 500,
            "headers":    CORS_HEADERS,
            "body":       json.dumps({"error": str(exc)}),
        }
