"""
Orchestrator Agent — coordinates all sub-agents and synthesizes the DailyMissionReport.
"""
import logging

from agents.mcp_client import MCPClient
from agents.nutrition_agent import NutritionAgent
from agents.environment_agent import EnvironmentAgent
from agents.crisis_agent import CrisisAgent
from agents.planner_agent import PlannerAgent
from agents.vision_agent import VisionAgent

from strands import Agent
from strands.models import BedrockModel

logger = logging.getLogger(__name__)


class OrchestratorAgent:
    def __init__(self, mcp: MCPClient = None):
        self.mcp = mcp or MCPClient()
        self.nutrition_agent = NutritionAgent(mcp=self.mcp)
        self.environment_agent = EnvironmentAgent(mcp=self.mcp)
        self.crisis_agent = CrisisAgent(mcp=self.mcp)
        self.planner_agent = PlannerAgent(mcp=self.mcp)
        self.vision_agent = VisionAgent(mcp=self.mcp)

    def _get_strands_agent(self) -> Agent:
        model = BedrockModel(
            model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            region_name="us-west-2",
        )
        return Agent(model=model)

    def run(self, sol: int, mission_context: dict) -> dict:
        """
        Runs all sub-agents in sequence and returns DailyMissionReport.
        """
        nutrition_ledger     = mission_context.get("nutrition_ledger", {})
        environment_state    = mission_context.get("environment_state", {})
        crises_active        = mission_context.get("crises_active", [])
        active_crises_detail = mission_context.get("active_crises_detail", {})
        prev_crew_health     = mission_context.get("prev_crew_health", None)
        cv_results           = mission_context.get("cv_results", {})
        plots                = mission_context.get("plots", [])

        nutrition_report = self.nutrition_agent.run(
            sol=sol,
            nutrition_ledger=nutrition_ledger,
            prev_crew_health=prev_crew_health,
        )

        environment_report = self.environment_agent.run(
            sol=sol,
            environment_state=environment_state,
        )

        crisis_report = self.crisis_agent.run(
            sol=sol,
            crises_active=crises_active,
            active_crises_detail=active_crises_detail,
        )

        planting_plan = self.planner_agent.run(
            nutrition_report=nutrition_report,
            environment_report=environment_report,
            crisis_report=crisis_report,
        )

        # VisionAgent — runs only when CV results exist (not skipped at high speed)
        vision_report = {}
        if cv_results:
            try:
                vision_report = self.vision_agent.run(
                    sol=sol,
                    cv_results=cv_results,
                    plots=plots,
                    env=environment_state,
                )
            except Exception as exc:
                logger.warning("VisionAgent in orchestrator failed: %s", exc)
                vision_report = {"summary": "", "kb_fallback": True}

        mission_summary = self._synthesize_summary(
            sol, nutrition_report, environment_report, crisis_report, planting_plan
        )

        return {
            "sol": sol,
            "nutrition_report":  nutrition_report,
            "environment_report": environment_report,
            "crisis_report":     crisis_report,
            "planting_plan":     planting_plan,
            "vision_report":     vision_report,
            "mission_summary":   mission_summary,
            "crew_health_emergency": nutrition_report.get("crew_health_emergency", False),
            "crew_health_statuses":  nutrition_report.get("crew_health_statuses", []),
        }

    def _synthesize_summary(
        self,
        sol: int,
        nutrition_report: dict,
        environment_report: dict,
        crisis_report: dict,
        planting_plan: dict,
    ) -> str:
        """Use Strands Agent with Claude 3.5 Haiku to generate a mission summary grounded in KB data."""
        try:
            agent = self._get_strands_agent()

            # Collect KB context from sub-agent reports
            kb_snippets = []
            for report in [nutrition_report, environment_report, crisis_report]:
                ctx = report.get("kb_context", "")
                if ctx:
                    kb_snippets.append(ctx[:500])
            kb_grounding = "\n".join(kb_snippets) if kb_snippets else "No KB context available."

            summary_prompt = (
                f"You are the OrbitGrow mission AI for a Martian greenhouse feeding 4 astronauts.\n\n"
                f"Syngenta Knowledge Base context:\n{kb_grounding}\n\n"
                f"Sol {sol} data:\n"
                f"- Nutrition coverage: {nutrition_report.get('coverage_score', 0):.1f}%\n"
                f"- Deficit summary: {nutrition_report.get('deficit_summary', 'N/A')}\n"
                f"- Crew health emergency: {nutrition_report.get('crew_health_emergency', False)}\n"
                f"- Environment: {environment_report.get('reasoning', 'N/A')}\n"
                f"- Crises handled: {crisis_report.get('crises_handled', [])}\n"
                f"- Planting plan: {planting_plan.get('rationale', 'N/A')}\n\n"
                "Provide a concise 2-3 sentence mission status report for Sol {sol}."
            )
            response = agent(summary_prompt)
            return str(response)
        except Exception as exc:
            logger.warning("Strands Agent synthesis failed: %s", exc)
            crises = crisis_report.get("crises_handled", [])
            env_status = "nominal" if not environment_report.get("setpoint_adjustments") else "adjustments needed"
            return (
                f"Sol {sol} report: Nutritional coverage at "
                f"{nutrition_report.get('coverage_score', 0):.1f}%. "
                f"Environment: {env_status}. "
                f"Active crises: {crises if crises else 'none'}. "
                f"Planting plan updated with {len(planting_plan.get('plot_assignments', []))} plot assignments."
            )

    def chat(self, message: str, mission_context: dict) -> dict:
        """
        Handles a natural language chat message with full mission context + MCP KB data.
        Returns {"response": str, "reasoning": str}
        """
        sol = mission_context.get("sol", "unknown")
        nutrition_ledger = mission_context.get("nutrition_ledger", {})
        environment_state = mission_context.get("environment_state", {})
        crises_active = mission_context.get("crises_active", [])
        crew_health = mission_context.get("crew_health", [])
        greenhouses = mission_context.get("greenhouses", [])
        facility_env = mission_context.get("facility_env", {})
        food_storage = mission_context.get("food_storage", {})
        agent_report = mission_context.get("agent_report", {})
        phase = mission_context.get("phase", "nominal")

        # Query KB with the user's actual question for relevant context
        kb_result = self.mcp.query_kb(message, max_results=5)
        kb_text = "\n---\n".join(kb_result["chunks"]) if kb_result["chunks"] else "Knowledge base unavailable."

        # Build greenhouse status — full detail per greenhouse
        gh_lines = []
        active_alerts = []
        for gh in greenhouses:
            health_pct = round(gh.get("health", 1.0) * 100)
            flags = ", ".join(gh.get("stress_flags", [])) or "none"
            last_scan = gh.get("last_scan_sol", -1)
            scan_str = f"last scanned Sol {last_scan}" if last_scan >= 0 else "not yet scanned"
            line = (
                f"  {gh['name']} ({gh['crop_id']}): health={health_pct}%, "
                f"stress={flags}, {scan_str}, "
                f"temp={gh.get('temperature','?')}°C, humidity={gh.get('air_humidity','?')}%, "
                f"soil={gh.get('soil_moisture','?')}, ph={gh.get('ph','?')}"
            )
            for a in gh.get("alerts", []):
                text = a["text"] if isinstance(a, dict) else str(a)
                severity = a.get("severity", "") if isinstance(a, dict) else ""
                line += f"\n    [ALERT/{severity.upper() if severity else 'INFO'}] {text}"
                active_alerts.append(f"{gh['name']}: {text}")
            gh_lines.append(line)
        gh_summary = "\n".join(gh_lines) if gh_lines else "No greenhouse data."

        # Alerts block — shown prominently at the top so the model cannot miss them
        if active_alerts:
            alerts_block = "ACTIVE GREENHOUSE ALERTS (robot scan results this Sol):\n" + "\n".join(
                f"  - {a}" for a in active_alerts
            )
        else:
            alerts_block = "No active greenhouse alerts this Sol."

        # Last agent reasoning snippets
        env_reasoning = agent_report.get("environment", {}).get("reasoning", "")
        crisis_reasoning = agent_report.get("crisis", {}).get("reasoning", "")
        nutrition_reasoning = agent_report.get("nutrition", {}).get("deficit_summary", "")
        vision_summary = agent_report.get("vision", {}).get("summary", "")
        plots_at_risk = agent_report.get("vision", {}).get("plots_at_risk", [])

        context_prompt = (
            f"You are the OrbitGrow mission AI managing a Martian greenhouse for 4 astronauts on Mars.\n"
            f"You have LIVE access to all sensor readings, robot scan results, and greenhouse alerts.\n"
            f"Always answer based on the LIVE DATA below — do not say data is unavailable.\n\n"
            f"## LIVE MISSION DATA — Sol {sol} (Phase: {phase})\n\n"
            f"### {alerts_block}\n\n"
            f"### Greenhouse Status (10 greenhouses)\n{gh_summary}\n\n"
            f"### Active System Crises\n"
            f"{crises_active if crises_active else 'None'}\n"
            f"{('Crisis agent: ' + crisis_reasoning) if crisis_reasoning else ''}\n\n"
            f"### Crew Health\n"
            + "\n".join(
                f"  {h.get('astronaut', '?')}: {h.get('health_score', 100)}/100"
                + (f" [deficits: {', '.join(h.get('deficit_flags', []))}]" if h.get('deficit_flags') else "")
                for h in crew_health
            )
            + f"\n\n### Nutrition\n"
            f"- kcal={nutrition_ledger.get('kcal', 0):.0f}, "
            f"protein_g={nutrition_ledger.get('protein_g', 0):.0f}, "
            f"coverage={nutrition_ledger.get('coverage_score', 0):.1f}%, "
            f"food runway={food_storage.get('days_remaining', 0):.1f} days\n"
            f"{('Deficits: ' + nutrition_reasoning) if nutrition_reasoning else ''}\n\n"
            f"### Facility Environment\n"
            f"CO2={facility_env.get('co2','?')} ppm, "
            f"radiation={facility_env.get('radiation','?')} mSv/day, "
            f"pressure={facility_env.get('pressure','?')} Pa, "
            f"water={facility_env.get('consumed_water','?')} L/day\n\n"
            + (f"### Vision Agent Summary\n{vision_summary}\nPlots at risk: {plots_at_risk}\n\n" if vision_summary else "")
            + (f"### Environment Agent Notes\n{env_reasoning}\n\n" if env_reasoning else "")
            + f"## Syngenta Knowledge Base\n{kb_text}\n\n"
            f"Using the LIVE DATA above, answer the astronaut's question. "
            f"Reference specific greenhouse names and alert details when relevant. "
            f"Never say data is unavailable — all current data is provided above.\n\n"
            f"Astronaut: {message}"
        )

        try:
            agent = self._get_strands_agent()
            response = agent(context_prompt)
            return {
                "response": str(response),
                "reasoning": f"Grounded in Syngenta KB ({len(kb_result['chunks'])} chunks) + mission state",
                "kb_fallback": kb_result["kb_fallback"],
            }
        except Exception as exc:
            logger.warning("Strands Agent chat failed: %s", exc)
            return {
                "response": (
                    f"I'm currently unable to process your request due to a connectivity issue. "
                    f"Mission is at Sol {sol} with "
                    f"{len(crises_active)} active crisis/crises."
                ),
                "reasoning": f"Fallback response due to agent error: {exc}",
                "kb_fallback": True,
            }
