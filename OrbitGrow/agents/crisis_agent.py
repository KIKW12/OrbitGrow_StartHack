"""
Crisis Agent — applies KB playbooks to active crises.
"""
from agents.mcp_client import MCPClient, STRUCTURED_DATA

_CRISIS = STRUCTURED_DATA["crisis"]


class CrisisAgent:
    def __init__(self, mcp: MCPClient = None):
        self.mcp = mcp or MCPClient()

    def run(self, sol: int, crises_active: list) -> dict:
        """
        Returns CrisisReport dict with keys:
        crises_handled, actions_taken, recovery_timeline_sols, reasoning, kb_context
        """
        if not crises_active:
            return {
                "crises_handled": [],
                "actions_taken": [],
                "recovery_timeline_sols": {},
                "reasoning": "No active crises.",
                "kb_fallback": False,
                "kb_context": "",
            }

        # Query KB for crisis-specific context
        crisis_names = " ".join(c.replace("_", " ") for c in crises_active)
        kb = self.mcp.query_kb(
            f"crisis response containment recovery {crisis_names} greenhouse Mars",
            max_results=3,
        )
        kb_context = "\n---\n".join(kb["chunks"]) if kb["chunks"] else ""

        playbooks = _CRISIS["playbooks"]

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
            "kb_context": kb_context,
        }
