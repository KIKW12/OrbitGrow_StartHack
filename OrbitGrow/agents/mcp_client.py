"""
MCP client for the Mars Crop Knowledge Base via AgentCore streamable HTTP endpoint.
"""
import asyncio
import logging

from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

logger = logging.getLogger(__name__)

MCP_ENDPOINT = (
    "https://kb-start-hack-gateway-buyjtibfpg.gateway.bedrock-agentcore"
    ".us-east-2.amazonaws.com/mcp"
)
MCP_TIMEOUT = 10  # seconds

# ---------------------------------------------------------------------------
# In-memory cache: document_id -> last successful KB response
# ---------------------------------------------------------------------------
KB_CACHE: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Hardcoded fallback data (used when KB is unreachable and cache is empty)
# ---------------------------------------------------------------------------
HARDCODED_DEFAULTS: dict[str, dict] = {
    # Document 03 — nutritional profiles
    "03": {
        "nutritional_profiles": {
            "potato": {
                "kcal_per_kg": 770,
                "protein_g_per_kg": 20,
                "vitamin_a_per_kg": 0,
                "vitamin_c_per_kg": 197,
                "vitamin_k_per_kg": 1.6,
                "folate_per_kg": 0.054,
            },
            "beans": {
                "kcal_per_kg": 1470,
                "protein_g_per_kg": 90,
                "vitamin_a_per_kg": 0,
                "vitamin_c_per_kg": 0,
                "vitamin_k_per_kg": 0,
                "folate_per_kg": 0.604,
            },
            "lettuce": {
                "kcal_per_kg": 150,
                "protein_g_per_kg": 14,
                "vitamin_a_per_kg": 7405,
                "vitamin_c_per_kg": 92,
                "vitamin_k_per_kg": 1026,
                "folate_per_kg": 0.136,
            },
            "radish": {
                "kcal_per_kg": 160,
                "protein_g_per_kg": 7,
                "vitamin_a_per_kg": 0,
                "vitamin_c_per_kg": 147,
                "vitamin_k_per_kg": 1.3,
                "folate_per_kg": 0.025,
            },
            "herbs": {
                "kcal_per_kg": 400,
                "protein_g_per_kg": 30,
                "vitamin_a_per_kg": 5000,
                "vitamin_c_per_kg": 500,
                "vitamin_k_per_kg": 2000,
                "folate_per_kg": 0.2,
            },
        },
        "daily_targets": {
            "kcal": 12000,
            "protein_g": 450,
            "vitamin_a": 3600,
            "vitamin_c": 400,
            "vitamin_k": 480,
            "folate": 1.6,
        },
    },
    # Document 04 — environmental constraints
    "04": {
        "optimal_bands": {
            "temperature_c": {"min": 18, "max": 26},
            "humidity_pct": {"min": 60, "max": 80},
            "co2_ppm": {"min": 800, "max": 1500},
            "light_umol": {"min": 300, "max": 500},
        },
        "stress_multipliers": {
            "temperature_out_of_band": 0.95,
            "humidity_out_of_band": 0.97,
            "co2_out_of_band": 0.96,
            "light_out_of_band": 0.94,
        },
        "base_yields_per_m2": {
            "potato": 5.0,
            "beans": 2.0,
            "lettuce": 3.0,
            "radish": 4.0,
            "herbs": 1.5,
        },
        "harvest_cycles_sol": {
            "potato": 120,
            "beans": 65,
            "lettuce": 35,
            "radish": 30,
            "herbs": 45,
        },
    },
    # Document 06 — crisis playbooks
    "06": {
        "playbooks": {
            "water_recycling_failure": {
                "containment": [
                    "reduce_irrigation_by_30pct",
                    "activate_backup_water_reserve",
                ],
                "recovery_timeline_sols": 3,
            },
            "energy_budget_cut": {
                "containment": [
                    "reduce_lighting_to_minimum",
                    "lower_temperature_setpoint",
                ],
                "recovery_timeline_sols": 2,
            },
            "temperature_spike": {
                "containment": [
                    "activate_cooling_system",
                    "increase_ventilation",
                ],
                "recovery_timeline_sols": 1,
            },
            "disease_outbreak": {
                "containment": [
                    "isolate_affected_zone",
                    "apply_biological_controls",
                ],
                "recovery_timeline_sols": 7,
            },
            "co2_imbalance": {
                "containment": [
                    "adjust_co2_scrubbers",
                    "increase_plant_density",
                ],
                "recovery_timeline_sols": 2,
            },
        }
    },
}


# ---------------------------------------------------------------------------
# MCPClient
# ---------------------------------------------------------------------------

class MCPClient:
    """Synchronous wrapper around the AgentCore MCP streamable HTTP endpoint."""

    async def _async_query(self, document_id: str, query: str) -> dict:
        """Open a streamable-HTTP MCP session and call query_knowledge_base."""
        async with streamablehttp_client(MCP_ENDPOINT) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "query_knowledge_base",
                    arguments={"document_id": document_id, "query": query},
                )
                # result.content is a list of content blocks; extract text payload
                if result.content:
                    import json as _json
                    raw = result.content[0]
                    # TextContent has a .text attribute
                    text = getattr(raw, "text", None) or str(raw)
                    try:
                        return _json.loads(text)
                    except (_json.JSONDecodeError, TypeError):
                        return {"raw": text}
                return {}

    def query(self, document_id: str, query: str) -> dict:
        """
        Query the MCP Knowledge Base synchronously.

        On success: caches the result and returns ``{**result, "kb_fallback": False}``.
        On any exception: logs a warning, returns cached or hardcoded defaults
        with ``"kb_fallback": True``.
        """
        try:
            result = asyncio.run(
                asyncio.wait_for(
                    self._async_query(document_id, query),
                    timeout=MCP_TIMEOUT,
                )
            )
            KB_CACHE[document_id] = result
            return {**result, "kb_fallback": False}
        except Exception as exc:
            logger.warning(
                "MCP KB unreachable for document %s (%s: %s); using fallback.",
                document_id,
                type(exc).__name__,
                exc,
            )
            cached = KB_CACHE.get(document_id) or HARDCODED_DEFAULTS.get(document_id, {})
            return {**cached, "kb_fallback": True}
