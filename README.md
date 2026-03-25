# 🌱 OrbitGrow — Autonomous Martian Greenhouse Intelligence

> **Mission:** Feed 4 astronauts for 450 days on Mars. Autonomously. Provably.

OrbitGrow is an autonomous AI agent network that manages a Martian greenhouse in real time — optimizing crop allocation, preventing crises, tracking crew nutrition, and explaining every decision. The system is visualized as a living digital twin you can watch, challenge, and interrogate.

Built for **STARTHack 2026** (Syngenta challenge) • Powered by **AWS Bedrock + Claude** • Grounded in the **Syngenta MCP Knowledge Base**

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                     OrbitGrow UI (React SPA)                     │
│   Greenhouse Digital Twin  ·  Mission Control  ·  Mission Chat   │
└────────────────────────────────┬─────────────────────────────────┘
                                 │  REST + WebSocket
┌────────────────────────────────▼─────────────────────────────────┐
│                    Backend (FastAPI / AWS SAM)                   │
│                                                                  │
│  ┌───────────────────── ORCHESTRATOR ─────────────────────────┐  │
│  │  Runs each simulated Sol. Invokes sub-agents in sequence.  │  │
│  │  Produces a DailyMissionReport. Stores all decisions.      │  │
│  └───┬──────────┬──────────┬──────────┬──────────┬────────────┘  │
│      │          │          │          │          │               │
│  ┌───▼───┐  ┌───▼───┐  ┌───▼───┐  ┌───▼───┐  ┌───▼───┐           │
│  │NUTRI- │  │ENVIRO-│  │CRISIS │  │PLANNER│  │VISION │           │
│  │TION   │  │NMENT  │  │       │  │       │  │       │           │
│  │Agent  │  │Agent  │  │Agent  │  │Agent  │  │Agent  │           │
│  └───────┘  └───────┘  └───────┘  └───────┘  └───────┘           │
│                                                                  │
│           MCP Client  ──▶  Syngenta Knowledge Base               │
│           Simulation Engine (sim_engine.py)                      │
│           DynamoDB  (mission · plots · environment · ledger · …) │
└──────────────────────────────────────────────────────────────────┘
```

---

## Agent Roles

| Agent | Responsibility |
|---|---|
| **Orchestrator** | Runs the Sol loop: advance simulation → call all sub-agents → compile the Sol report → push via WebSocket |
| **Nutrition** | Tracks kcal, protein, vitamins A/C/K, and folate vs crew daily targets. Identifies deficits and recommends crop mix changes |
| **Environment** | Monitors temperature, humidity, CO₂, and light. Detects when readings leave optimal bands and adjusts parameters |
| **Crisis** | Detects emergent crises (water failure, energy cut, disease outbreak, CO₂ imbalance, temperature spike) and executes KB-grounded containment playbooks |
| **Planner** | Decides next-Sol crop allocation, replanting schedules, and harvest timing to maximize nutritional coverage over the mission horizon |
| **Vision** | Interprets computer vision analysis results on crop images. Provides KB-grounded treatment plans and mission-impact assessments |

All agents use **Claude** (via AWS Bedrock / Strands SDK) and ground their reasoning in the **Syngenta MCP Knowledge Base**.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | React (Vite), single-page dark-space themed dashboard |
| **Backend (local)** | Python, FastAPI (CORS-enabled, serves REST + chat) |
| **Backend (prod)** | AWS SAM — Lambda functions + API Gateway (REST & WebSocket) |
| **AI / LLM** | Claude Sonnet 4.5 via AWS Bedrock (Strands Agents SDK) |
| **Knowledge Base** | Syngenta MCP endpoint (streamable HTTP, AgentCore) |
| **Database** | DynamoDB — 6 tables: mission state, greenhouse plots, environment, nutrition ledger, crew health, sol reports |
| **Vision layer** | OpenCV + Pillow + NumPy (packaged as a Lambda layer) |
| **IaC** | AWS SAM `template.yaml` |

---

## Project Structure

```
OrbitGrow_StartHack/
├── PLAN.md                        # Detailed build plan & architecture
├── README.md                      # ← You are here
│
└── OrbitGrow/
    ├── agents/                    # AI agents (Python)
    │   ├── orchestrator.py        # Sol-loop coordinator
    │   ├── nutrition_agent.py     # Calorie & micronutrient tracker
    │   ├── environment_agent.py   # Climate control
    │   ├── crisis_agent.py        # Crisis detection & containment
    │   ├── planner_agent.py       # Crop allocation optimizer
    │   ├── vision_agent.py        # Plant health advisor (CV results)
    │   └── mcp_client.py          # MCP Knowledge Base client + structured data
    │
    ├── simulation/
    │   └── sim_engine.py          # Mars greenhouse simulation engine
    │
    ├── lambdas/                   # Lambda function handlers
    │   ├── run_sol/               # Advance one Sol
    │   ├── init_mission/          # Initialize a new 450-sol mission
    │   ├── get_state/             # Read current mission state
    │   ├── inject_crisis/         # Trigger a crisis event
    │   ├── chat/                  # Mission Chat (Claude-powered Q&A)
    │   ├── auto_sim/              # Continuous simulation runner
    │   ├── sim_control/           # Start/stop/reset simulation
    │   └── ws_handler/            # WebSocket connect/disconnect
    │
    ├── infrastructure/
    │   └── template.yaml          # AWS SAM template (Lambdas, DynamoDB, APIs)
    │
    ├── layer/                     # Shared Lambda layer (strands, mcp, boto3)
    ├── vision_layer/              # CV Lambda layer (opencv, pillow, numpy)
    │
    ├── frontend/                  # React SPA
    │   ├── src/
    │   │   ├── App.jsx            # Main app — dashboard layout
    │   │   ├── GreenhouseView.jsx # 3D greenhouse digital twin
    │   │   ├── MissionChat.jsx    # Chat with the AI agents
    │   │   └── index.css          # Dark-space themed styles
    │   └── package.json
    │
    ├── local_api.py               # FastAPI dev server (runs locally)
    └── samconfig.toml             # SAM deployment config
```

---

## Getting Started

### Prerequisites

- **Python 3.11+**
- **Node.js 18+** and **npm**
- **AWS CLI** configured with credentials (for production deployment)
- **AWS SAM CLI** (for `sam build` / `sam deploy`)

### 1. Run Locally (FastAPI)

```bash
cd OrbitGrow

# Install Python dependencies
pip install fastapi uvicorn strands-agents strands-agents-tools "mcp[cli]" boto3 opencv-python-headless pillow numpy

# Start the API server
python local_api.py
```

The API runs at `http://localhost:8000`. Key endpoints:

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/init` | Initialize a new mission |
| `POST` | `/sol` | Advance one Sol |
| `GET`  | `/state` | Get current mission state |
| `POST` | `/crisis` | Inject a crisis event |
| `POST` | `/chat` | Send a message to Mission Chat |
| `POST` | `/sim/start` | Start continuous simulation |
| `POST` | `/sim/stop` | Pause simulation |
| `POST` | `/sim/reset` | Reset the mission |

### 2. Run the Frontend

```bash
cd OrbitGrow/frontend
npm install
npm run dev
```

Open the URL shown in the terminal (typically `http://localhost:5173`).

### 3. Deploy to AWS

```bash
cd OrbitGrow
sam build
sam deploy --guided
```

This provisions all Lambdas, DynamoDB tables, REST API Gateway, and WebSocket API from `infrastructure/template.yaml`.

---

## How It Works

1. **Initialize** — `POST /init` creates a fresh 450-sol mission with 12 greenhouse plots (2–3 of each crop: potato, beans, lettuce, radish, herbs) and seeds all DynamoDB tables.

2. **Each Sol** — The Orchestrator runs through 7 steps:
   - Advance the simulation engine (weather drift, crop growth, random events)
   - **Nutrition Agent** calculates daily yield vs. crew caloric & micronutrient targets
   - **Environment Agent** checks climate readings against optimal bands
   - **Crisis Agent** detects and responds to emergencies with KB-grounded playbooks
   - **Vision Agent** reviews CV analysis results and recommends treatments
   - **Planner Agent** proposes next-Sol crop allocation changes
   - Compile everything into a **Sol Report** and push to clients via WebSocket

3. **Mission Chat** — Ask Claude questions about the mission. The agent has full context on current state, plots, environment, nutrition, and crises.

4. **Crisis Injection** — Trigger events manually (`water_recycling_failure`, `energy_budget_cut`, `disease_outbreak`, `temperature_spike`, `co2_imbalance`) to stress-test the agents.

---

## Knowledge Base

All agents ground their reasoning in the **Syngenta MCP Knowledge Base**, accessed via a streamable HTTP MCP endpoint:

```
https://kb-start-hack-gateway-buyjtibfpg.gateway.bedrock-agentcore.us-east-2.amazonaws.com/mcp
```

The KB covers:
- **Crop nutritional profiles** (kcal, protein, vitamins per kg)
- **Environmental optimal bands** (temperature, humidity, CO₂, light)
- **Crop growth parameters** (yield per m², harvest cycle in sols)
- **Crisis response playbooks** (containment actions, recovery timelines)
- **Plant health & disease management**

Structured data verified against the KB is also hardcoded in `mcp_client.py` for the simulation engine, ensuring deterministic behavior even when the KB endpoint is unreachable.

---

## Environment Variables (Production)

Set automatically by the SAM template:

| Variable | Purpose |
|---|---|
| `MISSION_STATE_TABLE` | DynamoDB table for mission-level state |
| `GREENHOUSE_PLOTS_TABLE` | DynamoDB table for crop plot data |
| `ENVIRONMENT_STATE_TABLE` | DynamoDB table for climate readings |
| `NUTRITION_LEDGER_TABLE` | DynamoDB table for daily nutrition tracking |
| `CREW_HEALTH_TABLE` | DynamoDB table for astronaut health metrics |
| `SOL_REPORTS_TABLE` | DynamoDB table for daily Sol reports |
| `WS_CONNECTIONS_TABLE` | DynamoDB table for active WebSocket connections |
| `WEBSOCKET_API_ENDPOINT` | WebSocket API URL for push notifications |

---

## License

Built for STARTHack 2025 — Syngenta/AWS Challenge Track.
