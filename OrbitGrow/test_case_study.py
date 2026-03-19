"""
OrbitGrow — CASE_STUDY.md End-to-End Test
Tests all 5 scenarios through the agent pipeline with live MCP KB.
"""
import sys, os, uuid, json, logging

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "agents"))

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(name)s] %(message)s")

from agents.mcp_client import MCPClient, STRUCTURED_DATA, HARDCODED_DEFAULTS
from agents.orchestrator import OrchestratorAgent
from agents.greenhouse_models import (
    build_initial_greenhouses, build_initial_mars_env,
    build_initial_facility_env, build_initial_astronauts,
)

# ── Helpers ──────────────────────────────────────────────────────────────────

def build_plots():
    harvest_cycles = {"potato": 120, "beans": 65, "lettuce": 35, "radish": 30, "herbs": 45}
    plots = []
    for crop, count in [("potato", 9), ("beans", 5), ("lettuce", 4), ("radish", 1), ("herbs", 1)]:
        for i in range(count):
            plots.append({
                "id": str(uuid.uuid4()),
                "plot_id": f"{crop}_{i+1}",
                "crop": crop,
                "planted_sol": 0,
                "harvest_sol": harvest_cycles[crop],
                "area_m2": 2.5,
                "health": 1.0,
                "stress_flags": [],
            })
    return plots

def build_context(sol, env_overrides=None, crises=None, crises_detail=None, plots=None):
    env = {
        "temperature_c": 22.0, "humidity_pct": 65.0, "co2_ppm": 1200.0,
        "light_umol": 400.0, "water_efficiency_pct": 92.0, "energy_used_pct": 60.0,
        "external_temp_c": -60.0, "dust_storm_index": 0.0, "radiation_msv": 0.3,
    }
    if env_overrides:
        env.update(env_overrides)
    return {
        "nutrition_ledger": {"coverage_score": 45, "sol": sol, "kcal": 6000, "protein_g": 200},
        "environment_state": env,
        "crises_active": crises or [],
        "active_crises_detail": crises_detail or {},
        "prev_crew_health": None,
        "plots": plots or build_plots(),
        "cv_results": {},
    }

def print_header(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")

def print_report(result):
    # Environment
    er = result.get("environment_report", {})
    adj = er.get("setpoint_adjustments", [])
    print(f"\n  [Environment Agent]")
    print(f"    Reasoning: {er.get('reasoning', 'N/A')[:200]}")
    if adj:
        for a in adj:
            print(f"    Adjustment: {a.get('sensor')} {a.get('current')} → {a.get('target')} | {a.get('action', '')[:80]}")
    else:
        print(f"    No adjustments needed")
    print(f"    KB fallback: {er.get('kb_fallback', 'N/A')}")

    # Crisis
    cr = result.get("crisis_report", {})
    print(f"\n  [Crisis Agent]")
    print(f"    Crises handled: {cr.get('crises_handled', [])}")
    print(f"    Actions: {cr.get('actions_taken', [])}")
    print(f"    Recovery: {cr.get('recovery_timeline_sols', {})}")
    print(f"    Reasoning: {cr.get('reasoning', 'N/A')[:200]}")
    print(f"    KB fallback: {cr.get('kb_fallback', 'N/A')}")

    # Planner
    pp = result.get("planting_plan", {})
    print(f"\n  [Planner Agent]")
    print(f"    Rationale: {pp.get('rationale', 'N/A')[:200]}")
    assignments = pp.get("plot_assignments", [])
    if assignments:
        crops = {}
        for a in assignments:
            c = a.get("crop", "unknown")
            crops[c] = crops.get(c, 0) + 1
        print(f"    Plot allocation: {crops}")
    print(f"    KB fallback: {pp.get('kb_fallback', 'N/A')}")

    # Nutrition
    nr = result.get("nutrition_report", {})
    print(f"\n  [Nutrition Agent]")
    print(f"    Coverage: {nr.get('coverage_score', 'N/A')}%")
    print(f"    Deficits: {nr.get('deficit_summary', 'N/A')[:150]}")
    print(f"    Crew emergency: {nr.get('crew_health_emergency', False)}")

    # Summary
    print(f"\n  [Mission Summary]")
    summary = result.get("mission_summary", "N/A")
    print(f"    {summary[:300]}")

# ── MCP Connection ───────────────────────────────────────────────────────────

print_header("Connecting to Syngenta MCP Knowledge Base")
mcp = MCPClient()
test = mcp.query_kb("test connection", max_results=1)
if test["kb_fallback"]:
    print("  WARNING: MCP KB unreachable — will use fallback data")
else:
    print(f"  MCP KB connected — got {len(test['chunks'])} chunk(s)")

orch = OrchestratorAgent(mcp=mcp)

# ── Scenario 0: Baseline (Sol 0) ────────────────────────────────────────────

print_header("SCENARIO 0 — Baseline (Sol 0)")
print("  Expected: All systems nominal, no crises, healthy baseline")

ctx = build_context(sol=0)
result = orch.run(sol=0, mission_context=ctx)
print_report(result)

# ── Scenario 1: Water Recycling Failure (Sol 42) ────────────────────────────

print_header("SCENARIO 1 — Water Recycling Failure (Sol 42)")
print("  Expected: Reduce irrigation 30%, activate backup, shift to lower water crops")

ctx = build_context(
    sol=42,
    env_overrides={
        "temperature_c": 22, "humidity_pct": 71, "co2_ppm": 1000,
        "light_umol": 300, "water_efficiency_pct": 60.0,
    },
    crises=["water_recycling_failure"],
    crises_detail={
        "water_recycling_failure": {
            "severity": 0.7,
            "recovery_sol": 45,
        }
    },
)
result = orch.run(sol=42, mission_context=ctx)
print_report(result)

# Verify expected actions
actions = result["crisis_report"].get("actions_taken", [])
print(f"\n  [VERIFY] reduce_irrigation_by_30pct in actions: {'reduce_irrigation_by_30pct' in actions}")
print(f"  [VERIFY] activate_backup_water_reserve in actions: {'activate_backup_water_reserve' in actions}")

# ── Scenario 2: Energy Budget Cut (Sol 98) ──────────────────────────────────

print_header("SCENARIO 2 — Energy Budget Cut (Sol 98)")
print("  Expected: Reduce LED, lower temp setpoint, suspend herb zone")

ctx = build_context(
    sol=98,
    env_overrides={
        "temperature_c": 22, "humidity_pct": 70, "co2_ppm": 1000,
        "light_umol": 190, "energy_used_pct": 95.0,
    },
    crises=["energy_budget_cut"],
    crises_detail={
        "energy_budget_cut": {
            "severity": 0.6,
            "recovery_sol": 100,
        }
    },
)
result = orch.run(sol=98, mission_context=ctx)
print_report(result)

actions = result["crisis_report"].get("actions_taken", [])
print(f"\n  [VERIFY] reduce_lighting_to_minimum in actions: {'reduce_lighting_to_minimum' in actions}")
print(f"  [VERIFY] lower_temperature_setpoint in actions: {'lower_temperature_setpoint' in actions}")

# ── Scenario 3: Temperature Spike (Sol 155) ─────────────────────────────────

print_header("SCENARIO 3 — Temperature Spike (Sol 155)")
print("  Expected: Activate cooling, increase ventilation, flag lettuce for harvest")

ctx = build_context(
    sol=155,
    env_overrides={
        "temperature_c": 31, "humidity_pct": 70, "co2_ppm": 1000,
        "light_umol": 300,
    },
    crises=["temperature_spike"],
    crises_detail={
        "temperature_spike": {
            "severity": 0.8,
            "recovery_sol": 156,
        }
    },
)
result = orch.run(sol=155, mission_context=ctx)
print_report(result)

actions = result["crisis_report"].get("actions_taken", [])
env_adj = result["environment_report"].get("setpoint_adjustments", [])
print(f"\n  [VERIFY] activate_cooling_system in actions: {'activate_cooling_system' in actions}")
print(f"  [VERIFY] increase_ventilation in actions: {'increase_ventilation' in actions}")
print(f"  [VERIFY] Temperature adjustment recommended: {any(a['sensor'] == 'temperature_c' for a in env_adj)}")

# ── Scenario 4: Disease Outbreak (Sol 210) ──────────────────────────────────

print_header("SCENARIO 4 — Disease Outbreak (Sol 210)")
print("  Expected: Isolate zone, reduce humidity, increase monitoring")

# Give bean plots disease stress
plots = build_plots()
for p in plots:
    if p["crop"] == "beans":
        p["health"] = 0.5
        p["stress_flags"] = ["disease"]

ctx = build_context(
    sol=210,
    env_overrides={
        "temperature_c": 22, "humidity_pct": 85, "co2_ppm": 1000,
        "light_umol": 300,
    },
    crises=["disease_outbreak"],
    crises_detail={
        "disease_outbreak": {
            "severity": 0.6,
            "recovery_sol": 217,
        }
    },
    plots=plots,
)
result = orch.run(sol=210, mission_context=ctx)
print_report(result)

actions = result["crisis_report"].get("actions_taken", [])
env_adj = result["environment_report"].get("setpoint_adjustments", [])
print(f"\n  [VERIFY] isolate_affected_zone in actions: {'isolate_affected_zone' in actions}")
print(f"  [VERIFY] apply_biological_controls in actions: {'apply_biological_controls' in actions}")
print(f"  [VERIFY] Humidity adjustment recommended: {any(a['sensor'] == 'humidity_pct' for a in env_adj)}")

# ── Summary ──────────────────────────────────────────────────────────────────

print_header("TEST SUMMARY")
print("  All 5 scenarios executed through the full agent pipeline.")
print("  Check [VERIFY] lines above for pass/fail on expected behaviors.")
print("  Done!")
