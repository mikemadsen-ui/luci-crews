"""
Generic MCP Client for CrewAI
Provides access to all configured MCP servers and their tools.
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Read-only tool allowlists per server.
# Only these tools are passed to the LLM to keep token usage under control.
# Each MCP hub connection downloads ALL tools (~30+), but most are write ops
# (create, update, delete, execute_apex) that analysis crews don't need.
# Adding all tools would exceed OpenAI's TPM limits (231K tokens vs 30K limit).
TOOL_ALLOWLIST = {
    "avoma": {
        "list_meetings",
        "get_meeting",
        "get_meeting_notes",
        # get_meeting_transcript excluded — transcripts are huge and blow up context
    },
    "salesforce": {
        "salesforce_query",
        "salesforce_search",
        "salesforce_get_record",
        "salesforce_describe",
    },
    "snowflake": {
        "snowflake_query",
        "snowflake_list_databases",
        "snowflake_list_schemas",
        "snowflake_list_tables",
        "snowflake_describe_table",
    },
    "hubspot": {
        "hubspot_search_contacts",
        "hubspot_search_companies",
        "hubspot_search_deals",
        "hubspot_get_contact",
        "hubspot_get_company",
        "hubspot_get_deal",
    },
    "zendesk": {
        "zendesk_get_tickets",
        "zendesk_get_ticket",
        "zendesk_get_ticket_comments",
    },
    "userevidence": {
        "userevidence_search_assets",
        "userevidence_get_asset",
    },
}

# MCP server configurations
MCP_SERVERS = {
    "avoma": {
        "name": "Avoma",
        "description": "Meeting intelligence - search meetings, get transcripts and notes",
        "type": "http",
        "url": os.environ.get("AVOMA_MCP_URL", "https://mcp.avoma.com/mcp"),
        "auth": {
            "type": "bearer",
            "key": os.environ.get("AVOMA_API_KEY"),
        },
    },
    "salesforce": {
        "name": "Salesforce",
        "description": "CRM data - query accounts, contacts, opportunities, cases",
        "type": "remote",
        "url": "https://mcp-hub.leandata.workers.dev/mcp/sse",
        "auth": {
            "type": "bearer",
            "key": os.environ.get("LEANDATA_MCP_API_KEY", "mcp_oXv-00wBrDMbPOSAu0fdGbZQ6cX_pbVO9HyZdot70pE"),
        },
        "prefix": "salesforce_",
    },
    "snowflake": {
        "name": "Snowflake",
        "description": "Data warehouse - run SQL queries against analytics data",
        "type": "remote",
        "url": "https://mcp-hub.leandata.workers.dev/mcp/sse",
        "auth": {
            "type": "bearer",
            "key": os.environ.get("LEANDATA_MCP_API_KEY", "mcp_oXv-00wBrDMbPOSAu0fdGbZQ6cX_pbVO9HyZdot70pE"),
        },
        "prefix": "snowflake_",
    },
    "hubspot": {
        "name": "HubSpot",
        "description": "Marketing automation - search contacts, companies, deals, engagements",
        "type": "remote",
        "url": "https://mcp-hub.leandata.workers.dev/mcp/sse",
        "auth": {
            "type": "bearer",
            "key": os.environ.get("LEANDATA_MCP_API_KEY", "mcp_oXv-00wBrDMbPOSAu0fdGbZQ6cX_pbVO9HyZdot70pE"),
        },
        "prefix": "hubspot_",
    },
    "zendesk": {
        "name": "Zendesk",
        "description": "Support tickets - get tickets, comments, create and update tickets",
        "type": "remote",
        "url": "https://mcp-hub.leandata.workers.dev/mcp/sse",
        "auth": {
            "type": "bearer",
            "key": os.environ.get("LEANDATA_MCP_API_KEY", "mcp_oXv-00wBrDMbPOSAu0fdGbZQ6cX_pbVO9HyZdot70pE"),
        },
        "prefix": "zendesk_",
    },
    "userevidence": {
        "name": "UserEvidence",
        "description": "Customer proof points - search testimonials, case studies, stats",
        "type": "remote",
        "url": "https://mcp-hub.leandata.workers.dev/mcp/sse",
        "auth": {
            "type": "bearer",
            "key": os.environ.get("LEANDATA_MCP_API_KEY", "mcp_oXv-00wBrDMbPOSAu0fdGbZQ6cX_pbVO9HyZdot70pE"),
        },
        "prefix": "userevidence_",
    },
}


def _sanitize_tool_schemas(tools: List[Any]) -> List[Any]:
    """
    Sanitize MCP tool schemas to be compatible with OpenAI's function calling API.

    Fixes two classes of issues from mcpadapt's raw MCP schema passthrough:

    1. json_schema_extra contains None values (enum: null, items: null) and
       empty arrays (anyOf: []) that OpenAI rejects with errors like
       "None is not of type 'object', 'boolean'" and "[] should be non-empty".

    2. Fields typed as `dict` produce `type: object, additionalProperties: true`
       in the JSON schema. OpenAI requires `additionalProperties: false` on all
       nested objects, which breaks freeform dict fields. We convert these to
       `str` (JSON string) so the LLM serializes the data as a JSON string.
    """
    for tool in tools:
        schema_cls = getattr(tool, 'args_schema', None)
        if not schema_cls or not hasattr(schema_cls, 'model_fields'):
            continue

        for field_name, field_info in schema_cls.model_fields.items():
            # Fix 1: Convert freeform dict fields to str to avoid
            # OpenAI's "additionalProperties must be false" error.
            # The LLM will pass a JSON string instead of a nested object.
            if field_info.annotation is dict:
                field_info.annotation = str
                desc = field_info.description or field_name
                if "json" not in desc.lower():
                    field_info.description = f"{desc} (as a JSON string, e.g. '{{\"key\": \"value\"}}')"

            # Fix 2: Clean up json_schema_extra from mcpadapt
            extra = field_info.json_schema_extra
            if not isinstance(extra, dict):
                continue

            # Remove keys with None values (enum: null, items: null)
            # Remove empty arrays (anyOf: [])
            # Remove empty dicts for properties on leaf fields
            keys_to_remove = []
            for key, value in extra.items():
                if value is None:
                    keys_to_remove.append(key)
                elif isinstance(value, list) and len(value) == 0:
                    keys_to_remove.append(key)
                elif key == "properties" and isinstance(value, dict) and len(value) == 0:
                    keys_to_remove.append(key)
                elif key == "title" and value == "":
                    keys_to_remove.append(key)
                elif key == "additionalProperties":
                    # Remove additionalProperties from extras entirely;
                    # it's either wrong (true) or unnecessary (false)
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                del extra[key]

            # If extra is now empty, clear it entirely
            if not extra:
                field_info.json_schema_extra = None

        # Rebuild the model schema cache so changes take effect
        if hasattr(schema_cls, 'model_rebuild'):
            try:
                schema_cls.model_rebuild(force=True)
            except Exception:
                pass  # Non-critical if rebuild fails

    return tools


class MCPClient:
    """Generic MCP client that can connect to any configured MCP server."""

    def __init__(self, server_names: Optional[List[str]] = None):
        """
        Initialize MCP client with selected servers.

        Args:
            server_names: List of server names to connect to. If None, loads all available.
        """
        self.server_names = server_names or list(MCP_SERVERS.keys())
        self._adapters: Dict[str, Any] = {}
        self._tools_cache: Dict[str, List[Any]] = {}

    def _get_server_params(self, server_name: str) -> Optional[Dict[str, Any]]:
        """Get MCP server connection parameters."""
        config = MCP_SERVERS.get(server_name)
        if not config:
            logger.error(f"Unknown MCP server: {server_name}")
            return None

        # Check if auth key is available
        auth_key = config["auth"].get("key")
        if not auth_key:
            logger.warning(f"No auth key configured for {server_name} - skipping")
            return None

        # Build server params based on type
        # Both Avoma and the leandata MCP hub require streamable-http transport.
        # The hub URL path contains "/sse" but actually uses streamable-http POST.
        # mcpadapt defaults to "sse" which doesn't work for either endpoint.
        return {
            "url": config["url"],
            "transport": "streamable-http",
            "headers": {
                "Authorization": f"Bearer {auth_key}"
            }
        }

    def get_tools_for_server(self, server_name: str) -> List[Any]:
        """
        Get tools from a specific MCP server.

        Args:
            server_name: Name of the MCP server (e.g., 'avoma', 'salesforce')

        Returns:
            List of CrewAI-compatible tools
        """
        if server_name in self._tools_cache:
            return self._tools_cache[server_name]

        params = self._get_server_params(server_name)
        if not params:
            return []

        try:
            from crewai_tools import MCPServerAdapter

            adapter = MCPServerAdapter(params)
            tools = adapter.tools or []

            # Sanitize schemas to fix OpenAI API compatibility issues
            # (mcpadapt passes through null/empty values that OpenAI rejects)
            tools = _sanitize_tool_schemas(tools)

            # Filter tools by prefix if specified (for hub servers that share one endpoint)
            config = MCP_SERVERS.get(server_name, {})
            prefix = config.get("prefix")
            if prefix:
                tools = [t for t in tools if hasattr(t, 'name') and t.name.startswith(prefix)]

            # Apply allowlist to keep only read/query tools.
            # This is critical for staying under OpenAI's TPM limits —
            # full tool schemas for all MCP tools exceed 230K tokens.
            allowlist = TOOL_ALLOWLIST.get(server_name)
            if allowlist:
                before_count = len(tools)
                tools = [t for t in tools if hasattr(t, 'name') and t.name in allowlist]
                if before_count != len(tools):
                    logger.info(f"Filtered {server_name} tools: {before_count} -> {len(tools)} (allowlist)")

            self._adapters[server_name] = adapter
            self._tools_cache[server_name] = tools

            logger.info(f"Connected to {server_name} MCP, got {len(tools)} tools")
            return tools

        except ImportError:
            logger.error("crewai-tools[mcp] not installed. Run: pip install 'crewai-tools[mcp]'")
            return []
        except Exception as e:
            logger.warning(f"Skipping {server_name} MCP (connection failed): {str(e)[:100]}")
            return []

    def get_all_tools(self) -> List[Any]:
        """
        Get tools from all selected MCP servers.

        Returns:
            Combined list of all tools from all servers
        """
        all_tools = []
        for server_name in self.server_names:
            tools = self.get_tools_for_server(server_name)
            all_tools.extend(tools)

        logger.info(f"Loaded {len(all_tools)} total tools from {len(self.server_names)} MCP servers")
        return all_tools

    def get_tool_descriptions(self) -> Dict[str, List[str]]:
        """
        Get descriptions of available tools organized by server.

        Returns:
            Dict mapping server names to lists of tool names
        """
        descriptions = {}
        for server_name in self.server_names:
            tools = self.get_tools_for_server(server_name)
            descriptions[server_name] = [
                getattr(t, 'name', 'unknown') for t in tools
            ]
        return descriptions

    def stop(self):
        """Stop all MCP adapter connections."""
        for server_name, adapter in self._adapters.items():
            try:
                adapter.stop()
            except Exception as e:
                logger.warning(f"Error stopping {server_name} adapter: {e}")

        self._adapters.clear()
        self._tools_cache.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


def get_mcp_tools(server_names: Optional[List[str]] = None) -> List[Any]:
    """
    Get MCP tools for use with CrewAI agents.

    Args:
        server_names: List of MCP server names to use. If None, uses all available.
                     Example: ["avoma", "salesforce", "zendesk"]

    Returns:
        List of CrewAI-compatible tools from the selected MCP servers

    Example:
        from luci_crews.mcp_client import get_mcp_tools

        # Get tools from specific servers
        tools = get_mcp_tools(["avoma", "salesforce"])

        agent = Agent(
            role="Sales Analyst",
            tools=tools,
            ...
        )
    """
    client = MCPClient(server_names)
    return client.get_all_tools()


def get_available_servers() -> Dict[str, Dict[str, str]]:
    """
    Get information about available MCP servers.

    Returns:
        Dict mapping server names to their metadata (name, description, type)
    """
    return {
        key: {
            "name": config["name"],
            "description": config["description"],
            "type": config["type"],
            "available": bool(config["auth"].get("key")),
        }
        for key, config in MCP_SERVERS.items()
    }


def test_mcp_connection(server_name: str) -> bool:
    """
    Test connection to an MCP server.

    Args:
        server_name: Name of the server to test

    Returns:
        True if connection successful, False otherwise
    """
    try:
        client = MCPClient([server_name])
        tools = client.get_tools_for_server(server_name)
        client.stop()
        return len(tools) > 0
    except Exception as e:
        logger.error(f"Connection test failed for {server_name}: {e}")
        return False
