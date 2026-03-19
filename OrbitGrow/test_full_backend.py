"""
Full backend integration test — runs the complete OrbitGrow pipeline locally.
Real MCP KB queries, all 5 agents, simulation engine, stockpile model.
No DynamoDB or AWS required.

Usage:
    python test_full_backend.py              # 10 Sols, quick check
    python test_full_backend.py --sols 50    # 50 Sols
    python test_full_backend.py --sols 450   # full mission (slow — many MCP calls)
    python test_full_backend.py --no-mcp     # skip live MCP, use hardcoded data
"""
import sys
import os
import uuid
import random
import argparse
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "agents"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lambdas", "run_sol"))

from simulation import (
    step1_mars_external_drift,
    step2_internal_sensor_drift,
    step3_cascade_effects,
    step4_crisis_roll,
    step5_crop_growth,
    step6_nutritional_output,
    step7_resource_consumption,
    compute_coverage_score,
    apply_environment_adjustments,
    apply_crisis_containment,
)
from agents.mcp_client import MCPClient, STRUCTURED_DATA, HARDCODED_DEFAULTS
from agents.nutrition_agent import NutritionAgent
from agents.environment_agent import EnvironmentAgent
from agents.crisis_agent import CrisisAgent
from agents.planner_agent import PlannerAgent
from agents.orchestrator import OrchestratorAgent


class MockMCP:
    """Offline MCP client — uses hardcoded data only."""
    def query(self, doc_id, q):
        return {**HARDCODED_DEFAULTS.get(doc_id, {}), "kb_fallback": True}
    def query_kb(self, q, max_results=5):
        return {"chunks": [], "kb_fallback": True}
    def get_structured(self, domain):
        return STRUCTURED_DATA.get(domain, {})


def build_initial_state():
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

    env = {
        "temperature_c": 22.0, "humidity_pct": 65.0, "co2_ppm": 1200.0,
        "light_umol": 400.0, "water_efficiency_pct": 92.0, "energy_used_pct": 60.0,
        "external_temp_c": -60.0, "dust_storm_index": 0.0, "radiation_msv": 0.3,
    }

    daily_targets = {"kcal": 12000, "protein_g": 450, "vitamin_a": 3600,
                     "vitamin_c": 400, "vitamin_k": 480, "folate": 1.6}
    food_storage = {k: v * 360 for k, v in daily_targets.items()}

    return env, plots, food_storage


def run_mission(num_sols, use_mcp, seed=42):
    random.seed(seed)

    if use_mcp:
        print("Connecting to Syngenta MCP Knowledge Base...")
        mcp = MCPClient()
        # Test connection
        test = mcp.query_kb("test connection", max_results=1)
        if test["kb_fallback"]:
            print("WARNING: MCP KB unreachable, falling back to hardcoded data")
        else:
            print(f"MCP KB connected — got {len(test['chunks'])} chunks\n")
    else:
        print("Using offline mode (hardcoded data)\n")
        mcp = MockMCP()

    env, plots, food_storage = build_initial_state()
    planting_allocation = None
    prev_crew_health = None
    active_crises = {}
    phase = "nominal"

    na = NutritionAgent(mcp=mcp)
    ea = EnvironmentAgent(mcp=mcp)
    ca = CrisisAgent(mcp=mcp)
    pa = PlannerAgent(mcp=mcp)

    # Header
    print(f"{'Sol':>3} | {'Phase':>8} | {'Score':>6} | {'Kcal Eaten':>10} | {'Storage':>8} | {'Temp':>5} | {'CO2':>6} | {'Water%':>6} | {'Harvests':>8} | Crises / Agent Actions")
    print("-" * 130)

    all_crises = []
    deficit_sols = 0
    sol_times = []

    for sol in range(1, num_sols + 1):
        t0 = time.time()

        # --- Simulation Steps 1-4 ---
        env = step1_mars_external_drift(env)
        env = step2_internal_sensor_drift(env)
        env, plots = step3_cascade_effects(env, plots)
        env, plots, active_crises, newly_triggered = step4_crisis_roll(env, plots, sol, active_crises)
        crises_active = list(active_crises.keys())

        # --- Step 5: Crop growth (uses previous planner allocation) ---
        plots, harvests = step5_crop_growth(plots, env, sol, mcp, planting_allocation)

        # --- Step 6: Nutrition (stockpile model) ---
        nutrition_result = step6_nutritional_output(harvests, mcp, food_storage)
        daily = nutrition_result["daily_consumption"]
        food_storage = nutrition_result["food_storage"]
        harvest_added = nutrition_result["harvest_added"]

        # --- Step 7: Resources ---
        resources = step7_resource_consumption(plots, env)

        # --- Step 8: Run all agents ---
        nr = na.run(sol, daily, prev_crew_health)
        er = ea.run(sol, env)
        cr = ca.run(sol, crises_active, active_crises_detail=active_crises)
        pp = pa.run(nr, er, cr)

        # --- Step 8b: APPLY agent decisions ---
        env = apply_environment_adjustments(env, er)
        env, plots = apply_crisis_containment(env, plots, cr)

        # Store planner allocation for next Sol
        assignments = pp.get("plot_assignments", [])
        if assignments:
            counts = {}
            for a in assignments:
                c = a.get("crop", "potato")
                counts[c] = counts.get(c, 0) + 1
            total = sum(counts.values()) or 1
            planting_allocation = {c: n / total for c, n in counts.items()}

        # Update crew health for next Sol
        prev_crew_health = nr.get("crew_health_statuses", [])

        # Compute coverage score
        score = compute_coverage_score(
            daily["kcal"], daily["protein_g"], daily["vitamin_a"],
            daily["vitamin_c"], daily["vitamin_k"], daily["folate"]
        )

        # Phase transitions
        if crises_active:
            phase = "crisis"
        elif phase == "crisis" and not crises_active:
            phase = "recovery"
        elif phase == "recovery":
            phase = "nominal"

        if daily["kcal"] < 12000:
            deficit_sols += 1

        if crises_active:
            all_crises.extend(crises_active)

        elapsed = time.time() - t0
        sol_times.append(elapsed)

        # --- Print ---
        storage_days = food_storage["kcal"] / 12000
        actions_str = ""
        if crises_active:
            severity_strs = []
            for c in crises_active:
                sev = active_crises.get(c, {}).get("severity", 0)
                remaining = active_crises.get(c, {}).get("recovery_sol", sol) - sol
                severity_strs.append(f"{c}({sev:.0%},{remaining}d)")
            actions_str += f"CRISIS: {', '.join(severity_strs)}"
        if er.get("setpoint_adjustments"):
            sensors = [a["sensor"] for a in er["setpoint_adjustments"]]
            actions_str += f"  ENV: {', '.join(sensors)}"
        if cr.get("actions_taken"):
            actions_str += f"  FIX: {', '.join(cr['actions_taken'][:2])}"

        # Print every Sol for short runs, every 10 for medium, every 25 for long
        interval = 1 if num_sols <= 20 else (10 if num_sols <= 100 else 25)
        if sol % interval == 0 or sol == 1 or crises_active or (harvest_added["kcal"] > 0 and sol <= 45):
            print(
                f"{sol:3d} | {phase:>8} | {score:5.1f}% | {daily['kcal']:10.0f} | "
                f"{storage_days:6.1f}d | {env['temperature_c']:5.1f} | {env['co2_ppm']:6.0f} | "
                f"{env['water_efficiency_pct']:5.1f}% | {len(harvests):2d} crops | {actions_str}"
            )

    # --- Summary ---
    print("\n" + "=" * 130)
    print(f"MISSION COMPLETE — {num_sols} Sols")
    print("=" * 130)

    print(f"\nNutrition:")
    print(f"  Deficit Sols (partial food): {deficit_sols}/{num_sols}")
    print(f"  Final food storage: {food_storage['kcal']/12000:.0f} days kcal, {food_storage['protein_g']/450:.0f} days protein")

    print(f"\nCrises:")
    from collections import Counter
    crisis_counts = Counter(all_crises)
    if crisis_counts:
        for c, n in crisis_counts.most_common():
            print(f"  {c}: {n}x")
    else:
        print("  None occurred")

    print(f"\nCrop distribution (end):")
    crop_counts = {}
    for p in plots:
        crop_counts[p["crop"]] = crop_counts.get(p["crop"], 0) + 1
    for c, n in sorted(crop_counts.items(), key=lambda x: -x[1]):
        print(f"  {c}: {n} plots ({n/20*100:.0f}%)")

    print(f"\nCrew health (end):")
    if prev_crew_health:
        for ch in prev_crew_health:
            flags = ch.get("deficit_flags", [])
            flag_str = ", ".join(flags) if flags else "none"
            print(f"  {ch['astronaut']}: {ch['health_score']:.0f}/100  deficits: {flag_str}")

    print(f"\nEnvironment (end):")
    print(f"  Temp: {env['temperature_c']:.1f}°C  Humidity: {env['humidity_pct']:.1f}%  "
          f"CO2: {env['co2_ppm']:.0f} ppm  Light: {env['light_umol']:.0f} µmol")
    print(f"  Water eff: {env['water_efficiency_pct']:.1f}%  Energy: {env['energy_used_pct']:.1f}%")

    print(f"\nMCP KB: {'LIVE (Syngenta)' if use_mcp and not isinstance(mcp, MockMCP) else 'Offline (hardcoded)'}")
    print(f"  KB fallback used: {nr.get('kb_fallback', 'N/A')}")

    avg_time = sum(sol_times) / len(sol_times)
    print(f"\nPerformance: {avg_time:.2f}s avg/Sol ({avg_time * num_sols:.1f}s total)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OrbitGrow full backend test")
    parser.add_argument("--sols", type=int, default=10, help="Number of Sols to simulate (default: 10)")
    parser.add_argument("--no-mcp", action="store_true", help="Skip live MCP KB, use hardcoded data")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    args = parser.parse_args()

    run_mission(args.sols, use_mcp=not args.no_mcp, seed=args.seed)
