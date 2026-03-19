"""
Orchestrator Agent — coordinates all sub-agents and synthesizes the DailyMissionReport.
"""
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
            model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            region_name="us-west-2",
        )
        return Agent(model=model)

    def run(self, sol: int, mission_context: dict) -> dict:
        """
        Runs all sub-agents in sequence and returns DailyMissionReport.
        """
        nutrition_ledger = mission_context.get("nutrition_ledger", {})
        environment_state = mission_context.get("environment_state", {})
        crises_active = mission_context.get("crises_active", [])
        active_crises_detail = mission_context.get("active_crises_detail", {})
        prev_crew_health = mission_context.get("prev_crew_health", None)

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

        mission_summary = self._synthesize_summary(
            sol, nutrition_report, environment_report, crisis_report, planting_plan
        )

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

        # Query KB with the user's actual question for relevant context
        kb_result = self.mcp.query_kb(message, max_results=5)
        kb_text = "\n---\n".join(kb_result["chunks"]) if kb_result["chunks"] else "Knowledge base unavailable."

        context_prompt = (
            f"You are the OrbitGrow mission AI managing a Martian greenhouse for 4 astronauts.\n\n"
            f"## Syngenta Mars Crop Knowledge Base\n{kb_text}\n\n"
            f"## Current Mission State (Sol {sol})\n"
            f"- Nutrition: kcal={nutrition_ledger.get('kcal', 0):.0f}, "
            f"protein_g={nutrition_ledger.get('protein_g', 0):.0f}, "
            f"coverage_score={nutrition_ledger.get('coverage_score', 0):.1f}%\n"
            f"- Environment: temp={environment_state.get('temperature_c', 'N/A')}°C, "
            f"humidity={environment_state.get('humidity_pct', 'N/A')}%, "
            f"co2={environment_state.get('co2_ppm', 'N/A')} ppm\n"
            f"- Active crises: {crises_active if crises_active else 'none'}\n"
            f"- Crew health: {[str(h.get('astronaut')) + ': ' + str(h.get('health_score', 100)) for h in crew_health]}\n\n"
            f"Answer the following question using the Knowledge Base data and mission state above. "
            f"Ground your response in the KB data when relevant.\n\n"
            f"User question: {message}"
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
