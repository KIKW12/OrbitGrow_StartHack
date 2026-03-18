# OrbitGrow — Build Plan
### Autonomous Martian Greenhouse Intelligence System

> **Mission:** Feed 4 astronauts for 450 days on Mars. Autonomously. Beautifully. Provably.

---

## The One-Line Pitch

> *OrbitGrow is an autonomous AI agent network that manages a Martian greenhouse in real time — optimizing crops, preventing crises, and explaining every decision — visualized as a living digital twin you can watch, challenge, and interrogate.*

---

## Why This Wins

The four judging criteria map perfectly to four distinct wow moments in the demo:

| Criterion (25% each) | Our wow moment |
|---|---|
| **Creativity** | Multi-agent colony with specialized roles + live crises + individual astronaut health degrading in real time |
| **Functional / Accuracy** | Every number traces back to the KB: real kcal targets, real crop cycles, real Mars conditions, real radiation exposure limits |
| **Visual Design** | Animated greenhouse digital twin, live telemetry panels, crew health cards, beautiful dark-space UI |
| **Presentation / Demo** | 3-minute story arc: crisis hits → agents detect → agents respond → crew health recovers → mission saved |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        OrbitGrow UI (React)                      │
│  ┌─────────────┐  ┌──────────────────┐  ┌─────────────────────┐ │
│  │  Greenhouse  │  │  Mission Control │  │   Mission Chat      │ │
│  │  Digital     │  │  Dashboard       │  │   (talk to the AI)  │ │
│  │  Twin (3D)   │  │  (telemetry)     │  │                     │ │
│  └─────────────┘  └──────────────────┘  └─────────────────────┘ │
└───────────────────────────┬─────────────────────────────────────┘
                            │ REST / WebSocket
┌───────────────────────────▼─────────────────────────────────────┐
│                   AgentCore Gateway (AWS)                         │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │               ORCHESTRATOR AGENT (Commander)                 │ │
│  │  Runs every simulated Sol (Martian day). Calls sub-agents.   │ │
│  │  Produces a DailyMissionReport. Stores decisions.            │ │
│  └──────┬──────────────┬─────────────────┬──────────────────┘  │ │
│         │              │                 │                       │
│  ┌──────▼──────┐ ┌─────▼──────┐ ┌───────▼──────┐               │
│  │  NUTRITION  │ │ ENVIRONMENT│ │   CRISIS     │               │
│  │  AGENT      │ │ AGENT      │ │   AGENT      │               │
│  │             │ │            │ │              │               │
│  │ Tracks kcal │ │ Monitors   │ │ Detects &    │               │
│  │ protein     │ │ temp/CO₂/  │ │ responds to  │               │
│  │ micronutri- │ │ humidity/  │ │ water failure │               │
│  │ ents vs     │ │ light      │ │ power cuts   │               │
│  │ crew needs  │ │ adjusts    │ │ disease       │               │
│  └──────┬──────┘ └─────┬──────┘ └───────┬──────┘               │
│         └──────────────▼─────────────────┘                      │
│                  ┌──────────────┐                                │
│                  │  PLANNER     │                                │
│                  │  AGENT       │                                │
│                  │              │                                │
│                  │ Decides next │                                │
│                  │ Sol's crop   │                                │
│                  │ allocation   │                                │
│                  │ & parameters │                                │
│                  └──────┬───────┘                                │
└─────────────────────────┼───────────────────────────────────────┘
                          │
          ┌───────────────▼────────────────┐
          │  MCP Knowledge Base (AgentCore) │
          │  Mars crops, nutrition, enviro  │
          │  scenarios, stress responses    │
          └───────────────┬────────────────┘
                          │
          ┌───────────────▼────────────────┐
          │  DynamoDB — Mission State        │
          │  • greenhouse_state (per Sol)    │
          │  • crop_plots (current crops)    │
          │  • agent_decisions (audit log)   │
          │  • crew_nutrition_ledger         │
          └────────────────────────────────┘
```

---

## The Five Agents

### 1. Orchestrator (Commander)
- Runs once per simulated Sol
- Calls all sub-agents in sequence, collects their reports
- Writes a `DailyMissionReport` to DynamoDB with every decision and rationale
- Exposes a `/run-sol` endpoint the frontend calls to advance the simulation

### 2. Nutrition Agent
- Reads current crop inventory and projected yields from DynamoDB
- Queries the MCP KB: kcal per 100g, protein per crop, micronutrient profiles
- Computes daily nutritional output vs. crew target (12,000 kcal/day, 360–540g protein/day)
- Divides daily output across the 4 astronauts (equal split) and updates each crew member's health ledger
- Health score per astronaut: starts at 100, drops 2pts/Sol per active deficit flag, recovers 1pt/Sol when all targets met
- If any astronaut health score drops below 60, flags a crew health emergency in the report
- Returns a `NutritionReport` with the mission-level **Nutritional Coverage Score** (0–100) and individual `CrewHealthStatus[]` per astronaut

### 3. Environment Agent
- Monitors Mars environmental parameters: 24.6h sol, reduced gravity (0.38g), radiation cycles, temperature swings
- Reads the current Sol's sensor readings from DynamoDB (already drifted by the simulation engine)
- Adjusts setpoints: CO₂ enrichment, LED photoperiod, temperature, humidity
- Returns `EnvironmentReport` with adjusted parameters and reasoning

### 4. Crisis Agent
- Each Sol, the simulation engine rolls probabilistic crisis checks before agents run
- If a crisis fires (or is manually injected), this agent receives the anomaly signal
- Applies response playbooks sourced from the MCP KB (doc 06: Operational Scenarios)
- Handles: water recycling failure, energy budget reduction, temperature drift, CO₂ imbalance, disease risk
- Returns `CrisisReport` with containment actions and recovery timeline
- **This is the most impressive demo moment** — inject a crisis in real time and watch the agent respond

### 5. Planner Agent
- Takes all three reports above
- Queries MCP KB for crop selection criteria, growth cycles, space constraints
- Outputs a concrete `PlantingPlan` for the next Sol: crop ratios, zone assignments, parameter targets
- Uses the strategic allocation model: ~45% potatoes, ~25% legumes, ~18% leafy greens, ~12% radish/herbs
- Dynamically shifts ratios when deficits are detected

---

## Simulation Engine

The greenhouse simulation runs in DynamoDB. Each Sol tick advances in this exact order:

### Step 1 — Mars External Conditions Drift
Mars external variables shift every Sol via bounded random drift. These feed into the greenhouse environment as pressure on the internal systems.

```
new_value = current_value + random(−drift, +drift)
new_value = clamp(new_value, hard_min, hard_max)
```

| Variable | Start (Sol 0) | Drift/Sol | Hard Min | Hard Max |
|---|---|---|---|---|
| External temperature | −60°C | ±8°C | −125°C | +20°C |
| Dust storm index | 0.0 | ±0.05 | 0.0 | 1.0 |
| Radiation level | 0.3 mSv/day | ±0.05 | 0.1 | 0.7 |

### Step 2 — Internal Sensor Readings Drift
Greenhouse internal readings drift within their optimal bands each Sol. This is what the Environment Agent reads and reacts to.

| Variable | Start (Sol 0) | Optimal Band | Drift/Sol | Hard Min | Hard Max |
|---|---|---|---|---|---|
| Temperature | 22°C | 18–26°C | ±1.5°C | 10°C | 35°C |
| Humidity | 65% | 55–75% | ±3% | 30% | 95% |
| CO₂ | 1200 ppm | 900–1500 ppm | ±80 ppm | 400 | 2000 |
| Light intensity | 400 µmol/m²/s | 350–450 µmol | ±20 µmol | 200 | 600 |
| Water recycling efficiency | 92% | >85% | ±1.5% | 50% | 99% |
| Energy budget used | 60% | <80% | ±2% | 30% | 100% |

Mars external conditions cascade into internal readings:
- **Dust storm index > 0.5** → light intensity drops proportionally
- **External temp < −80°C** → heating load increases → energy budget pressure rises
- **Radiation > 0.6 mSv/day** → crop health degrades 0.02/Sol on exposed plots

### Step 3 — Probabilistic Crisis Roll
Before agents run, the engine rolls for spontaneous crises. Low per-Sol probability, but over 450 Sols multiple will naturally fire — making the agents feel necessary, not decorative.

| Crisis | Probability/Sol | Trigger condition |
|---|---|---|
| Water recycling failure | 0.8% | water_efficiency drops to 65% |
| Energy budget cut | 0.5% | energy_used spikes by 40% |
| Temperature spike | 1.2% | temp jumps to 30°C |
| Disease outbreak | 0.6% | health −0.3 on a random zone |
| CO₂ imbalance | 0.9% | CO₂ jumps to 1900 ppm |

Manual crisis injection (keyboard shortcuts) overrides this and fires immediately.

### Step 4 — Crop Growth
Each plot advances 1 Sol. On maturity, yield is calculated based on area, base yield/m², and any environmental stress multipliers applied that Sol. If any sensor reading was outside its optimal band this Sol, yield is penalized per the stress response rules in MCP doc 04.

### Step 5 — Nutritional Output
Sum of harvests converted to kcal, protein, and micronutrients using MCP doc 03 tables.

### Step 6 — Resource Consumption
Water and energy calculated per crop type and area.

### Step 7 — State Snapshot
All values written to DynamoDB with timestamp, triggering a frontend WebSocket push.

The simulation can be run in **demo speed** (1 Sol per button press) or **fast-forward** (auto-runs at 1 Sol/second to show the full 450-day arc).

---

## Initial Greenhouse State (Sol 0)

All values start at nominal average. The story starts green — crises and drift make it interesting.

**Crop plots — 20 plots seeded at fixed ratios:**
- ~45% potatoes (9 plots)
- ~25% legumes/beans (5 plots)
- ~18% leafy greens/lettuce (4 plots)
- ~12% radish/herbs (2 plots)

**All sensor readings at nominal (see table above).**
**All crop health at 1.0.**
**No active crises.**

---

## Crisis Injection System (Demo Secret Weapon)

A hidden panel (or keyboard shortcut) lets you inject crises mid-demo on top of the probabilistic system:

| Shortcut | Crisis |
|---|---|
| `W` | Water recycling drops to 65% |
| `E` | Energy budget cut by 40% |
| `T` | Temperature spike to 30°C |
| `D` | Disease detected in Zone B |
| `C` | CO₂ imbalance — reading too high |

The next Sol tick triggers the Crisis Agent, which responds live in the Decision Log and updates the Digital Twin visually (affected zone turns red, crops start showing stress indicators). Within 2–3 Sols, the agent brings the system back to green.

**During the demo:** inject a water failure mid-presentation, pause, ask the audience "what do you think will happen?" — then step forward one Sol and show the agent's response. This is a guaranteed wow moment.

---

## Frontend — The Digital Twin

### Screen 1: Greenhouse Visualization (the hero)

A top-down animated grid of the greenhouse floor (SVG or Three.js):
- Each cell is a crop plot, colored by crop type and growth stage
- Crops visually grow over Sols (seedling → mature → harvest)
- Hovering a plot shows: crop, days until harvest, health status, current yield forecast
- Zones pulse red/amber/green based on sensor health
- A running Sol counter with a Mars clock in the top bar
- Playback controls: **Step Sol**, **Auto-Run** (1 Sol/second), **Pause**

### Screen 2: Mission Control Dashboard

A multi-panel telemetry view:

**Nutrition Panel**
- Donut chart: Nutritional Coverage Score (animated fill, color transitions)
- Bar chart: kcal produced vs. 12,000 kcal target today
- Protein gauge: grams/day vs. 360g target
- Micronutrient heatmap: Vitamin A, C, K, Folate, Iron — green/amber/red

**Crew Health Panel**
- 4 astronaut cards: Commander, Scientist, Engineer, Pilot
- Each card shows: health score bar (green/amber/red), kcal/day received, protein/day, active deficit flags
- Cards pulse amber/red when a deficit flag is active — makes degradation immediately visible during demo

**Resources Panel**
- Water recycling efficiency % (target >90%)
- Energy budget bar (consumed vs. available)
- Area utilization by crop type

**Environment Panel**
- Live sparklines: temperature, humidity, CO₂, light intensity
- Optimal range bands shown as shaded zones
- Any parameter outside range glows red
- Mars external conditions sidebar: external temp, dust storm index, radiation level

**Timeline Panel**
- Full 450-Sol mission timeline bar
- Harvest events marked as gold ticks
- Crisis events marked as red lightning bolts
- Nutritional coverage score charted over the entire mission arc

### Screen 3: Agent Decision Log

A chronological feed of every agent decision:
```
Sol 14 — Nutrition Agent
⚠️  Protein deficit detected: 280g/day vs. 360g target
→  Increasing legume allocation from 20% → 30%
→  Adjusting nitrogen solution to support pod development
→  Projected recovery by Sol 28

Sol 15 — Crisis Agent
🔴  Water recycling efficiency dropped to 78% (threshold: 85%)
→  Reducing irrigation frequency by 30%
→  Prioritizing potatoes and beans over lettuce
→  Diagnostic routine initiated
```

Each entry is expandable to show the full agent reasoning chain (the LLM output verbatim).

### Screen 4: Mission Chat

A chat interface with the Orchestrator Agent as the persona.

Not just Q&A — the agent has full mission context. Example exchanges:
- *"Why did you reduce lettuce last week?"* → Explains the protein deficit decision
- *"What happens if the water system fails tomorrow?"* → Runs a hypothetical simulation
- *"Are we on track to feed the crew?"* → Full nutritional projection report
- *"Plant more herbs"* → Operator override, agent acknowledges, adjusts plan, explains tradeoffs

The chat is the explainability layer. Judges love being able to ask "why."

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Frontend | React + Vite + TailwindCSS | Fast dev, beautiful dark UI |
| Visualization | SVG grid + Framer Motion | Smooth crop growth animations |
| Charts | Recharts | Easy, good-looking telemetry |
| Hosting | AWS Amplify Gen2 | One-command deploy |
| Agents | Python + Strands Agents SDK | Hackathon-recommended, Kiro-native |
| Agent hosting | AWS Bedrock AgentCore | Required by challenge |
| Agent LLM | Claude 3.5 Sonnet (via Bedrock) | Best reasoning for planning tasks |
| Knowledge base | MCP over streamable HTTP | Provided AgentCore endpoint |
| State store | DynamoDB | Scalable, Amplify-native |
| Real-time push | API Gateway WebSocket | Live Sol updates to frontend |
| Agent API | Lambda + API Gateway REST | `/run-sol`, `/inject-crisis`, `/chat` |

---

## Data Model (DynamoDB)

### `mission_state`
```
pk: "MISSION"
current_sol: number
phase: "nominal" | "crisis" | "recovery"
last_updated: ISO timestamp
```

### `greenhouse_plots`
```
pk: "PLOT#{zone}#{index}"
crop: "lettuce" | "potato" | "beans" | "radish" | "herbs"
planted_sol: number
harvest_sol: number
area_m2: number
health: 0.0–1.0
stress_flags: string[]
```

### `sol_reports`
```
pk: "SOL#{number}"
nutrition_score: number
kcal_produced: number
protein_g: number
water_efficiency: number
energy_used: number
agent_decisions: JSON[]
crises_active: string[]
```

### `nutrition_ledger`
```
pk: "NUTRITION#{sol}"
kcal: number
protein_g: number
vitamin_a: number
vitamin_c: number
vitamin_k: number
folate: number
coverage_score: number
```

### `crew_health`
```
pk: "CREW#{astronaut_id}#{sol}"
astronaut: "commander" | "scientist" | "engineer" | "pilot"
kcal_received: number
protein_g: number
vitamin_a: number
vitamin_c: number
vitamin_k: number
folate: number
health_score: number        # 0–100, starts at 100 on Sol 0
deficit_flags: string[]     # e.g. ["protein_low", "vitamin_c_deficient"]
```

### `environment_state`
```
pk: "ENV#{sol}"
# Internal greenhouse readings
temperature_c: number
humidity_pct: number
co2_ppm: number
light_umol: number
water_efficiency_pct: number
energy_used_pct: number
# Mars external conditions
external_temp_c: number
dust_storm_index: number
radiation_msv: number
```

---

## Build Order (Hackathon Sprint Plan)

### Phase 1 — Foundation (first 3 hours)
- [ ] Scaffold React app with Amplify Gen2
- [ ] Set up DynamoDB tables (including `environment_state`)
- [ ] Configure MCP server in `.kiro/settings/mcp.json`
- [ ] Write Strands agent skeletons (Orchestrator + 4 sub-agents)
- [ ] Build `/run-sol` Lambda endpoint
- [ ] Seed initial greenhouse state: 20 plots at nominal values, Sol 0

### Phase 2 — Agent Logic (next 4 hours)
- [ ] Implement Nutrition Agent: queries KB for kcal/protein, computes coverage score
- [ ] Extend Nutrition Agent: divide output across 4 astronauts, compute per-astronaut health scores, write to `crew_health`
- [ ] Implement Environment Agent: reads drifted sensor state, adjusts setpoints
- [ ] Implement Crisis Agent: applies KB scenario playbooks to active crises
- [ ] Implement Planner Agent: outputs concrete planting plan
- [ ] Implement Orchestrator: calls all agents, writes DailyMissionReport (includes crew health emergency flag if any score < 60)
- [ ] Wire MCP KB queries into each agent

### Phase 3 — Simulation Engine (next 2 hours)
- [ ] Mars external conditions drift (Step 1): external temp, dust storm, radiation
- [ ] Internal sensor drift (Step 2): temp, humidity, CO₂, light, water, energy
- [ ] Mars→greenhouse cascade effects (dust→light, cold→energy)
- [ ] Probabilistic crisis roll (Step 3): per-Sol random checks
- [ ] Crop growth model (Step 4): advance Sol, stress multipliers, yield at harvest
- [ ] Resource consumption tracking (Step 6): water, energy
- [ ] Crisis injection endpoint: `/inject-crisis?type=water`

### Phase 4 — Frontend (next 4 hours)
- [ ] Greenhouse grid: SVG plots, crop colors, growth stage animation
- [ ] Mission Control dashboard: charts, gauges, telemetry sparklines
- [ ] Mars external conditions sidebar in Environment Panel
- [ ] Crew Health Panel: 4 astronaut cards with health score, kcal/day, protein/day, deficit flags
- [ ] Agent Decision Log: real-time feed from DynamoDB
- [ ] Sol controls: Step, Auto-Run, Pause, Fast-Forward
- [ ] Crisis injection UI (hidden panel)

### Phase 5 — Chat Interface (next 2 hours)
- [ ] Chat input → `/chat` Lambda → Orchestrator Agent with full mission context
- [ ] Agent has access to current sol_reports, nutrition_ledger, and environment_state
- [ ] Render reasoning chain in expandable chat messages

### Phase 6 — Polish & Demo Prep (final 3 hours)
- [ ] Dark space-themed UI: deep navy/black, orange/amber accents, star field background
- [ ] Smooth animations on all state transitions
- [ ] Amplify deploy to production URL
- [ ] Practice crisis injection demo flow
- [ ] Prepare 3-minute pitch narrative

---

## Presentation Narrative (3-minute script structure)

**0:00 – 0:30 — The Problem**
> "It's Sol 1. Four astronauts have landed on Mars. Their food supply lasts 200 days. The greenhouse needs to produce the rest — for 450 days — autonomously, scientifically, reliably."

**0:30 – 1:00 — The System**
> Show the architecture slide. "OrbitGrow is a colony of four specialized AI agents. They argue, negotiate, and agree on what to plant, how to grow it, and how to survive every crisis Mars throws at them."

**1:00 – 2:00 — The Demo (live)**
> - Show the greenhouse on Sol 1. Press Step Sol a few times. Watch crops grow and sensors drift.
> - Show the nutrition dashboard — coverage score climbing as first harvests come in.
> - Inject a water failure. "Watch what happens."
> - Step one Sol. Show the Crisis Agent response in the log. Show the digital twin zones turn red, then amber, then green.
> - Open the chat. Ask: "Are the astronauts going to make it?" Watch the agent analyze and answer.

**2:00 – 2:30 — The Science**
> "Every number is real. The 12,000 kcal daily target. The 360g protein requirement. The water recycling threshold. The Mars radiation levels. All sourced from the Syngenta knowledge base via MCP."

**2:30 – 3:00 — The Bigger Picture**
> "This system doesn't just solve Mars. The same autonomous optimization logic applies to vertical farms in drought zones, precision agriculture in climate-stressed regions, food security everywhere. OrbitGrow is the future of farming — tested on the hardest environment imaginable."

---

## Differentiators vs. Every Other Team

1. **Multi-agent architecture** — not one chatbot, but a colony of specialists that coordinate. This matches how real autonomous systems are built and how Syngenta's scientists think about AI.

2. **Live crisis injection** — most teams will show a static simulation. We let the judges break our greenhouse mid-demo and watch it heal itself.

3. **Full decision audit trail** — every agent decision is logged with reasoning. This is the "explainability" that NASA would actually require in a real system.

4. **Operator chat with mission context** — the agent isn't just answering generic questions; it knows it's Sol 47, protein is at 89% coverage, and Zone B just recovered from a disease event. It answers accordingly.

5. **Scientific grounding** — the nutritional coverage score, the crop allocation percentages, the environmental thresholds — all pulled from the provided KB via MCP. Judges from Syngenta will recognize their own data.

6. **Earth angle** — the closing pitch connects Martian agriculture to Syngenta's core business. Drought resilience, precision resource use, autonomous crop management — these are real Syngenta problems. This team understands the business, not just the tech.

---

## Nutritional Coverage Score (The KPI That Tells the Story)

This single number is the mission's heartbeat. Show it prominently at all times.

```
Coverage Score = (
  (kcal_produced / 12000) * 0.40 +
  (protein_g / 450) * 0.35 +
  (micronutrient_composite / target) * 0.25
) * 100
```

- **< 60**: Red alert — mission at risk
- **60–79**: Amber — agents actively correcting
- **80–94**: Green — on track
- **95–100**: Gold — mission optimal

When you start the demo at Sol 1 and fast-forward to Sol 450 with the score ending above 90, that is your closing visual. The mission was a success. The astronauts survived. OrbitGrow did it.
