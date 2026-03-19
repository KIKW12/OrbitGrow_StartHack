"""
MCP client for the Mars Crop Knowledge Base via AgentCore streamable HTTP endpoint.

The Syngenta KB is a RAG system that returns markdown text chunks, not structured
JSON.  The simulation engine uses STRUCTURED_DATA (hardcoded values verified against
the KB).  Agents use query_kb() to retrieve raw text for grounding their reasoning.
"""
import asyncio
import json
import logging

from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

logger = logging.getLogger(__name__)

MCP_ENDPOINT = (
    "https://kb-start-hack-gateway-buyjtibfpg.gateway.bedrock-agentcore"
    ".us-east-2.amazonaws.com/mcp"
)
MCP_TOOL_NAME = "kb-start-hack-target___knowledge_base_retrieve"
MCP_TIMEOUT = 10  # seconds

# ---------------------------------------------------------------------------
# In-memory cache: query string -> list of text chunks
# ---------------------------------------------------------------------------
KB_CACHE: dict[str, list[str]] = {}

# ---------------------------------------------------------------------------
# Structured data for the simulation engine.
# Values verified against the Syngenta KB (docs 03, 04, 06).
# ---------------------------------------------------------------------------
STRUCTURED_DATA: dict[str, dict] = {
    # Document 03 — nutritional profiles (per kg, derived from KB per-100g values)
    "nutrition": {
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
    # Document 04 — environmental constraints & crop parameters
    "environment": {
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
    "crisis": {
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

# Backward-compat aliases used by simulation engine imports
HARDCODED_DEFAULTS = {
    "03": STRUCTURED_DATA["nutrition"],
    "04": STRUCTURED_DATA["environment"],
    "06": STRUCTURED_DATA["crisis"],
}


# ---------------------------------------------------------------------------
# Response parser — extracts text chunks from the KB RAG response
# ---------------------------------------------------------------------------

def _parse_kb_response(raw_text: str) -> list[str]:
    """
    Parse the KB response.  The endpoint returns:
      {"statusCode": 200, "body": "{\"retrieved_chunks\": [...]}"}
    Each chunk has a "content" field with markdown text.
    """
    try:
        outer = json.loads(raw_text)
        body = json.loads(outer.get("body", "{}"))
        chunks = body.get("retrieved_chunks", [])
        return [chunk["content"] for chunk in chunks if "content" in chunk]
    except (json.JSONDecodeError, TypeError, KeyError) as exc:
        logger.warning("Failed to parse KB response: %s", exc)
        return [raw_text] if raw_text else []


# ---------------------------------------------------------------------------
# MCPClient
# ---------------------------------------------------------------------------

class MCPClient:
    """Synchronous wrapper around the Syngenta MCP Knowledge Base."""

    async def _async_query(self, query: str, max_results: int = 5) -> list[str]:
        """Open a streamable-HTTP MCP session and retrieve KB chunks."""
        async with streamablehttp_client(MCP_ENDPOINT) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    MCP_TOOL_NAME,
                    arguments={"query": query, "max_results": max_results},
                )
                if result.content:
                    raw = result.content[0]
                    text = getattr(raw, "text", None) or str(raw)
                    return _parse_kb_response(text)
                return []

    def query_kb(self, query: str, max_results: int = 5) -> dict:
        """
        Query the Syngenta Knowledge Base and return text chunks.

        Returns:
            {
                "chunks": list[str],   # markdown text passages from the KB
                "kb_fallback": bool,   # True if KB was unreachable
            }
        """
        cache_key = f"{query}:{max_results}"
        try:
            # Handle case where event loop is already running (e.g. some Lambda runtimes)
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    chunks = pool.submit(
                        asyncio.run,
                        asyncio.wait_for(
                            self._async_query(query, max_results),
                            timeout=MCP_TIMEOUT,
                        ),
                    ).result(timeout=MCP_TIMEOUT + 2)
            else:
                chunks = asyncio.run(
                    asyncio.wait_for(
                        self._async_query(query, max_results),
                        timeout=MCP_TIMEOUT,
                    )
                )

            if chunks:
                KB_CACHE[cache_key] = chunks
            return {"chunks": chunks, "kb_fallback": False}

        except Exception as exc:
            logger.warning(
                "MCP KB query failed (%s: %s); using cache.", type(exc).__name__, exc
            )
            cached = KB_CACHE.get(cache_key, [])
            return {"chunks": cached, "kb_fallback": True}

    def get_structured(self, domain: str) -> dict:
        """
        Return structured data for the simulation engine.
        domain: "nutrition", "environment", or "crisis"
        """
        return STRUCTURED_DATA.get(domain, {})

    # ------------------------------------------------------------------
    # Legacy interface — keeps existing agent code working during migration.
    # Maps old document_id calls to the new interface.
    # ------------------------------------------------------------------
    _DOMAIN_QUERIES = {
        "03": ("nutrition", "daily nutritional targets and crop profiles for Mars crew"),
        "04": ("environment", "optimal environmental bands and crop growth parameters"),
        "06": ("crisis", "crisis response playbooks and containment actions"),
    }

    def query(self, document_id: str, query: str) -> dict:
        """
        Legacy interface for backward compatibility.
        Returns structured data enriched with KB text chunks.
        """
        domain, default_query = self._DOMAIN_QUERIES.get(
            document_id, (None, query)
        )

        # Get KB text chunks (uses the caller's query for relevance)
        kb_result = self.query_kb(query, max_results=3)

        # Merge structured data with KB metadata
        structured = STRUCTURED_DATA.get(domain, HARDCODED_DEFAULTS.get(document_id, {}))
        return {
            **structured,
            "kb_chunks": kb_result["chunks"],
            "kb_fallback": kb_result["kb_fallback"],
        }
