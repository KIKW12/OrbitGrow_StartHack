# 🌱 OrbitGrow — End-to-End Test Case Study

> All values sourced directly from the Syngenta Knowledge Base via the MCP server.

---

## Mission Context

| Parameter | Value |
|---|---|
| Crew size | 4 astronauts |
| Mission duration | 450 sols |
| Daily caloric target (crew) | 12,000 kcal / day |
| Protein target (crew) | ~450 g / day |
| Total caloric need | ~5.4 million kcal over 450 sols |
| Greenhouse system | Sealed, pressurised, hydroponic CEA |

---

## Baseline Environment (Sol 0 — Normal Operations)

| Parameter | Optimal Range | Starting Value |
|---|---|---|
| Temperature | 18 – 26 °C | **22 °C** |
| Humidity | 60 – 80 % | **70 %** |
| CO₂ | 800 – 1,200 ppm | **1,000 ppm** |
| Light (PAR) | 150 – 400 µmol/m²/s | **300 µmol/m²/s** |

---

## Crop Portfolio (Sol 0)

| Crop | Zone area | Cycle (sols) | Base yield (kg/m²) | Role |
|---|---|---|---|---|
| Potato | 40 m² | 120 | 5.0 | Caloric backbone |
| Beans | 20 m² | 65 | 2.0 | Protein security |
| Lettuce | 15 m² | 35 | 3.0 | Micronutrients |
| Radish | 10 m² | 30 | 4.0 | Fast buffer crop |
| Herbs | 5 m² | 45 | 1.5 | Crew morale |

---

## Scenario 1 — Water Recycling Failure (Sol 42)

### Event
Recycling efficiency drops from 95 % to 60 %. Reservoir trend is declining.  
**Detection rule:** `IF recycling_efficiency < 70% AND reservoir_trend == "declining" → HIGH PRIORITY`

### Expected Agent Behaviour

| Phase | Action |
|---|---|
| **Immediate** | Reduce irrigation frequency by 30 %; activate backup water reserve |
| **Medium-term** | Run diagnostic — identify leakage/fouling; clean or replace filters |
| **Strategic** | Shift crop mix toward lower water-demand crops (potato > lettuce ratio) |

### Success Criteria
- Recycling efficiency restored to ≥ 90 %
- Water reservoir stabilised
- Crop stress score < 0.15

### Recovery timeline: **3 sols**

---

## Scenario 2 — Energy Budget Cut (Sol 98)

### Event
Solar panel output drops 35 % due to a dust storm. Battery storage declining.

### Expected Agent Behaviour

| Priority | Action |
|---|---|
| 1 — Life-critical | Maintain pressurisation and crew life support (non-negotiable) |
| 2 — Immediate | Shorten photoperiod; reduce LED intensity to minimum viable PAR (150 µmol/m²/s) |
| 3 — Medium-term | Lower temperature setpoint from 22 °C → 19 °C; prioritise high-efficiency crops |
| 4 — Strategic | Suspend herb zone lighting; focus energy on potato and bean zones |

### Success Criteria
- Energy budget balanced within 2 sols
- No crop zone drops below minimum PAR
- Temperature stays within 18 – 26 °C band

### Recovery timeline: **2 sols**

---

## Scenario 3 — Temperature Spike (Sol 155)

### Event
HVAC malfunction causes temperature to rise from 22 °C → 31 °C over 4 hours.  
Lettuce shows early bolting indicators.

### Expected Agent Behaviour

1. Activate cooling system
2. Increase ventilation rate
3. Flag lettuce zone for accelerated harvest (bolted lettuce is inedible)
4. Trigger replanting of lettuce — 35-sol cycle begins immediately

### Success Criteria
- Temperature back within 18 – 26 °C within 1 sol
- Lettuce loss contained to affected plants only
- Replanting initiated before sol ends

### Recovery timeline: **1 sol**

---

## Scenario 4 — Crop Disease / Pathogen Risk (Sol 210)

### Event
Vision agent detects discolouration and wilting in bean zone (Zone B).  
Humidity has been running at 85 % (above the 80 % ceiling) for 6 sols.

### Expected Agent Behaviour

1. **Isolate** Zone B — halt shared airflow with other zones
2. **Reduce humidity** across all zones to 65 %
3. **Increase monitoring frequency** in adjacent zones
4. **Remove contaminated material** if pathogen confirmed
5. Resume normal operations only after zone health validated

### Success Criteria
- No spread to other zones
- Humidity back within 60 – 80 % band
- Bean yield loss < 20 % of zone output

### Recovery timeline: **7 sols**

---

## Full Integration Test Flow

Run these scenarios sequentially to exercise every agent:

```
Sol 0    → Bootstrap simulation, assert baseline environment and yields
Sol 42   → Inject water recycling failure → test crisis_agent + environment_agent
Sol 98   → Inject energy budget cut → test planner_agent + environment_agent
Sol 155  → Inject temperature spike → test vision_agent + crisis_agent
Sol 210  → Inject disease event → test vision_agent + orchestrator
Sol 300  → Nutrition check → test nutrition_agent (cumulative yield vs. targets)
Sol 450  → Mission complete → full nutritional coverage report
```

### How to inject a scenario

```python
from agents.orchestrator import Orchestrator

orch = Orchestrator()

# Example: water recycling failure at Sol 42
result = orch.run({
    "sol": 42,
    "sensor_data": {
        "temperature_c": 22,
        "humidity_pct": 71,
        "co2_ppm": 1000,
        "light_umol": 300,
        "water_recycling_efficiency_pct": 60,   # <-- anomaly
        "reservoir_trend": "declining"
    }
})

print(result)
```

---

## Nutritional Coverage Check (Sol 300 snapshot)

With the baseline portfolio after 300 sols (assuming no compounding failures):

| Nutrient | Daily target | Estimated coverage |
|---|---|---|
| Calories | 12,000 kcal | ~65 % from greenhouse |
| Protein | 450 g | ~55 % from beans + potato |
| Vitamin A | 3,600 IU | ~110 % from lettuce |
| Vitamin C | 400 mg | ~90 % from radish + herbs |
| Folate | 1.6 mg | ~70 % from beans |

> Remaining gap is covered by pre-packaged stored food — a realistic mission assumption.

---

*Data sourced from: `01_Mars_Environment_Extended.md`, `03_Crop_Profiles_Extended.md`, `04_Environmental_Control.md`, `05_Nutritional_Strategy.md`, `06_Operational_Scenarios.md` — retrieved via MCP KB at session start.*
