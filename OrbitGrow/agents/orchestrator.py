"""
Orchestrator Agent — coordinates all sub-agents and synthesizes the DailyMissionReport.
"""
import os
import logging

from agents.mcp_client import MCPClient
from agents.nutrition_agent import NutritionAgent
from agents.environment_agent import EnvironmentAgent
from agents.crisis_agent import CrisisAgent
from agents.planner_agent import PlannerAgent

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

    def _get_strands_agent(self) -> Agent:
        model = BedrockModel(
            model_id="anthropic.claude-3-5-haiku-20241022-v1:0",
            region_name="us-west-2",
        )
        return Agent(model=model)

    def run(self, sol: int, mission_context: dict) -> dict:
        """
        Runs all sub-agents in sequence and returns DailyMissionReport.
        mission_context keys: nutrition_ledger, environment_state, crises_active,
                              prev_crew_health (optional)
        """
        # Step 1: Extract context
        nutrition_ledger = mission_context.get("nutrition_ledger", {})
        environment_state = mission_context.get("environment_state", {})
        crises_active = mission_context.get("crises_active", [])
        prev_crew_health = mission_context.get("prev_crew_health", None)

        # Step 2: Run NutritionAgent
        nutrition_report = self.nutrition_agent.run(
            sol=sol,
            nutrition_ledger=nutrition_ledger,
            prev_crew_health=prev_crew_health,
        )

        # Step 3: Run EnvironmentAgent
        environment_report = self.environment_agent.run(
            sol=sol,
            environment_state=environment_state,
        )

        # Step 4: Run CrisisAgent
        crisis_report = self.crisis_agent.run(
            sol=sol,
            crises_active=crises_active,
        )

        # Step 5: Run PlannerAgent
        planting_plan = self.planner_agent.run(
            nutrition_report=nutrition_report,
            environment_report=environment_report,
            crisis_report=crisis_report,
        )

        # Step 6: Use Strands Agent to synthesize mission_summary
        mission_summary = self._synthesize_summary(
            sol, nutrition_report, environment_report, crisis_report, planting_plan
        )

        # Step 7: Build DailyMissionReport
        return {
            "sol": sol,
            "nutrition_report": nutrition_report,
            "environment_report": environment_report,
            "crisis_report": crisis_report,
            "planting_plan": planting_plan,
            "mission_summary": mission_summary,
            "crew_health_emergency": nutrition_report.get("crew_health_emergency", False),
            "crew_health_statuses": nutrition_report.get("crew_health_statuses", []),
        }

    def _synthesize_summary(
        self,
        sol: int,
        nutrition_report: dict,
        environment_report: dict,
        crisis_report: dict,
        planting_plan: dict,
    ) -> str:
        """Use Strands Agent with Claude 3.5 Sonnet to generate a mission summary."""
        try:
            agent = self._get_strands_agent()
            summary_prompt = (
                f"Sol {sol} mission summary: "
                f"nutrition_score={nutrition_report.get('coverage_score', 0):.1f}, "
                f"crises={crisis_report.get('crises_handled', [])}, "
                f"environment={'nominal' if not environment_report.get('setpoint_adjustments') else 'adjustments needed'}. "
                "Provide a 2-sentence mission status."
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
        sol_reports = mission_context.get("sol_reports", {})
        crew_health = mission_context.get("crew_health", [])

        # Fetch relevant KB data to ground the response
        kb_nutrition = self.mcp.query("03", message)
        kb_environment = self.mcp.query("04", message)

        context_prompt = (
            f"You are the OrbitGrow mission AI managing a Martian greenhouse for 4 astronauts.\n\n"
            f"Current mission state (Sol {sol}):\n"
            f"- Nutrition: kcal={nutrition_ledger.get('kcal', 0):.0f}, "
            f"protein_g={nutrition_ledger.get('protein_g', 0):.0f}, "
            f"coverage_score={nutrition_ledger.get('coverage_score', 0):.1f}%\n"
            f"- Environment: temp={environment_state.get('temperature_c', 'N/A')}°C, "
            f"humidity={environment_state.get('humidity_pct', 'N/A')}%, "
            f"co2={environment_state.get('co2_ppm', 'N/A')} ppm\n"
            f"- Active crises: {crises_active if crises_active else 'none'}\n"
            f"- Crew health: {[str(h.get('astronaut')) + ': ' + str(h.get('health_score', 100)) for h in crew_health]}\n\n"
            f"Mars Crop Knowledge Base — Nutritional profiles:\n{kb_nutrition}\n\n"
            f"Mars Crop Knowledge Base — Environmental constraints:\n{kb_environment}\n\n"
            f"User question: {message}"
        )

        try:
            agent = self._get_strands_agent()
            response = agent(context_prompt)
            return {
                "response": str(response),
                "reasoning": "Agent reasoning via Claude 3.5 Haiku + MCP KB",
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
            }
