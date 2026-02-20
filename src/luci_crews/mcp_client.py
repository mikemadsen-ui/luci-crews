"""
Lightweight MCP Client for CrewAI

Provides thin tool wrappers that call MCP servers via HTTP (JSON-RPC).
Unlike mcpadapt/MCPServerAdapter which generates massive Pydantic schemas
(231K+ tokens), these wrappers use minimal schemas (~200 tokens each)
to stay well under OpenAI's TPM limits.
"""

import os
import json
import logging
import requests
from typing import List, Dict, Any, Optional

from crewai.tools import tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MCP server connection config
# ---------------------------------------------------------------------------

AVOMA_MCP_URL = os.environ.get("AVOMA_MCP_URL", "https://mcp.avoma.com/mcp")
AVOMA_API_KEY = os.environ.get("AVOMA_API_KEY", "")

LEANDATA_MCP_URL = "https://mcp-hub.leandata.workers.dev/mcp/sse"
LEANDATA_MCP_API_KEY = os.environ.get(
    "LEANDATA_MCP_API_KEY",
    "mcp_oXv-00wBrDMbPOSAu0fdGbZQ6cX_pbVO9HyZdot70pE",
)

# ---------------------------------------------------------------------------
# Low-level MCP JSON-RPC caller
# ---------------------------------------------------------------------------

def _mcp_call(url: str, api_key: str, tool_name: str, arguments: dict) -> str:
    """
    Call an MCP tool via JSON-RPC over HTTP POST.

    MCP uses streamable-http transport: POST a JSON-RPC request,
    get back a JSON-RPC response (possibly SSE-wrapped).
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()

        # The response may be plain JSON or SSE-wrapped.
        # Try plain JSON first.
        content_type = resp.headers.get("content-type", "")
        body = resp.text.strip()

        if "text/event-stream" in content_type:
            # Parse SSE: find the last "data:" line with JSON
            result_json = None
            for line in body.split("\n"):
                line = line.strip()
                if line.startswith("data:"):
                    data_str = line[5:].strip()
                    if data_str:
                        try:
                            result_json = json.loads(data_str)
                        except json.JSONDecodeError:
                            pass
            if result_json:
                return _extract_mcp_result(result_json)
            return body[:5000]  # Fallback: return raw text (truncated)
        else:
            result_json = resp.json()
            return _extract_mcp_result(result_json)

    except requests.exceptions.Timeout:
        return "Error: MCP request timed out after 30 seconds"
    except requests.exceptions.HTTPError as e:
        return f"Error: MCP HTTP {e.response.status_code}: {e.response.text[:500]}"
    except Exception as e:
        return f"Error calling MCP tool {tool_name}: {str(e)[:500]}"


def _extract_mcp_result(result_json: dict) -> str:
    """Extract the text content from an MCP JSON-RPC response."""
    # Standard JSON-RPC response: {"result": {"content": [{"type": "text", "text": "..."}]}}
    if "result" in result_json:
        result = result_json["result"]
        if isinstance(result, dict) and "content" in result:
            parts = []
            for item in result["content"]:
                if isinstance(item, dict) and "text" in item:
                    parts.append(item["text"])
            if parts:
                text = "\n".join(parts)
                # Truncate very large responses to avoid blowing up LLM context
                if len(text) > 15000:
                    return text[:15000] + "\n\n... [truncated — response too large]"
                return text
        # Fallback: stringify the result
        text = json.dumps(result, indent=2)
        if len(text) > 15000:
            return text[:15000] + "\n\n... [truncated]"
        return text
    elif "error" in result_json:
        err = result_json["error"]
        return f"Error: {err.get('message', json.dumps(err))}"
    else:
        text = json.dumps(result_json, indent=2)
        if len(text) > 15000:
            return text[:15000] + "\n\n... [truncated]"
        return text


# ---------------------------------------------------------------------------
# Salesforce tools (via leandata MCP hub)
# ---------------------------------------------------------------------------

@tool
def salesforce_query(soql: str) -> str:
    """Run a SOQL query against Salesforce. Use salesforce_describe first to find field names.
    Example: SELECT Id, Name, StageName, Amount FROM Opportunity WHERE Id = '006...'"""
    return _mcp_call(LEANDATA_MCP_URL, LEANDATA_MCP_API_KEY, "salesforce_query", {"soql": soql})


@tool
def salesforce_describe(object_type: str) -> str:
    """Get metadata and field names for a Salesforce object. ALWAYS call this before writing SOQL.
    Example: Account, Opportunity, Contact, Case"""
    return _mcp_call(LEANDATA_MCP_URL, LEANDATA_MCP_API_KEY, "salesforce_describe", {"objectType": object_type})


@tool
def salesforce_get_record(object_type: str, record_id: str) -> str:
    """Get a Salesforce record by its ID. Returns all standard fields.
    Example: salesforce_get_record('Opportunity', '006...')"""
    return _mcp_call(LEANDATA_MCP_URL, LEANDATA_MCP_API_KEY, "salesforce_get_record", {
        "objectType": object_type,
        "recordId": record_id,
    })


@tool
def salesforce_search(sosl: str) -> str:
    """Search across Salesforce objects using SOSL. Good for finding records by name.
    Example: FIND {Acme} IN ALL FIELDS RETURNING Account(Id, Name), Contact(Id, Name)"""
    return _mcp_call(LEANDATA_MCP_URL, LEANDATA_MCP_API_KEY, "salesforce_search", {"sosl": sosl})


# ---------------------------------------------------------------------------
# Avoma tools (meeting intelligence)
# ---------------------------------------------------------------------------

@tool
def avoma_list_meetings(from_date: str, to_date: str) -> str:
    """List Avoma meetings in a date range. Dates in YYYY-MM-DD format.
    Example: avoma_list_meetings('2026-01-01', '2026-02-01')"""
    args = {"from_date": from_date, "to_date": to_date}
    return _mcp_call(AVOMA_MCP_URL, AVOMA_API_KEY, "list_meetings", args)


@tool
def avoma_get_meeting(meeting_uuid: str) -> str:
    """Get details for a specific Avoma meeting by its UUID."""
    return _mcp_call(AVOMA_MCP_URL, AVOMA_API_KEY, "get_meeting", {"uuid": meeting_uuid})


@tool
def avoma_get_meeting_notes(meeting_uuid: str) -> str:
    """Get AI-generated notes and summary for an Avoma meeting."""
    return _mcp_call(AVOMA_MCP_URL, AVOMA_API_KEY, "get_meeting_notes", {"uuid": meeting_uuid})


# ---------------------------------------------------------------------------
# Zendesk tools (support tickets)
# ---------------------------------------------------------------------------

@tool
def zendesk_get_tickets(sort_by: str = "created_at", per_page: int = 25) -> str:
    """List recent Zendesk support tickets. Sort by: created_at, updated_at, priority, status."""
    args = {"sort_by": sort_by, "per_page": per_page}
    return _mcp_call(LEANDATA_MCP_URL, LEANDATA_MCP_API_KEY, "zendesk_get_tickets", args)


@tool
def zendesk_get_ticket(ticket_id: int) -> str:
    """Get a specific Zendesk ticket by its ID."""
    return _mcp_call(LEANDATA_MCP_URL, LEANDATA_MCP_API_KEY, "zendesk_get_ticket", {"ticket_id": ticket_id})


@tool
def zendesk_get_ticket_comments(ticket_id: int) -> str:
    """Get all comments on a Zendesk ticket."""
    return _mcp_call(LEANDATA_MCP_URL, LEANDATA_MCP_API_KEY, "zendesk_get_ticket_comments", {"ticket_id": ticket_id})


# ---------------------------------------------------------------------------
# HubSpot tools (CRM/marketing)
# ---------------------------------------------------------------------------

@tool
def hubspot_search_contacts(query: str) -> str:
    """Search HubSpot contacts by name, email, or company."""
    return _mcp_call(LEANDATA_MCP_URL, LEANDATA_MCP_API_KEY, "hubspot_search_contacts", {"query": query})


@tool
def hubspot_search_companies(query: str) -> str:
    """Search HubSpot companies by name or domain."""
    return _mcp_call(LEANDATA_MCP_URL, LEANDATA_MCP_API_KEY, "hubspot_search_companies", {"query": query})


@tool
def hubspot_search_deals(query: str) -> str:
    """Search HubSpot deals by deal name."""
    return _mcp_call(LEANDATA_MCP_URL, LEANDATA_MCP_API_KEY, "hubspot_search_deals", {"query": query})


# ---------------------------------------------------------------------------
# Snowflake tools (data warehouse)
# ---------------------------------------------------------------------------

@tool
def snowflake_query(sql: str) -> str:
    """Execute a SQL query against Snowflake data warehouse."""
    return _mcp_call(LEANDATA_MCP_URL, LEANDATA_MCP_API_KEY, "snowflake_query", {"sql": sql})


@tool
def snowflake_describe_table(database: str, schema_name: str, table: str) -> str:
    """Get column information for a Snowflake table. schema_name is the Snowflake schema."""
    return _mcp_call(LEANDATA_MCP_URL, LEANDATA_MCP_API_KEY, "snowflake_describe_table", {
        "database": database, "schema": schema_name, "table": table,
    })


# ---------------------------------------------------------------------------
# UserEvidence tools (customer proof points)
# ---------------------------------------------------------------------------

@tool
def userevidence_search(query: str) -> str:
    """Search customer testimonials, case studies, and proof points."""
    return _mcp_call(LEANDATA_MCP_URL, LEANDATA_MCP_API_KEY, "userevidence_search_assets", {"query": query})


# ---------------------------------------------------------------------------
# Tool registry — maps server names to their tool functions
# ---------------------------------------------------------------------------

TOOL_REGISTRY: Dict[str, List[Any]] = {
    "salesforce": [salesforce_query, salesforce_describe, salesforce_get_record, salesforce_search],
    "avoma": [avoma_list_meetings, avoma_get_meeting, avoma_get_meeting_notes],
    "zendesk": [zendesk_get_tickets, zendesk_get_ticket, zendesk_get_ticket_comments],
    "hubspot": [hubspot_search_contacts, hubspot_search_companies, hubspot_search_deals],
    "snowflake": [snowflake_query, snowflake_describe_table],
    "userevidence": [userevidence_search],
}


def get_mcp_tools(server_names: Optional[List[str]] = None) -> List[Any]:
    """
    Get lightweight MCP tools for use with CrewAI agents.

    Args:
        server_names: List of server names to use (e.g., ["salesforce", "avoma"]).
                     If None, returns tools for all servers.

    Returns:
        List of CrewAI-compatible @tool functions
    """
    if server_names is None:
        server_names = list(TOOL_REGISTRY.keys())

    tools = []
    for name in server_names:
        server_tools = TOOL_REGISTRY.get(name, [])
        if server_tools:
            tools.extend(server_tools)
            logger.info(f"Loaded {len(server_tools)} tools for {name}")
        else:
            logger.warning(f"No tools registered for server: {name}")

    logger.info(f"Total tools loaded: {len(tools)} from {len(server_names)} servers")
    return tools


def get_available_servers() -> Dict[str, Dict[str, str]]:
    """Get information about available MCP servers."""
    return {
        name: {
            "name": name,
            "tools": [getattr(t, 'name', str(t)) for t in tools],
            "count": len(tools),
        }
        for name, tools in TOOL_REGISTRY.items()
    }
