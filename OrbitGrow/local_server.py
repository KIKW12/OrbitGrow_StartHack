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
import io
import uuid
import random
import asyncio
import json
import logging
import argparse

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from PIL import Image as PILImage

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
from agents.vision_service import VisionService, SyntheticImageGenerator
from agents.vision_agent import VisionAgent
from agents.greenhouse_models import (
    CROPS, SCAN_ANGLES,
    build_initial_greenhouses,
    build_initial_mars_env,
    build_initial_facility_env,
    build_initial_astronauts,
)

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

# Serve frontend static assets (images, etc.)
_frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
app.mount("/images", StaticFiles(directory=os.path.join(_frontend_dir, "images")), name="images")


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
                "last_cv_analysis_sol": -1,
                "cv_confidence": 0.0,
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

        # New greenhouse model state
        self.greenhouses  = build_initial_greenhouses()
        self.mars_env     = build_initial_mars_env()
        self.facility_env = build_initial_facility_env()
        self.astronauts   = build_initial_astronauts()
        self.advice       = []


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
        "greenhouses":  STATE.greenhouses,
        "mars_env":     STATE.mars_env,
        "facility_env": STATE.facility_env,
        "astronauts":   STATE.astronauts,
        "advice":       STATE.advice[-20:],   # last 20 advice entries
        "crops":        CROPS,
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

    # Drift greenhouse sensors each Sol (gentle random walk within bounds)
    import random as _rnd
    for gh in STATE.greenhouses:
        crop = CROPS.get(gh["crop_id"], {})
        gh["temperature"]   = round(max(crop.get("min_temperature", 15), min(crop.get("max_temperature", 30), gh["temperature"]   + _rnd.uniform(-0.4, 0.4))), 2)
        gh["air_humidity"]  = round(max(crop.get("min_humidity", 50),    min(crop.get("max_humidity", 85),    gh["air_humidity"]  + _rnd.uniform(-0.8, 0.8))), 2)
        gh["ph"]            = round(max(crop.get("min_ph", 5.5),         min(crop.get("max_ph", 7.5),         gh["ph"]            + _rnd.uniform(-0.05, 0.05))), 2)
        gh["soil_moisture"] = round(max(crop.get("min_soil_moisture", 0.2), min(crop.get("max_soil_moisture", 0.5), gh["soil_moisture"] + _rnd.uniform(-0.01, 0.01))), 3)
        gh["day"]           = round(gh["day"] + 1.0, 1)
        if gh["day"] >= crop.get("growth_cycle", 90):
            gh["day"] = 0.0  # reset after harvest
        gh["health"] = round(max(0.0, min(1.0, gh["health"] + _rnd.uniform(-0.005, 0.003))), 4)
    # Drift Mars env
    STATE.mars_env["temperature"] = round(STATE.env.get("external_temp_c", -60), 1)
    STATE.mars_env["light"]       = round(STATE.env.get("light_umol", 400) * 0.4, 1)  # solar fraction
    # Drift facility env
    STATE.facility_env["co2"]     = round(STATE.env.get("co2_ppm", 1200), 1)
    STATE.facility_env["radiation"] = round(STATE.env.get("radiation_msv", 0.3), 3)

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

    # Step 4.5: CV health blend (skipped at sim_speed > 5x)
    # Rotate through 5 plots per Sol so a full cycle covers all 20 plots every 4 Sols.
    # Each plot is analysed every 4 Sols — adequate for 30–120 Sol harvest cycles.
    cv_results = {}
    use_fast_cv = STATE.sim_speed > 5
    if not use_fast_cv:
        start_idx = (STATE.sol % 4) * 5
        subset    = STATE.plots[start_idx: start_idx + 5]
        try:
            vs         = VisionService()
            cv_results = vs.analyze_all_plots(subset, STATE.env, use_fast=False)
            for plot in subset:
                pid    = plot["plot_id"]
                result = cv_results.get(pid)
                if not result:
                    continue
                conf      = result.get("confidence", 0.0)
                cv_health = result.get("health_score", plot["health"])
                # Blend: CV gets up to 70 % weight proportional to confidence.
                # Simulation retains at least 30 % — it encodes env history the image cannot see.
                blend_weight        = min(conf, 0.7)
                plot["health"]      = round(
                    max(0.0, min(1.0, blend_weight * cv_health + (1 - blend_weight) * plot["health"])),
                    4,
                )
                existing            = set(plot.get("stress_flags", []))
                cv_flags            = set(result.get("stress_flags", []))
                plot["stress_flags"]         = list(existing | cv_flags)
                plot["last_cv_analysis_sol"] = STATE.sol
                plot["cv_confidence"]        = round(conf, 3)
        except Exception as cv_exc:
            logger.warning("CV analysis failed, continuing without it: %s", cv_exc)

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
        vr = {}
    else:
        nr = STATE.na.run(STATE.sol, daily, STATE.prev_crew_health)
        er = STATE.ea.run(STATE.sol, STATE.env)
        cr = STATE.ca.run(STATE.sol, crises_active, active_crises_detail=STATE.active_crises)
        pp = STATE.pa.run(nr, er, cr)
        # Step 4.6: VisionAgent — KB-grounded reasoning over CV results
        vr = {}
        if cv_results:
            try:
                vr = VisionAgent(mcp=STATE.mcp).run(
                    sol=STATE.sol,
                    cv_results=cv_results,
                    plots=STATE.plots,
                    env=STATE.env,
                )
            except Exception as va_exc:
                logger.warning("VisionAgent failed: %s", va_exc)

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
        "vision": {
            "plots_analyzed": [r["plot_id"] for r in cv_results.values()],
            "avg_health": round(
                sum(r["health_score"] for r in cv_results.values()) / max(1, len(cv_results)), 3
            ) if cv_results else None,
            "avg_confidence": round(
                sum(r["confidence"] for r in cv_results.values()) / max(1, len(cv_results)), 3
            ) if cv_results else None,
            "skipped": use_fast_cv or not cv_results,
            # VisionAgent fields
            "summary":             vr.get("summary", ""),
            "detailed_reasoning":  vr.get("detailed_reasoning", ""),
            "plots_at_risk":       vr.get("plots_at_risk", []),
            "recommended_actions": vr.get("recommended_actions", []),
            "kb_fallback":         vr.get("kb_fallback", True),
        },
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


class AnalyzePlotReq(BaseModel):
    plot_id: str

@app.post("/analyze-plot")
async def analyze_plot_endpoint(req: AnalyzePlotReq):
    """On-demand CV scan of a single plot via Claude Vision."""
    plot = next((p for p in STATE.plots if p["plot_id"] == req.plot_id), None)
    if not plot:
        raise HTTPException(status_code=404, detail=f"Plot '{req.plot_id}' not found.")
    vs     = VisionService()
    result = vs.analyze_plot(plot, STATE.env)
    return result


@app.post("/analyze-image")
async def analyze_image(
    file: UploadFile = File(...),
    plot_id: str = Form(default=None),
):
    """
    Analyse a real uploaded image with Claude Vision.
    Optionally bind to a plot_id to get real plot context (crop type, current health, etc.).
    Accepts JPEG, PNG, WebP. For HEIC files, convert first:
        sips -s format jpeg input.HEIC --out output.jpg
    """
    contents = await file.read()
    try:
        img = PILImage.open(io.BytesIO(contents)).convert("RGB")
        # Resize large photos to max 1024 px on the longest side — keeps Bedrock payload small
        max_dim = 1024
        if max(img.width, img.height) > max_dim:
            img.thumbnail((max_dim, max_dim), PILImage.LANCZOS)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot decode image: {exc}")

    # Resolve plot context — use real plot if provided, otherwise a generic placeholder
    plot = {"plot_id": "uploaded", "crop": "unknown", "health": 1.0, "stress_flags": []}
    if plot_id:
        match = next((p for p in STATE.plots if p["plot_id"] == plot_id), None)
        if match:
            plot = match

    vs     = VisionService()
    result = vs.analyze_plot(plot, STATE.env, image=img)
    result["image_filename"] = file.filename
    result["image_size"]     = f"{img.width}x{img.height}"
    return result


@app.post("/plant-health-check")
async def plant_health_check(
    file: UploadFile = File(...),
    plot_id: str = Form(default=None),
):
    """
    Full plant health analysis pipeline:
      1. OpenCV preprocessing
      2. Claude Vision → CV health score + stress flags
      3. VisionAgent → KB-grounded treatment plan + mission impact
    Returns combined result for display in the frontend plot modal.
    """
    contents = await file.read()
    try:
        img = PILImage.open(io.BytesIO(contents)).convert("RGB")
        if max(img.width, img.height) > 1024:
            img.thumbnail((1024, 1024), PILImage.LANCZOS)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot decode image: {exc}")

    plot = {"plot_id": plot_id or "uploaded", "crop": "unknown", "health": 1.0, "stress_flags": []}
    if plot_id:
        match = next((p for p in STATE.plots if p["plot_id"] == plot_id), None)
        if match:
            plot = match

    vs        = VisionService()
    cv_result = vs.analyze_plot(plot, STATE.env, image=img)

    va             = VisionAgent(mcp=STATE.mcp)
    agent_analysis = va.analyze_image_with_agent(cv_result, plot, STATE.env, STATE.sol)

    return {
        "cv_analysis":    cv_result,
        "agent_analysis": agent_analysis,
        "plot_context": {
            "plot_id":          plot.get("plot_id"),
            "crop":             plot.get("crop"),
            "sim_health":       plot.get("health"),
            "harvest_sol":      plot.get("harvest_sol"),
            "sol":              STATE.sol,
            "image_size":       f"{img.width}×{img.height}",
            "image_filename":   file.filename,
        },
    }


@app.get("/camera-feed/{plot_id}")
async def camera_feed(plot_id: str):
    """Serve a synthetic camera JPEG image for a plot."""
    plot = next((p for p in STATE.plots if p["plot_id"] == plot_id), None)
    if not plot:
        raise HTTPException(status_code=404, detail=f"Plot '{plot_id}' not found.")
    img = SyntheticImageGenerator().generate(plot, STATE.env)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/jpeg")


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


@app.get("/greenhouses")
def get_greenhouses():
    return {"greenhouses": STATE.greenhouses, "crops": CROPS}


@app.get("/greenhouse/{gh_id}")
def get_greenhouse(gh_id: str):
    gh = next((g for g in STATE.greenhouses if g["id"] == gh_id), None)
    if not gh:
        raise HTTPException(status_code=404, detail=f"Greenhouse '{gh_id}' not found")
    crop = CROPS.get(gh["crop_id"], {})
    return {"greenhouse": gh, "crop": crop, "mars_env": STATE.mars_env, "facility_env": STATE.facility_env}


@app.post("/robot-scan/{gh_id}")
async def robot_scan(gh_id: str):
    """
    Simulate the robot dog scanning a greenhouse from 4 preset angles.
    Returns CV analysis for each angle and updates greenhouse health/alerts.
    """
    gh = next((g for g in STATE.greenhouses if g["id"] == gh_id), None)
    if not gh:
        raise HTTPException(status_code=404, detail=f"Greenhouse '{gh_id}' not found")

    crop_id = gh["crop_id"]
    # Build a plot-compatible dict for VisionService
    plot_proxy = {
        "plot_id":              gh["id"],
        "crop":                 crop_id,
        "health":               gh["health"],
        "stress_flags":         gh["stress_flags"],
        "last_cv_analysis_sol": gh["last_scan_sol"],
    }

    scan_results = []
    vs = VisionService()
    all_health_scores = []
    all_flags = set()

    for angle_info in SCAN_ANGLES:
        angle_id = angle_info["id"]
        img = SyntheticImageGenerator().generate(plot_proxy, STATE.env, angle=angle_id)
        result = vs.analyze_plot(plot_proxy, STATE.env, image=img)
        scan_results.append({
            "angle_id":    angle_id,
            "angle_label": angle_info["label"],
            "description": angle_info["description"],
            "health_score":  result["health_score"],
            "confidence":    result["confidence"],
            "stress_flags":  result["stress_flags"],
            "cv_reasoning":  result["cv_reasoning"],
            "kb_fallback":   result["kb_fallback"],
        })
        if not result["kb_fallback"]:
            all_health_scores.append(result["health_score"])
            all_flags.update(result["stress_flags"])

    # Aggregate results
    avg_health = sum(all_health_scores) / len(all_health_scores) if all_health_scores else gh["health"]
    disease_detected = "disease" in all_flags

    # Update greenhouse state
    gh["health"]               = round(avg_health, 4)
    gh["stress_flags"]         = list(all_flags)
    gh["disease_detected"]     = disease_detected
    gh["last_scan_sol"]        = STATE.sol
    gh["cv_confidence"]        = round(sum(r["confidence"] for r in scan_results) / len(scan_results), 3)
    gh["latest_scan_results"]  = scan_results

    # Generate alert if disease detected or health low
    new_alerts = []
    if disease_detected:
        new_alerts.append({
            "day":      f"Sol {STATE.sol}",
            "text":     f"\u26a0 Disease detected in {gh['name']} ({CROPS[crop_id]['name']}). Immediate isolation recommended.",
            "severity": "high",
            "gh_id":    gh_id,
        })
    if avg_health < 0.5:
        new_alerts.append({
            "day":      f"Sol {STATE.sol}",
            "text":     f"\U0001f534 Critical health ({avg_health:.0%}) in {gh['name']}. Crew intervention required.",
            "severity": "high",
            "gh_id":    gh_id,
        })
    elif avg_health < 0.7:
        new_alerts.append({
            "day":      f"Sol {STATE.sol}",
            "text":     f"\U0001f7e1 Moderate stress in {gh['name']} \u2014 {', '.join(all_flags) or 'low vitality'}.",
            "severity": "medium",
            "gh_id":    gh_id,
        })

    gh["alerts"] = new_alerts
    STATE.advice.extend(new_alerts)

    await broadcast_state()
    return {
        "gh_id":           gh_id,
        "greenhouse_name": gh["name"],
        "crop":            crop_id,
        "sol":             STATE.sol,
        "scan_results":    scan_results,
        "aggregate": {
            "avg_health":      round(avg_health, 4),
            "disease_detected": disease_detected,
            "all_flags":       list(all_flags),
        },
        "alerts": new_alerts,
    }


@app.get("/camera-feed-angle/{gh_id}/{angle_id}")
async def camera_feed_angle(gh_id: str, angle_id: str):
    """Serve a synthetic camera image for a greenhouse at a specific scan angle."""
    gh = next((g for g in STATE.greenhouses if g["id"] == gh_id), None)
    if not gh:
        raise HTTPException(status_code=404, detail=f"Greenhouse '{gh_id}' not found")
    valid_angles = {a["id"] for a in SCAN_ANGLES}
    if angle_id not in valid_angles:
        raise HTTPException(status_code=400, detail=f"Invalid angle '{angle_id}'")
    plot_proxy = {
        "plot_id": gh["id"], "crop": gh["crop_id"],
        "health": gh["health"], "stress_flags": gh["stress_flags"],
        "last_cv_analysis_sol": gh["last_scan_sol"],
    }
    img = SyntheticImageGenerator().generate(plot_proxy, STATE.env, angle=angle_id)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/jpeg")


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
