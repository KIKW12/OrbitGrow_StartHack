# How to Write a Good Prompt for Kiro

When asking Kiro to generate code, the more structured your prompt, the better the output. Use the template below to craft clear, actionable prompts.

---

## Prompt Template

```
In [LANGUAGE], [ACTION] that [SPECIFIC_REQUIREMENT].

Input: [INPUT_SPECIFICATION]
Output: [OUTPUT_SPECIFICATION]
Edge cases: [EDGE_CASE_HANDLING]
Constraints: [TECHNICAL_CONSTRAINTS]
Context: [BUSINESS_CONTEXT]
```

---

## How to Fill Each Field

| Field | What to Write | Example |
|---|---|---|
| `LANGUAGE` | The programming language or framework | TypeScript, Python, React, SQL |
| `ACTION` | What you want built | create a function, build a component, write a Lambda handler |
| `SPECIFIC_REQUIREMENT` | The core behavior or purpose | fetches crop data from DynamoDB and returns it sorted by growth stage |
| `INPUT_SPECIFICATION` | What the code receives | A crop name (string) and a date range (start, end) |
| `OUTPUT_SPECIFICATION` | What the code returns or renders | A JSON array of crop records with fields: name, stage, waterNeeds, temperature |
| `EDGE_CASE_HANDLING` | What to do when things go wrong | Return an empty array if no records found. Throw an error if crop name is invalid |
| `TECHNICAL_CONSTRAINTS` | Limits, dependencies, or requirements | Use AWS SDK v3. No external libraries. Must run in Lambda with 128MB memory |
| `BUSINESS_CONTEXT` | Why this matters — helps Kiro make better decisions | This powers the dashboard that astronauts use to monitor greenhouse health |

---

## Examples

### Example 1 — Backend Function

```
In TypeScript, create a Lambda function that queries DynamoDB for crop sensor readings.

Input: cropId (string), timeRange (last 24h, 7d, or 30d)
Output: Array of { timestamp, temperature, humidity, soilMoisture } sorted by timestamp descending
Edge cases: Return empty array if no readings exist. Return 400 if cropId is missing.
Constraints: Use AWS SDK v3. DynamoDB table name from environment variable SENSOR_TABLE.
Context: This feeds the real-time monitoring dashboard for the Mars greenhouse.
```

### Example 2 — Frontend Component

```
In React with TypeScript, build a component that displays crop health status cards.

Input: Array of crop objects with fields: name, healthScore (0-100), lastWatered (ISO date)
Output: A grid of cards showing crop name, a color-coded health indicator (green/yellow/red), and time since last watered
Edge cases: Show "No crops planted" message if array is empty. Show "Unknown" if healthScore is null.
Constraints: Use Tailwind CSS for styling. No external component libraries.
Context: This is the main view astronauts see when they open the greenhouse management app.
```

### Example 3 — AI Agent

```
In Python, create a Strands agent that recommends optimal watering schedules.

Input: Current soil moisture levels, crop type, and growth stage
Output: A watering schedule with times and amounts for the next 7 days
Edge cases: If soil moisture sensor is offline, use the last known value and flag it as estimated.
Constraints: Use Strands SDK. Query the Mars crop knowledge base MCP for crop water requirements.
Context: This agent runs autonomously to manage water resources in the greenhouse, where water is scarce.
```

---

## Tips

- You don't need to fill every field every time — but the more context you give, the better the result.
- Start with the action and requirement, then add details as needed.
- If the first result isn't right, refine by adding more edge cases or constraints.
- Use Kiro's Planner (`Shift + Tab`) to break complex prompts into smaller steps first.
