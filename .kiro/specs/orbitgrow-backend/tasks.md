# Tasks — OrbitGrow Backend

## Task List

- [x] 1. Amplify Gen2 Data Schema
  - [x] 1.1 Replace the `Todo` placeholder in `OrbitGrow/amplify/data/resource.ts` with the `MissionState` model (fields: `current_sol` Int, `phase` String, `last_updated` AWSDateTime) with `allow.authenticated().to(['read'])` auth
  - [x] 1.2 Add `GreenhousePlot` model (fields: `plot_id` String, `crop` String, `planted_sol` Int, `harvest_sol` Int, `area_m2` Float, `health` Float, `stress_flags` [String]) with same auth
  - [x] 1.3 Add `SolReport` model (fields: `sol` Int, `nutrition_score` Float, `kcal_produced` Float, `protein_g` Float, `water_efficiency` Float, `energy_used` Float, `agent_decisions` AWSJSON, `crises_active` [String]) with same auth
  - [x] 1.4 Add `NutritionLedger` model (fields: `sol` Int, `kcal` Float, `protein_g` Float, `vitamin_a` Float, `vitamin_c` Float, `vitamin_k` Float, `folate` Float, `coverage_score` Float) with same auth
  - [x] 1.5 Add `CrewHealth` model (fields: `astronaut` String, `sol` Int, `kcal_received` Float, `protein_g` Float, `vitamin_a` Float, `vitamin_c` Float, `vitamin_k` Float, `folate` Float, `health_score` Float, `deficit_flags` [String]) with same auth
  - [x] 1.6 Add `EnvironmentState` model (fields: `sol` Int, `temperature_c` Float, `humidity_pct` Float, `co2_ppm` Float, `light_umol` Float, `water_efficiency_pct` Float, `energy_used_pct` Float, `external_temp_c` Float, `dust_storm_index` Float, `radiation_msv` Float) with same auth
  - [x] 1.7 Update `authorizationModes` in `defineData` to use `userPool` as the default auth mode

- [x] 2. Infrastructure — API Gateway + Lambda (SAM or CDK)
  - [x] 2.1 Create `OrbitGrow/infrastructure/template.yaml` (SAM) defining the REST API with POST /run-sol, POST /inject-crisis, POST /chat routes and CORS enabled
  - [x] 2.2 Add WebSocket API definition with `$connect`, `$disconnect`, `$default` routes
  - [x] 2.3 Define the `ws_connections` DynamoDB table (PK: `connection_id` String) in the template
  - [x] 2.4 Define IAM roles for all Lambda functions granting DynamoDB read/write on all tables and `execute-api:ManageConnections` for WebSocket broadcast
  - [x] 2.5 Wire each Lambda function (run_sol, inject_crisis, chat, ws_connect, ws_disconnect) to its route in the template with Python 3.11 runtime and 60s timeout (300s for run_sol)

- [x] 3. MCP Client (`OrbitGrow/agents/mcp_client.py`)
  - [x] 3.1 Implement `MCPClient` class with `query(document_id, query)` method that connects to the AgentCore MCP endpoint via streamable HTTP using the `mcp` Python SDK
  - [x] 3.2 Add in-memory `KB_CACHE` dict; on any connection error or timeout (10s), return cached value with `kb_fallback: True`; if no cache exists, return `HARDCODED_DEFAULTS` for that document with `kb_fallback: True`
  - [x] 3.3 Define `HARDCODED_DEFAULTS` for documents 03 (nutritional profiles), 04 (environmental constraints), and 06 (crisis playbooks) as fallback values

- [x] 4. Simulation Engine (`OrbitGrow/lambdas/run_sol/simulation.py`)
  - [x] 4.1 Implement `apply_drift(current, drift_magnitude, hard_min, hard_max) -> float` using `clamp(current + random.uniform(-drift, +drift), hard_min, hard_max)`
  - [x] 4.2 Implement `step1_mars_external_drift(env: dict) -> dict` applying drift to `external_temp_c` (±8, [-125,20]), `dust_storm_index` (±0.05, [0,1]), `radiation_msv` (±0.05, [0.1,0.7])
  - [x] 4.3 Implement `step2_internal_sensor_drift(env: dict) -> dict` applying drift to all 6 internal sensors per spec bounds
  - [x] 4.4 Implement `step3_cascade_effects(env: dict, plots: list) -> tuple[dict, list]` applying dust→light, cold→energy, and radiation→crop health rules
  - [x] 4.5 Implement `step4_crisis_roll(env: dict, plots: list) -> tuple[dict, list, list]` rolling independent checks for all 5 crisis types and applying their state effects; return updated env, plots, and `crises_active` list
  - [x] 4.6 Implement `step5_crop_growth(plots: list, env: dict, sol: int, mcp: MCPClient) -> tuple[list, list]` advancing plot age, applying stress multipliers from MCP_KB doc 04, computing yield at harvest, resetting harvested plots; return updated plots and harvest records
  - [x] 4.7 Implement `step6_nutritional_output(harvests: list, mcp: MCPClient) -> dict` summing kcal/protein/vitamins across all harvests using MCP_KB doc 03 nutritional profiles
  - [x] 4.8 Implement `step7_resource_consumption(plots: list, env: dict) -> dict` computing water and energy consumed per crop type and area
  - [x] 4.9 Implement `compute_coverage_score(kcal, protein_g, micronutrient_composite, target) -> float` using the formula `min(((kcal/12000)*0.40 + (protein_g/450)*0.35 + (micronutrient_composite/target)*0.25) * 100, 100.0)`

- [x] 5. AI Agents
  - [x] 5.1 Implement `OrbitGrow/agents/mcp_client.py` (covered in task 3)
  - [x] 5.2 Implement `OrbitGrow/agents/nutrition_agent.py` — `NutritionAgent.run(sol, nutrition_ledger)`: reads nutrition_ledger, queries MCP_KB doc 03 for micronutrient targets, computes coverage_score, computes per-astronaut health_score deltas, sets deficit_flags, returns NutritionReport; includes `crew_health_emergency` signal if any score < 60
  - [x] 5.3 Implement `OrbitGrow/agents/environment_agent.py` — `EnvironmentAgent.run(sol, environment_state)`: reads sensor state, queries MCP_KB doc 04 for optimal bands, determines setpoint adjustments for out-of-band sensors, returns EnvironmentReport with reasoning
  - [x] 5.4 Implement `OrbitGrow/agents/crisis_agent.py` — `CrisisAgent.run(sol, crises_active)`: if empty returns no-op report; otherwise queries MCP_KB doc 06 for each crisis playbook, applies containment actions to DynamoDB, returns CrisisReport with recovery timeline
  - [x] 5.5 Implement `OrbitGrow/agents/planner_agent.py` — `PlannerAgent.run(nutrition_report, environment_report, crisis_report)`: queries MCP_KB for crop selection criteria, outputs PlantingPlan maintaining baseline allocation or shifting beans +5pp on protein deficit / potato +5pp on kcal deficit
  - [x] 5.6 Implement `OrbitGrow/agents/orchestrator.py` — `OrchestratorAgent.run(sol, mission_context)`: invokes Nutrition → Environment → Crisis → Planner agents in sequence, synthesizes DailyMissionReport, includes `crew_health_emergency` flag if triggered, uses Claude 3.5 Sonnet via Bedrock

- [x] 6. Lambda Handlers
  - [x] 6.1 Implement `OrbitGrow/lambdas/run_sol/handler.py`: reads current state from DynamoDB, runs simulation steps 1–7, runs step 8 (agents via OrchestratorAgent), runs step 9 (writes all records to DynamoDB), invokes ws_broadcast, returns HTTP 200 with `mission_state`, `environment_state`, `nutrition_ledger`, `sol_reports`; returns HTTP 500 with `message` and `sol` on any unhandled exception
  - [x] 6.2 Implement `OrbitGrow/lambdas/inject_crisis/handler.py`: validates `type` field against 5 known crisis types (HTTP 400 if invalid), applies crisis state changes to current `environment_state` and `greenhouse_plots` in DynamoDB, updates `mission_state.phase` to `"crisis"`, adds crisis to current Sol's `crises_active`, returns HTTP 200 with confirmed crisis and updated `mission_state`
  - [x] 6.3 Implement `OrbitGrow/lambdas/chat/handler.py`: validates message length 1–2000 chars (HTTP 400 if invalid), fetches current `mission_state`, latest `sol_reports`, `nutrition_ledger`, `environment_state`, and 4 `crew_health` records from DynamoDB, invokes OrchestratorAgent with message + context (30s timeout → HTTP 503), returns HTTP 200 with `response` and `reasoning`
  - [x] 6.4 Implement `OrbitGrow/lambdas/ws_connect/handler.py`: writes `connection_id` and `connected_at` to `ws_connections` DynamoDB table, returns HTTP 200
  - [x] 6.5 Implement `OrbitGrow/lambdas/ws_disconnect/handler.py`: deletes `connection_id` from `ws_connections` DynamoDB table, returns HTTP 200

- [x] 7. WebSocket Broadcast (`OrbitGrow/lambdas/ws_broadcast/handler.py`)
  - [x] 7.1 Implement broadcast handler: scan `ws_connections` table for all active connection IDs
  - [x] 7.2 For each connection, post the broadcast payload (`mission_state`, `environment_state`, `nutrition_ledger`, `crises_active`) via API Gateway Management API
  - [x] 7.3 On `GoneException`, delete the stale connection ID from DynamoDB and continue to remaining connections

- [x] 8. Backend Initialization (`OrbitGrow/lambdas/init_mission/handler.py`)
  - [x] 8.1 Implement init handler that writes `mission_state` record: `current_sol=0`, `phase="nominal"`, `last_updated=now`
  - [x] 8.2 Write all 20 `greenhouse_plots` records with seed distribution (9 potato, 5 beans, 4 lettuce, 1 radish, 1 herbs), `health=1.0`, `stress_flags=[]`, appropriate `planted_sol` and `harvest_sol` values
  - [x] 8.3 Write Sol 0 `environment_state` record with all nominal seed values from spec
  - [x] 8.4 Use DynamoDB `put_item` with no condition so existing Sol 0 records are overwritten; do not delete records with `sol > 0`
  - [x] 8.5 Expose init as `POST /init-mission` in the infrastructure template

- [x] 9. Property-Based Tests
  - [x] 9.1 Write `OrbitGrow/tests/property/test_drift_bounds.py` — Property 13: for any sensor value and drift delta, `apply_drift` result stays within `[hard_min, hard_max]` for all 9 sensor variables; use `@settings(max_examples=100)`
  - [x] 9.2 Write `OrbitGrow/tests/property/test_health_invariants.py` — Property 4: for any sequence of health deltas, plot health stays in [0.0, 1.0]; Property 10: for any K deficit flags, health_score decreases by 2*K floored at 0; for zero deficits and all targets met, health_score increases by 1 capped at 100
  - [x] 9.3 Write `OrbitGrow/tests/property/test_nutrition_formulas.py` — Property 8: for any kcal/protein/micronutrient values, `compute_coverage_score` matches formula and is clamped to 100; Property 19: for any list of harvest records, total kcal in nutrition_ledger equals sum of individual harvest kcal contributions
  - [x] 9.4 Write `OrbitGrow/tests/property/test_simulation_steps.py` — Property 1: sol counter increments by exactly 1; Property 14: dust cascade formula; Property 15: cold cascade formula; Property 16: each crisis type produces correct state change; Property 18: yield = area * base_yield * health
  - [x] 9.5 Write `OrbitGrow/tests/property/test_api_validation.py` — Property 20: for any string with length 0 or > 2000, chat handler returns HTTP 400
  - [x] 9.6 Write `OrbitGrow/tests/property/test_planner.py` — Property 23: for any NutritionReport with protein deficit, PlantingPlan beans allocation ≥ baseline + 5pp; for kcal deficit, potato allocation ≥ baseline + 5pp

- [x] 10. Unit Tests
  - [x] 10.1 Write `OrbitGrow/tests/unit/test_initialization.py`: verify Sol 0 seed values for mission_state, all 20 plots (count, crop distribution, health, stress_flags), and environment_state match spec exactly
  - [x] 10.2 Write `OrbitGrow/tests/unit/test_simulation_engine.py`: phase transition sequence (nominal→crisis→recovery→nominal after 3 quiet Sols); harvest triggers plot reset with health=1.0; nutritional output split equally across 4 astronauts
  - [x] 10.3 Write `OrbitGrow/tests/unit/test_crisis_effects.py`: each of the 5 crisis types produces the correct state change when injected; unknown crisis type returns HTTP 400
  - [x] 10.4 Write `OrbitGrow/tests/unit/test_api_handlers.py`: run-sol returns HTTP 200 with correct response shape; run-sol returns HTTP 500 on DynamoDB failure; chat returns HTTP 503 on agent timeout; WebSocket connect stores connection_id; WebSocket disconnect removes connection_id; stale connection cleaned up during broadcast
  - [x] 10.5 Write `OrbitGrow/tests/unit/test_agents.py`: crew health emergency flag appears in DailyMissionReport when any astronaut score < 60; MCP fallback sets `kb_fallback: true` when endpoint unreachable; CrisisAgent returns no-op report when crises_active is empty
