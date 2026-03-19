# OrbitGrow — Pitch Guide

> **3-minute pitch + live demo for StartHack 2026 — Syngenta Track: "Agriculture on Mars"**
> Judging: Creativity 25% | Functional Accuracy 25% | Visual Design 25% | Presentation 25%

---

## The One-Liner

**OrbitGrow is a multi-agent AI system that autonomously manages a Martian greenhouse to feed 4 astronauts over a 450-sol mission — grounded in real Syngenta agricultural science, with human-in-the-loop astronaut oversight.**

---

## 1. The Problem (30 seconds)

NASA targets sending astronauts to Mars by the late 2030s. A 450-day surface mission requires growing food in the most hostile environment humans have ever farmed in:

- **-60°C** outside, dust storms, radiation
- **No resupply** — what you grow is what you eat
- **4 astronauts** need 12,000 kcal/day, 450g protein, and critical vitamins (A, C, K, folate)
- Pre-packaged food covers calories but **vitamins degrade in storage** — the greenhouse is the crew's lifeline for micronutrients

One failed harvest could mean malnutrition. One undetected disease could wipe out an entire crop zone. The system managing this greenhouse can't afford to be simple.

---

## 2. Our Solution: OrbitGrow (60 seconds)

OrbitGrow is a **digital twin of a Martian greenhouse** powered by 5 specialized AI agents that think, reason, and collaborate — all grounded in the **Syngenta Knowledge Base** via AWS AgentCore MCP.

### The 5 Agents

| Agent | Role | What It Does |
|-------|------|-------------|
| **Environment Agent** | Climate control | Monitors temperature, humidity, CO₂, light. Detects when sensors drift out of optimal bands (18-26°C, 60-80% humidity) and recommends corrections. Uses KB data on crop stress thresholds. |
| **Crisis Agent** | Emergency response | Responds to 5 crisis types: water recycling failure, energy budget cut, temperature spike, disease outbreak, CO₂ imbalance. Each crisis has severity, recovery timeline, and containment playbook — all from KB. |
| **Planner Agent** | Crop allocation | Dynamically reallocates the 5-crop portfolio (potato, beans, lettuce, radish, herbs) based on nutritional deficits and active crises. Optimizes for coverage over multiple harvest cycles. |
| **Nutrition Agent** | Crew health | Tracks per-astronaut health with individual metabolic profiles. Commander has higher activity needs, scientist has lower resilience, engineer does EVA work. Computes coverage score weighted: 40% calories, 35% protein, 25% micronutrients. |
| **Vision Agent** | Plant inspection | A robot dog scans greenhouse plots from 4 angles. OpenCV preprocessing + Claude Vision detects disease, water stress, nutrient deficiency. VisionAgent then generates KB-grounded treatment plans with mission impact assessment. |

### What Makes It Special

**KB-Grounded Reasoning:** Every agent queries the Syngenta Knowledge Base before making decisions. When the Environment Agent recommends lowering humidity, it cites KB Section 4.7 on fungal risk thresholds. When the Planner shifts crops toward lettuce, it references KB Section 3.3 on vitamin A density per harvest cycle.

**Human-in-the-Loop:** When a crisis hits, the simulation pauses and presents agent recommendations to the astronaut crew for review. The astronaut can:
- **Approve** — apply the AI's recommendations
- **Reject** — override and keep current state
- **Chat** — ask the AI "Why are you cutting herb zone lighting?" and get a reasoned, KB-grounded response

This isn't just AI making decisions — it's AI collaborating with humans under pressure.

---

## 3. The Simulation Engine (45 seconds)

Each sol (Martian day), the simulation runs a **7-step pipeline**:

```
Sol N
 ├── Step 1: Mars external drift (temp, dust storms, radiation)
 ├── Step 2: Internal sensor drift (temp, humidity, CO₂, light)
 ├── Step 3: Cascade effects (dust reduces light, cold spikes energy)
 ├── Step 4: Crisis roll (probabilistic + scripted scenarios)
 ├── Step 5: Crop growth + harvest (5 crops, staggered planting)
 ├── Step 6: Nutritional output (fresh vs aged vitamin model)
 └── Step 7: Resource consumption (water, energy)
 ↓
 5 AI Agents analyze state → recommend actions
 ↓
 Astronaut approves/rejects (if crisis)
 ↓
 Apply decisions → advance to Sol N+1
```

### The Fresh vs. Aged Vitamin Model

This is our key scientific innovation. Pre-packaged food from Earth has **degraded vitamins** — vitamin C loses potency fastest (only 35% bioavailable from aged food). Fresh greenhouse produce is **100% bioavailable** but decays at ~6% per sol.

This creates a realistic nutritional oscillation:
- **Between harvests:** Coverage drops as fresh produce decays → crew relies on aged food with capped vitamins
- **At harvest:** Coverage spikes as fresh vitamins flood in
- **Net effect:** The greenhouse must be continuously productive or the crew develops micronutrient deficiency

The AI agents optimize for this — the Planner Agent staggers planting so harvests are spread across the cycle, ensuring a steady flow of fresh vitamins.

### Staggered Planting

20 plots across 5 crops, with planting offsets so harvests are spread evenly:

| Crop | Plots | Cycle | Harvest Interval |
|------|-------|-------|-----------------|
| Potato | 6 | 120 sols | Every ~20 sols |
| Beans | 4 | 65 sols | Every ~16 sols |
| Lettuce | 4 | 35 sols | Every ~9 sols |
| Radish | 3 | 30 sols | Every ~10 sols |
| Herbs | 3 | 45 sols | Every ~15 sols |

**Result:** Something harvests almost every 2-3 sols. Nutritional coverage stays 96-100% under normal conditions. When a crisis disrupts harvests, coverage visibly drops — and the AI must adapt.

---

## 4. The 5 Crisis Scenarios (30 seconds)

Matching the Syngenta case study, our simulation auto-triggers scripted scenarios:

| Sol | Crisis | What Happens | Agent Response |
|-----|--------|-------------|----------------|
| **42** | Water recycling failure | Efficiency drops to 60%, reservoir declining | Reduce irrigation 30%, activate backup reserve, shift to low-water crops |
| **98** | Energy budget cut | Solar output drops 35% (dust storm) | Shorten photoperiod, reduce LED to minimum viable PAR, lower temp to 19°C |
| **155** | Temperature spike | HVAC malfunction, temp rises to 31°C | Activate cooling, increase ventilation, flag lettuce for accelerated harvest |
| **210** | Disease outbreak | Bean zone shows discoloration and wilting | Isolate zone, reduce humidity to 65%, remove contaminated material |

Each crisis has **persistent severity** — it doesn't vanish after one sol. Recovery takes 1-7 sols depending on severity. During that time, the crisis applies ongoing effects (reduced water efficiency, temperature pressure, etc.).

The astronaut reviews and approves each response via the HITL modal.

---

## 5. The Dashboard (15 seconds — show it)

Three-panel mission control interface:

**Left Panel — Crew & Resources:**
- 4 astronaut health scores (diverge individually)
- Macro food reserves (450 sols of calories)
- Vitamin reserves (critical — only 35-45 sols)
- Per-vitamin breakdown (A, C, K, Folate)
- Active crises with severity bars

**Center Panel — Greenhouse Grid + Analytics:**
- 10 greenhouse domes with real-time sensor readings
- Click to inspect: crop health, stress flags, growth day
- **AI Agents tab:** All 5 agent reports with KB-grounded reasoning
- **Mission Timeline:** SVG chart showing coverage, crew health, harvests, crises over time
- **Camera & Robot:** CV scan results with plant images

**Right Panel — Mission AI Chat:**
- Natural language conversation with the Orchestrator Agent
- Ask: "What's causing the vitamin C deficit?" → Get KB-grounded analysis
- Ask: "Should we plant more radish?" → Get projected coverage impact

---

## 6. Technical Architecture

```
┌─────────────────────────────────────────────────────┐
│                   FRONTEND (React)                    │
│  Mission Control Dashboard + WebSocket Live Updates   │
└───────────────────────┬─────────────────────────────┘
                        │ WebSocket + REST
┌───────────────────────▼─────────────────────────────┐
│               LOCAL SERVER (FastAPI)                   │
│  GameState · 7-Step Simulation · HITL · Endpoints     │
└───────────┬───────────┬───────────┬─────────────────┘
            │           │           │
   ┌────────▼──┐  ┌─────▼────┐  ┌──▼──────────────┐
   │ 5 AI      │  │ Simulation│  │ Vision Pipeline  │
   │ Agents    │  │ Engine    │  │ OpenCV + Claude  │
   │ (Strands) │  │ (7 steps) │  │ Vision           │
   └────┬──────┘  └──────────┘  └──────────────────┘
        │
   ┌────▼──────────────────────────┐
   │  Syngenta Knowledge Base       │
   │  AWS AgentCore MCP Gateway     │
   │  Claude Sonnet 4.5 (Bedrock)  │
   └────────────────────────────────┘
```

**Key Technologies:**
- **Strands SDK** — Agent framework for multi-agent orchestration
- **AWS Bedrock** — Claude Sonnet 4.5 for agent reasoning + Claude Vision for plant analysis
- **MCP (Model Context Protocol)** — Live connection to Syngenta agricultural KB
- **OpenCV** — Image preprocessing for plant health analysis
- **FastAPI + WebSocket** — Real-time simulation server
- **React (no build step)** — Single-file dashboard, instant deployment

---

## 7. Why OrbitGrow Wins

| Criterion | What We Deliver |
|-----------|----------------|
| **Creativity** | 5 specialized agents that deliberate and sometimes disagree. Human-in-the-loop astronaut approval. Robot dog vision system. Fresh vs. aged vitamin biochemistry model. No other team will have this depth. |
| **Functional Accuracy** | All 5 Syngenta case study scenarios implemented and passing. Real nutritional profiles from KB. Scientifically grounded crop growth, harvest cycles, and vitamin degradation. Per-astronaut metabolic modeling. |
| **Visual Design** | Dark sci-fi mission control aesthetic. Real-time WebSocket updates. Interactive greenhouse inspection. Timeline visualization. Approval modal with AI chat. Professional, polished, accessible. |
| **Presentation** | Live simulation running at variable speed. Crisis injection on demand. Astronaut approval flow demonstrable in real-time. Every agent decision shows KB citations. The demo tells a 450-sol story. |

---

## Demo Script (3 minutes)

**0:00 — Open (15s)**
"OrbitGrow: an AI agent system that manages a Martian greenhouse to keep 4 astronauts alive for 450 sols. Grounded in Syngenta's agricultural knowledge base."

**0:15 — Show Dashboard (20s)**
Show the three-panel layout. Point out: 10 greenhouses, 4 astronauts, vitamin reserves ticking down while calories stay stable. "The greenhouse is critical for micronutrients — stored food vitamins degrade."

**0:35 — Start Simulation (30s)**
Hit play at 5x speed. Watch sols advance. Point out: "See the nutrition coverage? It oscillates — spikes when crops harvest, dips between. Our staggered planting keeps it above 96%. Each agent runs every sol, connected to the Syngenta KB."

**1:05 — Crisis Hits (45s)**
Let sol 42 arrive (or inject water crisis manually). HITL modal appears. "The AI detected a water recycling failure. Here's what 3 agents recommend. The astronaut can approve, reject, or chat with the AI." Click chat: "Why reduce irrigation?" Show AI response with KB citations. Click approve.

**1:50 — Show Agent Reports (30s)**
Switch to AI Agents tab. "Each agent explains its reasoning, grounded in your knowledge base. The Crisis Agent references KB playbooks. The Planner shifts crops toward faster-cycle lettuce and radish to recover vitamin coverage."

**2:20 — Vision Demo (25s)**
Click a greenhouse plot. "Our robot dog scans plants with OpenCV + Claude Vision. Here it detects water stress in this bean plot — the VisionAgent recommends treatment based on KB plant health guidance."

**2:45 — Close (15s)**
"OrbitGrow: 5 AI agents, grounded in Syngenta science, keeping astronauts alive on Mars. Real simulation, real KB, real human-AI collaboration. Thank you."

---

## Quick Facts for Q&A

- **How many agents?** 5 specialized + 1 orchestrator
- **What model?** Claude Sonnet 4.5 on AWS Bedrock
- **Is the KB connection real?** Yes — live MCP gateway to Syngenta AgentCore, verifiable by "KB Fallback: false" in agent reports
- **What if KB is down?** Graceful degradation — agents fall back to validated hardcoded data from the KB
- **How realistic is the nutrition model?** Based on real crop nutritional profiles (kcal/kg, protein/kg, vitamins/kg) from the KB. Two-tier fresh/aged vitamin model reflects actual produce degradation
- **Can astronauts override the AI?** Yes — HITL system pauses on crises, astronaut reviews + approves/rejects/chats
- **How many crisis scenarios?** 5 types, matching all Syngenta case study scenarios
- **What's the vision system?** OpenCV preprocessing → Claude Vision analysis → VisionAgent KB-grounded treatment plans
- **Tech stack?** Python (FastAPI, Strands SDK, OpenCV, PIL), React (no build step), AWS Bedrock, MCP
