# Requirements Document

## Introduction

OrbitGrow is an autonomous Martian greenhouse management backend that feeds 4 astronauts for a 450-Sol Mars surface mission. The backend provides a simulation engine that advances the mission Sol-by-Sol, a multi-agent AI system (Orchestrator, Nutrition, Environment, Crisis, and Planner agents) that makes autonomous decisions each Sol, a REST API for frontend interaction, a WebSocket channel for real-time state push, and a DynamoDB-backed state store. All agent reasoning is grounded in the Mars Crop Knowledge Base accessed via MCP.

## Glossary

- **Sol**: One Martian day (~24.6 hours). The atomic unit of simulation time.
- **System**: The OrbitGrow backend as a whole.
- **Simulation_Engine**: The Lambda function component that advances environmental and crop state each Sol.
- **Orchestrator_Agent**: The top-level AI agent that coordinates all sub-agents and writes the DailyMissionReport each Sol.
- **Nutrition_Agent**: Sub-agent responsible for computing nutritional output and per-astronaut health scores.
- **Environment_Agent**: Sub-agent responsible for reading sensor state and adjusting greenhouse setpoints.
- **Crisis_Agent**: Sub-agent responsible for detecting and responding to active crises using KB playbooks.
- **Planner_Agent**: Sub-agent responsible for producing the PlantingPlan for the next Sol.
- **MCP_KB**: The Mars Crop Knowledge Base accessible at the AgentCore MCP endpoint, providing crop profiles, nutritional data, environmental constraints, and crisis playbooks.
- **DynamoDB**: The AWS DynamoDB database used as the mission state store.
- **Sol_API**: The REST API Gateway exposing `/run-sol`, `/inject-crisis`, and `/chat` endpoints backed by Lambda.
- **WebSocket_API**: The API Gateway WebSocket endpoint that pushes Sol state updates to connected frontend clients.
- **NutritionReport**: The structured output of the Nutrition_Agent for a given Sol.
- **EnvironmentReport**: The structured output of the Environment_Agent for a given Sol.
- **CrisisReport**: The structured output of the Crisis_Agent for a given Sol.
- **PlantingPlan**: The structured output of the Planner_Agent specifying crop allocations for the next Sol.
- **DailyMissionReport**: The consolidated per-Sol report written to DynamoDB by the Orchestrator_Agent.
- **Nutritional_Coverage_Score**: The mission KPI computed as `((kcal/12000)*0.40 + (protein_g/450)*0.35 + (micronutrient_composite/target)*0.25) * 100`.
- **Health_Score**: Per-astronaut score starting at 100, decreasing 2 points per Sol per active deficit flag, recovering 1 point per Sol when all targets are met.
- **Crew_Health_Emergency**: Condition triggered when any astronaut Health_Score drops below 60.
- **Crisis**: An anomalous condition affecting greenhouse operations — one of: water_recycling_failure, energy_budget_cut, temperature_spike, disease_outbreak, co2_imbalance.
- **Drift**: Bounded random walk applied each Sol: `new_value = clamp(current + random(−drift, +drift), hard_min, hard_max)`.
- **Astronaut**: One of four crew members: Commander, Scientist, Engineer, Pilot.
- **Plot**: One of 20 greenhouse growing areas, each assigned a single crop type.

---

## Requirements

### Requirement 1: Data Model — Mission State

**User Story:** As a frontend developer, I want a persistent mission state record, so that the current Sol number and mission phase are always available.

#### Acceptance Criteria

1. THE System SHALL store a single `mission_state` record in DynamoDB with fields: `current_sol` (integer ≥ 0), `phase` (one of `nominal`, `crisis`, `recovery`), and `last_updated` (ISO 8601 timestamp).
2. WHEN the backend is initialized at Sol 0, THE System SHALL write a `mission_state` record with `current_sol = 0`, `phase = "nominal"`, and `last_updated` set to the initialization timestamp.
3. WHEN a Sol is advanced, THE System SHALL update `current_sol` by exactly 1 and update `last_updated` to the current timestamp.
4. WHEN at least one Crisis is active during a Sol, THE System SHALL set `phase` to `"crisis"`.
5. WHEN no Crisis is active and the previous Sol had `phase = "crisis"`, THE System SHALL set `phase` to `"recovery"`.
6. WHEN no Crisis is active and `phase` is `"nominal"` or `"recovery"` for 3 consecutive Sols, THE System SHALL set `phase` to `"nominal"`.

---

### Requirement 2: Data Model — Greenhouse Plots

**User Story:** As a frontend developer, I want to read the state of all 20 greenhouse plots, so that I can render the digital twin visualization.

#### Acceptance Criteria

1. THE System SHALL store exactly 20 `greenhouse_plots` records in DynamoDB, each with fields: `plot_id` (string, e.g. `PLOT#A#1`), `crop` (one of `potato`, `beans`, `lettuce`, `radish`, `herbs`), `planted_sol` (integer), `harvest_sol` (integer), `area_m2` (number), `health` (number 0.0–1.0), and `stress_flags` (list of strings).
2. WHEN the backend is initialized at Sol 0, THE System SHALL seed the 20 plots with the following crop distribution: 9 plots of `potato`, 5 plots of `beans`, 4 plots of `lettuce`, 1 plot of `radish`, 1 plot of `herbs`.
3. WHEN the backend is initialized at Sol 0, THE System SHALL set `health = 1.0` and `stress_flags = []` for all plots.
4. WHEN a Sol is advanced and a plot's `health` drops below 0.0, THE System SHALL clamp `health` to 0.0.
5. WHEN a Sol is advanced and a plot's `health` exceeds 1.0, THE System SHALL clamp `health` to 1.0.
6. WHEN a plot reaches its `harvest_sol`, THE System SHALL calculate yield and reset the plot with a new `planted_sol`, `harvest_sol`, and `health = 1.0`.

---

### Requirement 3: Data Model — Sol Reports

**User Story:** As a frontend developer, I want a per-Sol snapshot of mission metrics, so that I can display the Agent Decision Log and timeline.

#### Acceptance Criteria

1. THE System SHALL write one `sol_reports` record to DynamoDB per Sol with fields: `sol` (integer), `nutrition_score` (number 0–100), `kcal_produced` (number), `protein_g` (number), `water_efficiency` (number), `energy_used` (number), `agent_decisions` (JSON array), and `crises_active` (list of strings).
2. WHEN a Sol completes, THE System SHALL populate `agent_decisions` with the structured decision output from all agents that ran during that Sol.
3. WHEN no crises are active during a Sol, THE System SHALL write `crises_active` as an empty list.

---

### Requirement 4: Data Model — Nutrition Ledger

**User Story:** As a frontend developer, I want per-Sol nutritional output data, so that I can render the Nutrition Panel charts.

#### Acceptance Criteria

1. THE System SHALL write one `nutrition_ledger` record to DynamoDB per Sol with fields: `sol` (integer), `kcal` (number), `protein_g` (number), `vitamin_a` (number), `vitamin_c` (number), `vitamin_k` (number), `folate` (number), and `coverage_score` (number 0–100).
2. THE System SHALL compute `coverage_score` using the formula: `((kcal/12000)*0.40 + (protein_g/450)*0.35 + (micronutrient_composite/target)*0.25) * 100`.
3. WHEN `coverage_score` exceeds 100, THE System SHALL clamp it to 100.

---

### Requirement 5: Data Model — Crew Health

**User Story:** As a frontend developer, I want per-astronaut per-Sol health data, so that I can render the Crew Health Panel cards.

#### Acceptance Criteria

1. THE System SHALL write 4 `crew_health` records to DynamoDB per Sol — one per Astronaut — with fields: `astronaut` (one of `commander`, `scientist`, `engineer`, `pilot`), `sol` (integer), `kcal_received` (number), `protein_g` (number), `vitamin_a` (number), `vitamin_c` (number), `vitamin_k` (number), `folate` (number), `health_score` (number 0–100), and `deficit_flags` (list of strings).
2. WHEN all nutritional targets are met for an Astronaut on a given Sol, THE System SHALL increase that Astronaut's `health_score` by 1 point, to a maximum of 100.
3. WHEN an Astronaut has one or more active `deficit_flags` on a given Sol, THE System SHALL decrease that Astronaut's `health_score` by 2 points per active flag.
4. WHEN an Astronaut's computed `health_score` drops below 0, THE System SHALL clamp it to 0.
5. WHEN any Astronaut's `health_score` drops below 60, THE Orchestrator_Agent SHALL include a Crew_Health_Emergency flag in the DailyMissionReport.
6. THE System SHALL distribute daily nutritional output equally across all 4 Astronauts.

---

### Requirement 6: Data Model — Environment State

**User Story:** As a frontend developer, I want per-Sol environmental sensor readings, so that I can render the Environment Panel sparklines and Mars external conditions sidebar.

#### Acceptance Criteria

1. THE System SHALL write one `environment_state` record to DynamoDB per Sol with fields: `sol` (integer), `temperature_c` (number), `humidity_pct` (number), `co2_ppm` (number), `light_umol` (number), `water_efficiency_pct` (number), `energy_used_pct` (number), `external_temp_c` (number), `dust_storm_index` (number), and `radiation_msv` (number).
2. WHEN the backend is initialized at Sol 0, THE System SHALL seed `environment_state` with nominal values: `temperature_c = 22`, `humidity_pct = 65`, `co2_ppm = 1200`, `light_umol = 400`, `water_efficiency_pct = 92`, `energy_used_pct = 60`, `external_temp_c = -60`, `dust_storm_index = 0.0`, `radiation_msv = 0.3`.

---

### Requirement 7: Simulation Engine — Mars External Conditions Drift

**User Story:** As a simulation designer, I want Mars external conditions to drift realistically each Sol, so that the greenhouse environment is under continuous pressure.

#### Acceptance Criteria

1. WHEN a Sol is advanced, THE Simulation_Engine SHALL apply Drift to `external_temp_c` with drift magnitude ±8°C, hard minimum −125°C, and hard maximum +20°C.
2. WHEN a Sol is advanced, THE Simulation_Engine SHALL apply Drift to `dust_storm_index` with drift magnitude ±0.05, hard minimum 0.0, and hard maximum 1.0.
3. WHEN a Sol is advanced, THE Simulation_Engine SHALL apply Drift to `radiation_msv` with drift magnitude ±0.05, hard minimum 0.1, and hard maximum 0.7.

---

### Requirement 8: Simulation Engine — Internal Sensor Drift

**User Story:** As a simulation designer, I want greenhouse internal sensor readings to drift each Sol, so that the Environment Agent has realistic data to react to.

#### Acceptance Criteria

1. WHEN a Sol is advanced, THE Simulation_Engine SHALL apply Drift to `temperature_c` with drift magnitude ±1.5°C, hard minimum 10°C, and hard maximum 35°C.
2. WHEN a Sol is advanced, THE Simulation_Engine SHALL apply Drift to `humidity_pct` with drift magnitude ±3%, hard minimum 30%, and hard maximum 95%.
3. WHEN a Sol is advanced, THE Simulation_Engine SHALL apply Drift to `co2_ppm` with drift magnitude ±80 ppm, hard minimum 400 ppm, and hard maximum 2000 ppm.
4. WHEN a Sol is advanced, THE Simulation_Engine SHALL apply Drift to `light_umol` with drift magnitude ±20 µmol/m²/s, hard minimum 200 µmol/m²/s, and hard maximum 600 µmol/m²/s.
5. WHEN a Sol is advanced, THE Simulation_Engine SHALL apply Drift to `water_efficiency_pct` with drift magnitude ±1.5%, hard minimum 50%, and hard maximum 99%.
6. WHEN a Sol is advanced, THE Simulation_Engine SHALL apply Drift to `energy_used_pct` with drift magnitude ±2%, hard minimum 30%, and hard maximum 100%.

---

### Requirement 9: Simulation Engine — Mars-to-Greenhouse Cascade Effects

**User Story:** As a simulation designer, I want Mars external conditions to cascade into internal sensor readings, so that the simulation reflects realistic physical dependencies.

#### Acceptance Criteria

1. WHEN `dust_storm_index` exceeds 0.5 after drift, THE Simulation_Engine SHALL reduce `light_umol` proportionally by `(dust_storm_index - 0.5) * 2 * light_umol` before writing the Sol's environment state.
2. WHEN `external_temp_c` drops below −80°C after drift, THE Simulation_Engine SHALL increase `energy_used_pct` by `(-80 - external_temp_c) * 0.1` percentage points before writing the Sol's environment state.
3. WHEN `radiation_msv` exceeds 0.6 after drift, THE Simulation_Engine SHALL reduce `health` by 0.02 on all plots that do not have radiation shielding listed in `stress_flags`.

---

### Requirement 10: Simulation Engine — Probabilistic Crisis Roll

**User Story:** As a simulation designer, I want spontaneous crises to fire probabilistically each Sol, so that the agents feel necessary and the demo remains unpredictable.

#### Acceptance Criteria

1. WHEN a Sol is advanced, THE Simulation_Engine SHALL independently roll a random check for each of the 5 crisis types before agents run.
2. THE Simulation_Engine SHALL use the following per-Sol probabilities: `water_recycling_failure` at 0.8%, `energy_budget_cut` at 0.5%, `temperature_spike` at 1.2%, `disease_outbreak` at 0.6%, `co2_imbalance` at 0.9%.
3. WHEN `water_recycling_failure` fires, THE Simulation_Engine SHALL set `water_efficiency_pct` to 65%.
4. WHEN `energy_budget_cut` fires, THE Simulation_Engine SHALL increase `energy_used_pct` by 40 percentage points, clamped to 100%.
5. WHEN `temperature_spike` fires, THE Simulation_Engine SHALL set `temperature_c` to 30°C.
6. WHEN `disease_outbreak` fires, THE Simulation_Engine SHALL reduce `health` by 0.3 on all plots in a randomly selected zone and add `"disease"` to their `stress_flags`.
7. WHEN `co2_imbalance` fires, THE Simulation_Engine SHALL set `co2_ppm` to 1900 ppm.
8. WHEN a crisis fires, THE Simulation_Engine SHALL add the crisis type string to `crises_active` in the Sol's `sol_reports` record.

---

### Requirement 11: Simulation Engine — Crop Growth Model

**User Story:** As a simulation designer, I want crops to grow, stress, and yield realistically each Sol, so that the nutritional output reflects actual greenhouse performance.

#### Acceptance Criteria

1. WHEN a Sol is advanced, THE Simulation_Engine SHALL increment the age of each plot by 1 Sol.
2. WHEN any internal sensor reading is outside its optimal band during a Sol, THE Simulation_Engine SHALL apply a stress multiplier to the affected plots' `health` as defined in MCP_KB document 04.
3. WHEN a plot's age reaches `harvest_sol - planted_sol`, THE Simulation_Engine SHALL calculate yield as `area_m2 * base_yield_per_m2 * health`, where `base_yield_per_m2` is sourced from MCP_KB.
4. WHEN a plot is harvested, THE Simulation_Engine SHALL record the yield in the Sol's `sol_reports` and reset the plot for the next planting cycle.

---

### Requirement 12: Simulation Engine — Nutritional Output Calculation

**User Story:** As a simulation designer, I want harvested crop yields to be converted to nutritional values each Sol, so that the Nutrition Agent has accurate data to work with.

#### Acceptance Criteria

1. WHEN a plot is harvested during a Sol, THE Simulation_Engine SHALL convert yield mass to `kcal`, `protein_g`, `vitamin_a`, `vitamin_c`, `vitamin_k`, and `folate` using the nutritional profiles from MCP_KB document 03.
2. THE Simulation_Engine SHALL sum nutritional values across all harvests in a Sol and write the totals to the `nutrition_ledger` record for that Sol.

---

### Requirement 13: REST API — Run Sol Endpoint

**User Story:** As a frontend developer, I want a `POST /run-sol` endpoint, so that I can advance the simulation by one Sol and receive the updated mission state.

#### Acceptance Criteria

1. THE Sol_API SHALL expose a `POST /run-sol` endpoint backed by a Lambda function.
2. WHEN `POST /run-sol` is called, THE Sol_API SHALL execute the Simulation_Engine steps in this exact order: (1) Mars external conditions drift, (2) internal sensor drift, (3) cascade effects, (4) probabilistic crisis roll, (5) crop growth, (6) nutritional output calculation, (7) resource consumption, (8) run all agents, (9) write state snapshot to DynamoDB.
3. WHEN `POST /run-sol` completes successfully, THE Sol_API SHALL return HTTP 200 with a JSON body containing the updated `mission_state`, `environment_state`, `nutrition_ledger`, and `sol_reports` for the completed Sol.
4. IF an unhandled error occurs during `POST /run-sol`, THEN THE Sol_API SHALL return HTTP 500 with a JSON error body containing a `message` field and the current `sol` number.
5. WHEN `POST /run-sol` completes, THE Sol_API SHALL publish the updated state to all connected WebSocket_API clients.

---

### Requirement 14: REST API — Inject Crisis Endpoint

**User Story:** As a demo operator, I want a `POST /inject-crisis` endpoint, so that I can manually trigger a specific crisis type during a live demo.

#### Acceptance Criteria

1. THE Sol_API SHALL expose a `POST /inject-crisis` endpoint that accepts a JSON body with a `type` field set to one of: `water_recycling_failure`, `energy_budget_cut`, `temperature_spike`, `disease_outbreak`, `co2_imbalance`.
2. WHEN `POST /inject-crisis` is called with a valid `type`, THE Sol_API SHALL immediately apply the corresponding crisis state change to the current `environment_state` and `greenhouse_plots` in DynamoDB, identical to the effect defined in Requirement 10.
3. WHEN `POST /inject-crisis` is called with a valid `type`, THE Sol_API SHALL add the crisis type to `crises_active` in the current Sol's `sol_reports` record and update `mission_state.phase` to `"crisis"`.
4. WHEN `POST /inject-crisis` is called with a valid `type`, THE Sol_API SHALL return HTTP 200 with a JSON body confirming the injected crisis type and the updated `mission_state`.
5. IF `POST /inject-crisis` is called with an unrecognized `type` value, THEN THE Sol_API SHALL return HTTP 400 with a JSON error body containing a descriptive `message` field.

---

### Requirement 15: REST API — Chat Endpoint

**User Story:** As a frontend developer, I want a `POST /chat` endpoint, so that users can send natural language messages to the Orchestrator Agent with full mission context.

#### Acceptance Criteria

1. THE Sol_API SHALL expose a `POST /chat` endpoint that accepts a JSON body with a `message` field (string, 1–2000 characters).
2. WHEN `POST /chat` is called, THE Sol_API SHALL retrieve the current `mission_state`, the most recent `sol_reports`, `nutrition_ledger`, `environment_state`, and all 4 `crew_health` records for the current Sol from DynamoDB and include them as context in the Orchestrator_Agent prompt.
3. WHEN `POST /chat` is called, THE Sol_API SHALL invoke the Orchestrator_Agent with the user message and mission context and return HTTP 200 with a JSON body containing a `response` field (the agent's reply) and a `reasoning` field (the agent's reasoning chain).
4. IF `POST /chat` is called with a `message` field that is empty or exceeds 2000 characters, THEN THE Sol_API SHALL return HTTP 400 with a JSON error body containing a descriptive `message` field.
5. IF the Orchestrator_Agent call fails or times out after 30 seconds, THEN THE Sol_API SHALL return HTTP 503 with a JSON error body containing a `message` field.

---

### Requirement 16: WebSocket API — Real-Time Sol Updates

**User Story:** As a frontend developer, I want a WebSocket connection that pushes Sol state updates, so that the UI updates in real time without polling.

#### Acceptance Criteria

1. THE WebSocket_API SHALL support `$connect`, `$disconnect`, and `$default` route keys via API Gateway WebSocket.
2. WHEN a client connects to the WebSocket_API, THE WebSocket_API SHALL store the connection ID in DynamoDB.
3. WHEN a client disconnects from the WebSocket_API, THE WebSocket_API SHALL remove the connection ID from DynamoDB.
4. WHEN a Sol completes via `POST /run-sol`, THE System SHALL broadcast a JSON message to all active WebSocket connections containing the updated `mission_state`, `environment_state`, `nutrition_ledger`, and `crises_active` for the completed Sol.
5. IF a WebSocket connection ID is stale when a broadcast is attempted, THEN THE System SHALL remove the stale connection ID from DynamoDB and continue broadcasting to remaining connections.

---

### Requirement 17: Orchestrator Agent

**User Story:** As a mission operator, I want an Orchestrator Agent that coordinates all sub-agents each Sol, so that every decision is consolidated into a single auditable DailyMissionReport.

#### Acceptance Criteria

1. WHEN `POST /run-sol` triggers agent execution, THE Orchestrator_Agent SHALL invoke the Nutrition_Agent, Environment_Agent, Crisis_Agent, and Planner_Agent in sequence and collect their reports.
2. WHEN all sub-agent reports are collected, THE Orchestrator_Agent SHALL write a DailyMissionReport to the `sol_reports` record containing the NutritionReport, EnvironmentReport, CrisisReport, PlantingPlan, and a synthesized mission summary.
3. WHEN a Crew_Health_Emergency is detected, THE Orchestrator_Agent SHALL include a `crew_health_emergency: true` flag and the affected Astronaut identifiers in the DailyMissionReport.
4. THE Orchestrator_Agent SHALL use Claude 3.5 Sonnet via Amazon Bedrock as its LLM.
5. THE Orchestrator_Agent SHALL query MCP_KB using the provided MCP endpoint for any crop, nutritional, or environmental data needed to synthesize the mission summary.

---

### Requirement 18: Nutrition Agent

**User Story:** As a mission operator, I want a Nutrition Agent that tracks nutritional output and crew health each Sol, so that deficits are detected and flagged before they become emergencies.

#### Acceptance Criteria

1. WHEN invoked by the Orchestrator_Agent, THE Nutrition_Agent SHALL read the current Sol's `nutrition_ledger` from DynamoDB and compare `kcal` against the 12,000 kcal/day crew target and `protein_g` against the 450 g/day crew target.
2. WHEN invoked by the Orchestrator_Agent, THE Nutrition_Agent SHALL query MCP_KB for micronutrient targets and compare the current Sol's micronutrient values against those targets.
3. WHEN a nutritional value falls below its target, THE Nutrition_Agent SHALL add the corresponding deficit string to `deficit_flags` for each affected Astronaut in the `crew_health` record.
4. THE Nutrition_Agent SHALL compute the Nutritional_Coverage_Score and include it in the NutritionReport.
5. THE Nutrition_Agent SHALL compute updated Health_Score values for all 4 Astronauts and write them to the `crew_health` records for the current Sol.
6. WHEN any Astronaut's Health_Score drops below 60, THE Nutrition_Agent SHALL include a Crew_Health_Emergency signal in the NutritionReport.
7. THE Nutrition_Agent SHALL return a NutritionReport containing: `coverage_score`, `kcal_produced`, `protein_g`, `crew_health_statuses` (array of 4 per-Astronaut records), and `deficit_summary`.

---

### Requirement 19: Environment Agent

**User Story:** As a mission operator, I want an Environment Agent that reads sensor state and adjusts greenhouse setpoints each Sol, so that internal conditions stay within optimal bands.

#### Acceptance Criteria

1. WHEN invoked by the Orchestrator_Agent, THE Environment_Agent SHALL read the current Sol's `environment_state` from DynamoDB.
2. WHEN any internal sensor reading is outside its optimal band, THE Environment_Agent SHALL determine adjusted setpoints for CO₂ enrichment, LED photoperiod, temperature, and humidity using MCP_KB document constraints.
3. THE Environment_Agent SHALL return an EnvironmentReport containing: the current sensor readings, the recommended setpoint adjustments, and a reasoning string explaining each adjustment.
4. WHEN all internal sensor readings are within their optimal bands, THE Environment_Agent SHALL return an EnvironmentReport indicating nominal conditions with no adjustments required.

---

### Requirement 20: Crisis Agent

**User Story:** As a mission operator, I want a Crisis Agent that applies knowledge base playbooks to active crises, so that the greenhouse recovers within a predictable number of Sols.

#### Acceptance Criteria

1. WHEN invoked by the Orchestrator_Agent, THE Crisis_Agent SHALL read `crises_active` from the current Sol's `sol_reports`.
2. WHEN `crises_active` is empty, THE Crisis_Agent SHALL return a CrisisReport indicating no active crises and no actions taken.
3. WHEN `crises_active` contains one or more crisis types, THE Crisis_Agent SHALL query MCP_KB document 06 for the corresponding response playbook for each active crisis.
4. WHEN a playbook is retrieved, THE Crisis_Agent SHALL apply the containment actions defined in the playbook to the affected `greenhouse_plots` and `environment_state` records in DynamoDB.
5. THE Crisis_Agent SHALL return a CrisisReport containing: `crises_handled` (list of crisis types), `actions_taken` (list of action strings), `recovery_timeline_sols` (estimated Sols to recovery per crisis), and `reasoning`.

---

### Requirement 21: Planner Agent

**User Story:** As a mission operator, I want a Planner Agent that outputs a concrete planting plan each Sol, so that crop allocation dynamically responds to nutritional deficits and environmental conditions.

#### Acceptance Criteria

1. WHEN invoked by the Orchestrator_Agent, THE Planner_Agent SHALL receive the NutritionReport, EnvironmentReport, and CrisisReport as inputs.
2. THE Planner_Agent SHALL query MCP_KB for crop selection criteria, growth cycle durations, and space constraints.
3. WHEN no nutritional deficits are active, THE Planner_Agent SHALL output a PlantingPlan maintaining the baseline allocation: ~45% potato, ~25% beans, ~18% lettuce, ~12% radish/herbs across the 20 plots.
4. WHEN a protein deficit is active, THE Planner_Agent SHALL increase the beans allocation by at least 5 percentage points in the PlantingPlan.
5. WHEN a kcal deficit is active, THE Planner_Agent SHALL increase the potato allocation by at least 5 percentage points in the PlantingPlan.
6. THE Planner_Agent SHALL return a PlantingPlan containing: `plot_assignments` (array of 20 plot-to-crop mappings), `rationale` (string), and `projected_coverage_score_next_sol` (number).

---

### Requirement 22: MCP Knowledge Base Integration

**User Story:** As a system architect, I want all agents to query the MCP Knowledge Base for authoritative data, so that every agent decision is grounded in the provided Mars crop science.

#### Acceptance Criteria

1. THE System SHALL configure all agents to connect to the MCP_KB endpoint at `https://kb-start-hack-gateway-buyjtibfpg.gateway.bedrock-agentcore.us-east-2.amazonaws.com/mcp` using streamable HTTP transport.
2. WHEN an agent requires crop nutritional profiles, THE System SHALL retrieve them from MCP_KB document 03 rather than using hardcoded values.
3. WHEN an agent requires environmental constraint thresholds, THE System SHALL retrieve them from MCP_KB document 04 rather than using hardcoded values.
4. WHEN the Crisis_Agent requires a response playbook, THE System SHALL retrieve it from MCP_KB document 06.
5. IF the MCP_KB endpoint is unreachable during an agent call, THEN THE System SHALL log the error, fall back to the last successfully cached KB values, and include a `kb_fallback: true` flag in the affected agent's report.

---

### Requirement 23: Backend Initialization — Seed State

**User Story:** As a developer, I want a one-time initialization routine that seeds Sol 0 state, so that the simulation starts from a known nominal baseline.

#### Acceptance Criteria

1. THE System SHALL provide an initialization endpoint or script that seeds all DynamoDB tables with Sol 0 state.
2. WHEN initialization runs, THE System SHALL write the `mission_state` record as defined in Requirement 1, Criterion 2.
3. WHEN initialization runs, THE System SHALL write all 20 `greenhouse_plots` records as defined in Requirement 2, Criteria 2 and 3.
4. WHEN initialization runs, THE System SHALL write the Sol 0 `environment_state` record as defined in Requirement 6, Criterion 2.
5. WHEN initialization runs on a DynamoDB table that already contains data, THE System SHALL overwrite existing Sol 0 records without deleting records from subsequent Sols.

---

### Requirement 24: Amplify Gen2 Data Schema

**User Story:** As a developer, I want the DynamoDB tables defined in the Amplify Gen2 data schema, so that the frontend can use the generated Amplify Data client for reads.

#### Acceptance Criteria

1. THE System SHALL replace the placeholder `Todo` model in `OrbitGrow/amplify/data/resource.ts` with models for `MissionState`, `GreenhousePlot`, `SolReport`, `NutritionLedger`, `CrewHealth`, and `EnvironmentState` matching the fields defined in Requirements 1–6.
2. THE System SHALL configure authorization on all models to allow authenticated users to read all records and allow the backend Lambda functions to write all records.
3. WHEN the Amplify Gen2 schema is deployed, THE System SHALL generate TypeScript types for all models accessible to the frontend via the Amplify Data client.
