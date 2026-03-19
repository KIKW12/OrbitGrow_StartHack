"""
Crisis Agent — applies KB playbooks to active crises.
"""
from agents.mcp_client import MCPClient, HARDCODED_DEFAULTS


class CrisisAgent:
    def __init__(self, mcp: MCPClient = None):
        self.mcp = mcp or MCPClient()

    def run(self, sol: int, crises_active: list) -> dict:
        """
        Returns CrisisReport dict with keys:
        crises_handled, actions_taken, recovery_timeline_sols, reasoning
        """
        # Step 1: No-op if no active crises
        if not crises_active:
            return {
                "crises_handled": [],
                "actions_taken": [],
                "recovery_timeline_sols": {},
                "reasoning": "No active crises.",
            }

        # Step 2: Query MCP KB doc "06" for playbooks
        kb = self.mcp.query("06", "crisis response playbooks and containment actions")
        defaults = HARDCODED_DEFAULTS["06"]
        playbooks = kb.get("playbooks", defaults["playbooks"])

        # Step 3 & 4: Process each active crisis
        crises_handled = []
        actions_taken = []
        recovery_timeline_sols = {}
        reasoning_parts = []

        for crisis in crises_active:
            playbook = playbooks.get(crisis)
            if not playbook:
                reasoning_parts.append(
                    f"No playbook found for crisis '{crisis}'; skipping."
                )
                continue

            containment = playbook.get("containment", [])
            recovery_sols = playbook.get("recovery_timeline_sols", 0)

            crises_handled.append(crisis)
            actions_taken.extend(containment)
            recovery_timeline_sols[crisis] = recovery_sols

            reasoning_parts.append(
                f"Crisis '{crisis}': applied containment actions "
                f"[{', '.join(containment)}]; estimated recovery in {recovery_sols} Sol(s)."
            )

        reasoning = " ".join(reasoning_parts) if reasoning_parts else "All crises processed."

        return {
            "crises_handled": crises_handled,
            "actions_taken": actions_taken,
            "recovery_timeline_sols": recovery_timeline_sols,
            "reasoning": reasoning,
            "kb_fallback": kb.get("kb_fallback", False),
        }
