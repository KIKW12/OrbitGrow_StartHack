"""
OrbitGrow local development server — FastAPI + WebSocket.
Runs the full simulation pipeline locally (no AWS needed).
Connects to the Syngenta MCP Knowledge Base for real KB-grounded agent decisions.

Usage:
    python local_server.py              # Live MCP (Syngenta KB)
    python local_server.py --offline    # Skip MCP, use hardcoded data
"""
import sys
import os
import uuid
import random
import asyncio
import json
import logging
import argparse

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

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

logger = logging.getLogger("orbitgrow")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

MISSION_DURATION = 450

# Will be set from CLI args before server starts
USE_MCP = True
MCP_CONNECTED = False

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class MockMCP:
    """Offline fallback — uses hardcoded structured data only."""
    def query(self, doc_id, q):
        return {**HARDCODED_DEFAULTS.get(doc_id, {}), "kb_fallback": True}
    def query_kb(self, q, max_results=5):
        return {"chunks": [], "kb_fallback": True}
    def get_structured(self, domain):
        return STRUCTURED_DATA.get(domain, {})


def create_mcp_client():
    """Create the MCP client — real Syngenta KB or offline fallback."""
    global MCP_CONNECTED
    if not USE_MCP:
        logger.info("Offline mode — using hardcoded data (no MCP)")
        MCP_CONNECTED = False
        return MockMCP()

    logger.info("Connecting to Syngenta MCP Knowledge Base...")
    mcp = MCPClient()
    try:
        test = mcp.query_kb("test connection", max_results=1)
        if test["kb_fallback"]:
            logger.warning("MCP KB unreachable — falling back to hardcoded data")
            MCP_CONNECTED = False
        else:
            logger.info("MCP KB connected — got %d chunks", len(test["chunks"]))
            MCP_CONNECTED = True
    except Exception as e:
        logger.warning("MCP connection test failed: %s — using fallback", e)
        MCP_CONNECTED = False
    return mcp


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


class GameState:
    def __init__(self):
        self.mcp = create_mcp_client()
        self.reset()

    def reset(self):
        env, plots, food = build_initial_state()
        self.env = env
        self.plots = plots
        self.food_storage = food
        self.sol = 0
        self.phase = "nominal"
        self.planting_allocation = None
        self.prev_crew_health = None
        self.active_crises = {}       # persistent crises dict
        self.sol_history = []
        self.sim_running = False
        self.sim_speed = 1.0          # Sols per second
        self.mission_complete = False
        self.seed = 42
        random.seed(self.seed)

        self.na = NutritionAgent(mcp=self.mcp)
        self.ea = EnvironmentAgent(mcp=self.mcp)
        self.ca = CrisisAgent(mcp=self.mcp)
        self.pa = PlannerAgent(mcp=self.mcp)

        self.nutrition_ledger = {"coverage_score": 0, "sol": 0}
        self.crew_health_state = []
        self.last_crises_active = []
        self.last_agent_report = {}


STATE = GameState()
connected_clients: set[WebSocket] = set()


def get_frontend_state():
    storage_days = STATE.food_storage.get("kcal", 0) / 12000 if STATE.food_storage else 0
    return {
        "mission_state": {
            "current_sol": STATE.sol,
            "phase": STATE.phase,
            "sim_running": STATE.sim_running,
            "sim_speed": STATE.sim_speed,
            "mission_duration": MISSION_DURATION,
            "mission_complete": STATE.mission_complete,
            "mcp_connected": MCP_CONNECTED,
        },
        "environment_state": STATE.env,
        "nutrition_ledger": STATE.nutrition_ledger,
        "greenhouse_plots": STATE.plots,
        "crew_health": STATE.crew_health_state,
        "sol_history": STATE.sol_history[-100:],
        "food_storage": {
            **STATE.food_storage,
            "days_remaining": storage_days,
        },
        "active_crises": {
            name: {
                "severity": info["severity"],
                "start_sol": info["start_sol"],
                "recovery_sol": info["recovery_sol"],
                "remaining_sols": max(0, info["recovery_sol"] - STATE.sol),
            }
            for name, info in STATE.active_crises.items()
        },
        "agent_report": STATE.last_agent_report,
    }


async def broadcast_state():
    data = get_frontend_state()
    disconnected = set()
    for client in connected_clients:
        try:
            await client.send_json(data)
        except Exception:
            disconnected.add(client)
    connected_clients.difference_update(disconnected)


def advance_sol():
    if STATE.mission_complete:
        return

    STATE.sol += 1

    # Steps 1-3: Environment
    STATE.env = step1_mars_external_drift(STATE.env)
    STATE.env = step2_internal_sensor_drift(STATE.env)
    STATE.env, STATE.plots = step3_cascade_effects(STATE.env, STATE.plots)

    # Step 4: Persistent crises
    STATE.env, STATE.plots, STATE.active_crises, newly_triggered = step4_crisis_roll(
        STATE.env, STATE.plots, STATE.sol, STATE.active_crises
    )
    crises_active = list(STATE.active_crises.keys())
    STATE.last_crises_active = crises_active

    # Step 5: Crop growth
    STATE.plots, harvests = step5_crop_growth(
        STATE.plots, STATE.env, STATE.sol, STATE.mcp, STATE.planting_allocation
    )

    # Step 6: Nutrition (stockpile model)
    nutrition_result = step6_nutritional_output(harvests, STATE.mcp, STATE.food_storage)
    daily = nutrition_result["daily_consumption"]
    STATE.food_storage = nutrition_result["food_storage"]

    # Step 7: Resources
    resources = step7_resource_consumption(STATE.plots, STATE.env)

    # Step 8: Agents
    # At high speed (>5x), use fast rule-based agents to keep up.
    # At low speed or manual, use full LLM+KB agents for grounded decisions.
    use_fast = STATE.sim_speed > 5
    if use_fast:
        # Temporarily swap to MockMCP to skip LLM calls (rules-only path)
        fast_mcp = MockMCP()
        from agents.nutrition_agent import NutritionAgent as NA
        from agents.environment_agent import EnvironmentAgent as EA
        from agents.crisis_agent import CrisisAgent as CA
        from agents.planner_agent import PlannerAgent as PA
        nr = NA(mcp=fast_mcp).run(STATE.sol, daily, STATE.prev_crew_health)
        er = EA(mcp=fast_mcp).run(STATE.sol, STATE.env)
        cr = CA(mcp=fast_mcp).run(STATE.sol, crises_active, active_crises_detail=STATE.active_crises)
        pp = PA(mcp=fast_mcp).run(nr, er, cr)
    else:
        nr = STATE.na.run(STATE.sol, daily, STATE.prev_crew_health)
        er = STATE.ea.run(STATE.sol, STATE.env)
        cr = STATE.ca.run(STATE.sol, crises_active, active_crises_detail=STATE.active_crises)
        pp = STATE.pa.run(nr, er, cr)

    # Step 8b: Apply agent decisions
    STATE.env = apply_environment_adjustments(STATE.env, er)
    STATE.env, STATE.plots = apply_crisis_containment(STATE.env, STATE.plots, cr)

    # Store planner allocation for next Sol
    assignments = pp.get("plot_assignments", [])
    if assignments:
        counts = {}
        for a in assignments:
            c = a.get("crop", "potato")
            counts[c] = counts.get(c, 0) + 1
        total = sum(counts.values()) or 1
        STATE.planting_allocation = {c: n / total for c, n in counts.items()}

    STATE.prev_crew_health = nr.get("crew_health_statuses", [])
    STATE.crew_health_state = STATE.prev_crew_health

    # Coverage score
    filtered = {k: daily.get(k, 0) for k in ["kcal", "protein_g", "vitamin_a", "vitamin_c", "vitamin_k", "folate"]}
    score = compute_coverage_score(**filtered)

    STATE.nutrition_ledger = {
        "sol": STATE.sol,
        "coverage_score": score,
        **daily,
    }

    # Phase transitions
    if crises_active:
        STATE.phase = "crisis"
    elif STATE.phase == "crisis" and not crises_active:
        STATE.phase = "recovery"
    elif STATE.phase == "recovery":
        STATE.phase = "nominal"

    # Store agent report summary (includes KB grounding info)
    STATE.last_agent_report = {
        "environment": {
            "adjustments": er.get("setpoint_adjustments", []),
            "reasoning": er.get("reasoning", ""),
            "kb_fallback": er.get("kb_fallback", True),
        },
        "crisis": {
            "handled": cr.get("crises_handled", []),
            "actions": cr.get("actions_taken", []),
            "reasoning": cr.get("reasoning", ""),
            "kb_fallback": cr.get("kb_fallback", True),
        },
        "planner": {
            "rationale": pp.get("rationale", ""),
            "kb_fallback": pp.get("kb_fallback", True),
        },
        "nutrition": {
            "coverage_score": nr.get("coverage_score", 0),
            "deficit_summary": nr.get("deficit_summary", ""),
            "crew_health_emergency": nr.get("crew_health_emergency", False),
            "kb_fallback": nr.get("kb_fallback", True),
        },
        "mcp_connected": MCP_CONNECTED,
    }

    # Sol history
    STATE.sol_history.append({
        "sol": STATE.sol,
        "nutrition_score": score,
        "kcal_produced": nutrition_result["harvest_added"]["kcal"],
        "kcal_consumed": daily.get("kcal", 0),
        "water_efficiency": STATE.env["water_efficiency_pct"],
        "energy_used": STATE.env["energy_used_pct"],
        "storage_days": STATE.food_storage.get("kcal", 0) / 12000,
        "crises_active": crises_active.copy(),
        "newly_triggered": newly_triggered,
        "num_harvests": len(harvests),
        "crew_health_avg": (
            sum(c.get("health_score", 100) for c in STATE.crew_health_state) / max(1, len(STATE.crew_health_state))
        ),
    })

    # Mission complete?
    if STATE.sol >= MISSION_DURATION:
        STATE.mission_complete = True
        STATE.sim_running = False


async def auto_sim_loop():
    """Background loop: advances Sols at configured speed."""
    while True:
        if STATE.sim_running and not STATE.mission_complete:
            advance_sol()
            await broadcast_state()
            # Speed: sols/sec → delay = 1/speed
            delay = max(0.05, 1.0 / STATE.sim_speed)
            await asyncio.sleep(delay)
        else:
            await asyncio.sleep(0.2)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(auto_sim_loop())


# ── Routes ──────────────────────────────────────────────────────────────────

@app.get("/")
def get_frontend():
    return FileResponse(os.path.join(os.path.dirname(__file__), "frontend", "index.html"))


@app.get("/state")
def get_state():
    return get_frontend_state()


class SimControlReq(BaseModel):
    action: str
    speed: float = None

@app.post("/sim-control")
async def sim_control(req: SimControlReq):
    if req.action == "start":
        if STATE.mission_complete:
            STATE.reset()
        STATE.sim_running = True
        if req.speed is not None:
            STATE.sim_speed = max(0.1, min(50, req.speed))
    elif req.action == "pause":
        STATE.sim_running = False
    elif req.action == "reset":
        STATE.reset()
    elif req.action == "speed" and req.speed is not None:
        STATE.sim_speed = max(0.1, min(50, req.speed))
    await broadcast_state()
    return {"sim_running": STATE.sim_running, "sim_speed": STATE.sim_speed}


@app.post("/run-sol")
async def run_sol():
    advance_sol()
    await broadcast_state()
    return get_frontend_state()


class CrisisReq(BaseModel):
    type: str

@app.post("/inject-crisis")
async def inject_crisis(req: CrisisReq):
    from simulation import _CRISIS_DEFINITIONS
    defn = _CRISIS_DEFINITIONS.get(req.type)
    if defn and req.type not in STATE.active_crises:
        severity = random.uniform(*defn["severity_range"])
        recovery_sols = max(1, round(defn["base_recovery_sols"] * (0.5 + severity)))
        STATE.active_crises[req.type] = {
            "start_sol": STATE.sol,
            "recovery_sol": STATE.sol + recovery_sols,
            "severity": round(severity, 2),
        }
        STATE.phase = "crisis"
    await broadcast_state()
    return {"status": "ok", "crisis": req.type, "active_crises": list(STATE.active_crises.keys())}


class ChatReq(BaseModel):
    message: str

@app.post("/chat")
def chat(req: ChatReq):
    """Chat with the orchestrator agent (uses Strands + Bedrock if available)."""
    try:
        orchestrator = OrchestratorAgent(mcp=STATE.mcp)
        mission_context = {
            "sol": STATE.sol,
            "nutrition_ledger": STATE.nutrition_ledger,
            "environment_state": STATE.env,
            "crises_active": STATE.last_crises_active,
            "crew_health": STATE.crew_health_state,
        }
        result = orchestrator.chat(req.message, mission_context)
        return result
    except Exception as e:
        logger.warning("Chat failed: %s", e)
        return {
            "response": f"Mission AI here (Sol {STATE.sol}). I'm running in offline mode. "
                        f"Current coverage: {STATE.nutrition_ledger.get('coverage_score', 0):.1f}%. "
                        f"Phase: {STATE.phase}. Active crises: {STATE.last_crises_active or 'none'}.",
            "reasoning": f"Fallback: {e}",
            "kb_fallback": True,
        }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)
    # Send initial state
    try:
        await websocket.send_json(get_frontend_state())
    except Exception:
        pass
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connected_clients.discard(websocket)


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description="OrbitGrow local server")
    parser.add_argument("--offline", action="store_true",
                        help="Skip Syngenta MCP KB, use hardcoded data only")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    USE_MCP = not args.offline

    # Re-create global state with proper MCP client
    STATE.mcp = create_mcp_client()
    STATE.na = NutritionAgent(mcp=STATE.mcp)
    STATE.ea = EnvironmentAgent(mcp=STATE.mcp)
    STATE.ca = CrisisAgent(mcp=STATE.mcp)
    STATE.pa = PlannerAgent(mcp=STATE.mcp)

    print(f"\n{'='*60}")
    print(f"  OrbitGrow — Autonomous Mars Greenhouse")
    print(f"  MCP KB: {'LIVE (Syngenta)' if MCP_CONNECTED else 'Offline (hardcoded)'}")
    print(f"  Open http://localhost:{args.port}")
    print(f"{'='*60}\n")

    uvicorn.run(app, host="0.0.0.0", port=args.port)
