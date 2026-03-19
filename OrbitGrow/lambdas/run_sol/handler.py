"""
run_sol Lambda handler — advances the simulation by one Sol.
"""
import os
import json
import uuid
import decimal
import logging
from datetime import datetime, timezone

import boto3

from simulation import (
    step1_mars_external_drift,
    step2_internal_sensor_drift,
    step3_cascade_effects,
    step4_crisis_roll,
    step5_crop_growth,
    step6_nutritional_output,
    step7_resource_consumption,
    compute_coverage_score,
)
from agents.orchestrator import OrchestratorAgent
from agents.mcp_client import MCPClient

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
WS_BROADCAST_FUNCTION = os.environ.get("WS_BROADCAST_FUNCTION", "OrbitGrow-WsBroadcast")

dynamodb = boto3.resource("dynamodb")
lambda_client = boto3.client("lambda")


def _to_decimal(obj):
    """Recursively convert floats to Decimal for DynamoDB."""
    if isinstance(obj, float):
        return decimal.Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_decimal(i) for i in obj]
    return obj


def _from_decimal(obj):
    """Recursively convert Decimal back to float for JSON serialization."""
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _from_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_from_decimal(i) for i in obj]
    return obj


def lambda_handler(event, context):
    current_sol = 0
    try:
        # --- Read current mission_state ---
        ms_table = dynamodb.Table(MISSION_STATE_TABLE)
        ms_resp = ms_table.scan(Limit=1)
        mission_state = _from_decimal(ms_resp["Items"][0]) if ms_resp.get("Items") else {
            "id": "MISSION",
            "current_sol": 0,
            "phase": "nominal",
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        current_sol = int(mission_state.get("current_sol", 0))
        prev_phase = mission_state.get("phase", "nominal")

        # --- Read all greenhouse_plots ---
        gp_table = dynamodb.Table(GREENHOUSE_PLOTS_TABLE)
        gp_resp = gp_table.scan()
        greenhouse_plots = [_from_decimal(item) for item in gp_resp.get("Items", [])]

        # --- Read latest environment_state ---
        env_table = dynamodb.Table(ENVIRONMENT_STATE_TABLE)
        env_resp = env_table.scan()
        env_items = sorted(
            [_from_decimal(i) for i in env_resp.get("Items", [])],
            key=lambda x: int(x.get("sol", 0)),
            reverse=True,
        )
        environment_state = env_items[0] if env_items else {
            "sol": current_sol,
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

        # --- Read latest nutrition_ledger for prev_crew_health ---
        nl_table = dynamodb.Table(NUTRITION_LEDGER_TABLE)
        nl_resp = nl_table.scan()
        nl_items = sorted(
            [_from_decimal(i) for i in nl_resp.get("Items", [])],
            key=lambda x: int(x.get("sol", 0)),
            reverse=True,
        )
        prev_nutrition_ledger = nl_items[0] if nl_items else {}

        # --- Read latest crew_health for current sol ---
        ch_table = dynamodb.Table(CREW_HEALTH_TABLE)
        ch_resp = ch_table.scan()
        crew_health_items = [
            _from_decimal(i) for i in ch_resp.get("Items", [])
            if int(i.get("sol", -1)) == current_sol
        ]
        prev_crew_health = crew_health_items if crew_health_items else None

        # --- Steps 1–7: Simulation ---
        env = step1_mars_external_drift(environment_state)
        env = step2_internal_sensor_drift(env)
        env, plots = step3_cascade_effects(env, greenhouse_plots)
        env, plots, crises_active = step4_crisis_roll(env, plots)
        plots, harvests = step5_crop_growth(plots, env, current_sol, MCPClient())
        nutrition_output = step6_nutritional_output(harvests, MCPClient())
        resource_consumption = step7_resource_consumption(plots, env)

        # --- Step 8: OrchestratorAgent ---
        mission_context = {
            "nutrition_ledger": nutrition_output,
            "environment_state": env,
            "crises_active": crises_active,
            "prev_crew_health": prev_crew_health,
        }
        orchestrator = OrchestratorAgent()
        daily_report = orchestrator.run(current_sol, mission_context)

        nutrition_report = daily_report.get("nutrition_report", {})
        crew_health_statuses = daily_report.get("crew_health_statuses", [])

        # Compute coverage_score
        micronutrient_composite = (
            nutrition_output.get("vitamin_a", 0)
            + nutrition_output.get("vitamin_c", 0)
            + nutrition_output.get("vitamin_k", 0)
            + nutrition_output.get("folate", 0)
        )
        micronutrient_target = 3600 + 400 + 480 + 1.6  # from design doc daily targets
        coverage_score = compute_coverage_score(
            nutrition_output.get("kcal", 0),
            nutrition_output.get("protein_g", 0),
            micronutrient_composite,
            micronutrient_target,
        )

        # --- Determine new phase ---
        new_sol = current_sol + 1
        if crises_active:
            new_phase = "crisis"
        elif prev_phase == "crisis" and not crises_active:
            new_phase = "recovery"
        else:
            new_phase = "nominal"

        now_iso = datetime.now(timezone.utc).isoformat()

        # --- Step 9: Write all records to DynamoDB ---

        # Update mission_state
        ms_table.put_item(Item=_to_decimal({
            **mission_state,
            "current_sol": new_sol,
            "phase": new_phase,
            "last_updated": now_iso,
        }))

        # Update all greenhouse_plots
        for plot in plots:
            gp_table.put_item(Item=_to_decimal({
                **plot,
                "id": plot.get("id", str(uuid.uuid4())),
            }))

        # Write new environment_state record
        new_env_id = str(uuid.uuid4())
        new_env_record = {**env, "id": new_env_id, "sol": new_sol}
        env_table.put_item(Item=_to_decimal(new_env_record))

        # Write nutrition_ledger record
        new_nl_id = str(uuid.uuid4())
        new_nl_record = {
            "id": new_nl_id,
            "sol": new_sol,
            "kcal": nutrition_output.get("kcal", 0.0),
            "protein_g": nutrition_output.get("protein_g", 0.0),
            "vitamin_a": nutrition_output.get("vitamin_a", 0.0),
            "vitamin_c": nutrition_output.get("vitamin_c", 0.0),
            "vitamin_k": nutrition_output.get("vitamin_k", 0.0),
            "folate": nutrition_output.get("folate", 0.0),
            "coverage_score": coverage_score,
        }
        nl_table.put_item(Item=_to_decimal(new_nl_record))

        # Write 4 crew_health records
        astronauts = ["commander", "scientist", "engineer", "pilot"]
        kcal_per_crew = nutrition_output.get("kcal", 0.0) / 4
        protein_per_crew = nutrition_output.get("protein_g", 0.0) / 4
        vitamin_a_per_crew = nutrition_output.get("vitamin_a", 0.0) / 4
        vitamin_c_per_crew = nutrition_output.get("vitamin_c", 0.0) / 4
        vitamin_k_per_crew = nutrition_output.get("vitamin_k", 0.0) / 4
        folate_per_crew = nutrition_output.get("folate", 0.0) / 4

        for i, astronaut in enumerate(astronauts):
            # Find matching crew health status from agent report
            status = next(
                (s for s in crew_health_statuses if s.get("astronaut") == astronaut),
                {}
            )
            prev_score = 100.0
            if prev_crew_health:
                prev_record = next(
                    (h for h in prev_crew_health if h.get("astronaut") == astronaut),
                    {}
                )
                prev_score = float(prev_record.get("health_score", 100.0))

            deficit_flags = status.get("deficit_flags", [])
            if not deficit_flags and coverage_score >= 80:
                new_health_score = min(100.0, prev_score + 1.0)
            else:
                new_health_score = max(0.0, prev_score - 2.0 * len(deficit_flags))

            ch_table.put_item(Item=_to_decimal({
                "id": str(uuid.uuid4()),
                "astronaut": astronaut,
                "sol": new_sol,
                "kcal_received": kcal_per_crew,
                "protein_g": protein_per_crew,
                "vitamin_a": vitamin_a_per_crew,
                "vitamin_c": vitamin_c_per_crew,
                "vitamin_k": vitamin_k_per_crew,
                "folate": folate_per_crew,
                "health_score": new_health_score,
                "deficit_flags": deficit_flags,
            }))

        # Write sol_report record
        sol_report_id = str(uuid.uuid4())
        sol_report = {
            "id": sol_report_id,
            "sol": new_sol,
            "nutrition_score": coverage_score,
            "kcal_produced": nutrition_output.get("kcal", 0.0),
            "protein_g": nutrition_output.get("protein_g", 0.0),
            "water_efficiency": resource_consumption.get("water_efficiency", 0.0),
            "energy_used": resource_consumption.get("energy_used", 0.0),
            "agent_decisions": json.dumps(daily_report),
            "crises_active": crises_active,
        }
        sr_table = dynamodb.Table(SOL_REPORTS_TABLE)
        sr_table.put_item(Item=_to_decimal(sol_report))

        # --- Invoke ws_broadcast asynchronously ---
        broadcast_payload = {
            "mission_state": {**mission_state, "current_sol": new_sol, "phase": new_phase},
            "environment_state": new_env_record,
            "nutrition_ledger": new_nl_record,
            "crises_active": crises_active,
        }
        try:
            lambda_client.invoke(
                FunctionName=WS_BROADCAST_FUNCTION,
                InvocationType="Event",
                Payload=json.dumps(broadcast_payload),
            )
        except Exception as broadcast_err:
            logger.warning("ws_broadcast invoke failed: %s", broadcast_err)

        # --- Return HTTP 200 ---
        response_body = {
            "mission_state": {**mission_state, "current_sol": new_sol, "phase": new_phase, "last_updated": now_iso},
            "environment_state": new_env_record,
            "nutrition_ledger": new_nl_record,
            "sol_reports": sol_report,
        }
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps(response_body),
        }

    except Exception as exc:
        logger.exception("run_sol failed at sol %d: %s", current_sol, exc)
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": str(exc), "sol": current_sol}),
        }
