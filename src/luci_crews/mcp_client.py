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
import time
import requests
import jwt as pyjwt  # PyJWT — avoid shadowing built-in
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

# Outreach S2S (server-to-server) app credentials
# Used to generate signed JWTs for direct Outreach API enrollment.
OUTREACH_S2S_APP_UID = os.environ.get("OUTREACH_S2S_APP_UID", "")
OUTREACH_PRIVATE_KEY = os.environ.get("OUTREACH_PRIVATE_KEY", "")
OUTREACH_TOKEN_URL = "https://api.outreach.io/oauth/token"
OUTREACH_API_BASE = "https://api.outreach.io/api/v2"

# ---------------------------------------------------------------------------
# Outreach S2S JWT helpers
# ---------------------------------------------------------------------------

def _get_outreach_access_token() -> str:
    """
    Generate a signed JWT and exchange it for an Outreach access token.

    Uses Outreach S2S (server-to-server) app authentication with RS256.
    OUTREACH_S2S_APP_UID: the app UID from Outreach Settings > Apps > API.
    OUTREACH_PRIVATE_KEY: PEM private key content (set on Railway; env var).

    Private key loading priority:
    1. OUTREACH_PRIVATE_KEY env var (Railway — set as a single-line value)
    2. outreach_private.pem file in the repo root (local dev — dotenv cannot
       parse multiline PEM, so the env var is empty locally)

    Returns the access token string. Raises on auth failure.
    """
    if not OUTREACH_S2S_APP_UID:
        raise ValueError("OUTREACH_S2S_APP_UID must be set in environment")

    # 1. Try env var first (works on Railway where it's set as a proper env var)
    private_key_pem = OUTREACH_PRIVATE_KEY.replace("\\n", "\n").strip()

    # 2. Fall back to PEM file when env var is incomplete (local dev — dotenv only parses
    #    the first line of a multiline PEM, leaving the key body missing).
    #    A valid PEM has both -----BEGIN ...----- and -----END ...----- markers.
    if "-----END" not in private_key_pem:
        pem_path = os.path.join(os.path.dirname(__file__), "../../outreach_private.pem")
        pem_path = os.path.normpath(pem_path)
        if not os.path.exists(pem_path):
            raise ValueError(
                "OUTREACH_PRIVATE_KEY env var is empty and outreach_private.pem not found. "
                f"Looked at: {pem_path}"
            )
        with open(pem_path, "r") as f:
            private_key_pem = f.read().strip()
        logger.debug(f"[Outreach S2S] Loaded private key from file: {pem_path}")

    now = int(time.time())
    claims = {
        "iss": OUTREACH_S2S_APP_UID,
        "iat": now,
        "exp": now + 3600,
        "aud": "https://api.outreach.io",
    }

    # PyJWT 2.x requires bytes for RS256 private key — str raises "Could not parse public key"
    signed_jwt = pyjwt.encode(claims, private_key_pem.encode("utf-8"), algorithm="RS256")

    resp = requests.post(
        OUTREACH_TOKEN_URL,
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": signed_jwt,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    resp.raise_for_status()
    token_data = resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise ValueError(f"No access_token in Outreach token response: {token_data}")
    return access_token

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
# ZoomInfo tools (company enrichment and contact search)
# ---------------------------------------------------------------------------

@tool
def zoominfo_enrich_company(company_name: str) -> str:
    """Enrich a company with ZoomInfo firmographic data. CONSUMES CREDITS —
    only call after Salesforce validation confirms the account is a valid prospect.
    Returns: employee count, revenue, tech stack, funding stage, recent news."""
    return _mcp_call(LEANDATA_MCP_URL, LEANDATA_MCP_API_KEY, "zoominfo_enrich_company", {
        "companyName": company_name,
    })


@tool
def zoominfo_search_contacts(
    company_name: str,
    title_keywords: str,
    management_level: str = "Director",
    max_results: int = 5,
) -> str:
    """Search ZoomInfo contacts at a company. Does NOT consume credits.
    title_keywords: comma-separated keywords e.g. 'Revenue Operations,Sales Operations'.
    management_level: full string only — 'Vice President', 'Director', 'Senior Manager'.
    Never use abbreviations like 'VP'. Returns top contacts by seniority."""
    return _mcp_call(LEANDATA_MCP_URL, LEANDATA_MCP_API_KEY, "zoominfo_search_contacts", {
        "companyName": company_name,
        "titleKeywords": title_keywords,
        "managementLevel": management_level,
        "maxResults": max_results,
    })


# ---------------------------------------------------------------------------
# LUCI tools (conversation intelligence — UUID account IDs, not Salesforce IDs)
# ---------------------------------------------------------------------------

@tool
def graph_account_network(account_name: str) -> str:
    """Get the full account relationship network by account name (partial match, case-insensitive).
    Returns contacts, open/closed opportunities, parent/child account hierarchy,
    and recent meeting activity. Call AFTER salesforce_query confirms prospect
    status. Pass the account_name from the input — no UUID needed."""
    return _mcp_call(LEANDATA_MCP_URL, LEANDATA_MCP_API_KEY, "graph_account_network", {
        "accountName": account_name,
    })


@tool
def luci_list_meetings(
    search: str = "",
    from_date: str = "",
    to_date: str = "",
    account_id: str = "",
) -> str:
    """List LUCI meetings. All parameters are optional — use any combination.
    search: keyword match on meeting subject.
    from_date / to_date: date range filter in YYYY-MM-DD format.
    account_id: LUCI UUID — optional, only pass if already resolved via luci_list_accounts.
    Can be called with just a search string or date range without a UUID."""
    args: Dict[str, Any] = {}
    if search:
        args["search"] = search
    if from_date:
        args["fromDate"] = from_date
    if to_date:
        args["toDate"] = to_date
    if account_id:
        args["accountId"] = account_id
    return _mcp_call(LEANDATA_MCP_URL, LEANDATA_MCP_API_KEY, "luci_list_meetings", args)


@tool
def luci_list_accounts(query: str) -> str:
    """List LUCI accounts matching a query. Use this to resolve a Salesforce
    account name to a LUCI UUID before calling luci_search_portfolio.
    LUCI UUIDs are NOT the same as Salesforce 18-char IDs."""
    return _mcp_call(LEANDATA_MCP_URL, LEANDATA_MCP_API_KEY, "luci_list_accounts", {
        "query": query,
    })


@tool
def luci_search_portfolio(
    query: str,
    match_threshold: float = 0.35,
    data_type_filter: Optional[List[str]] = None,
    speaker_role_filter: str = "",
    match_count: int = 10,
) -> str:
    """Semantic search across the LUCI customer portfolio for pain signals and patterns.
    query: natural language e.g. '[account_name] routing pain lead assignment'.
    match_threshold: use 0.35 — 0.5 returns too few results for most signal queries.
    data_type_filter: LIST e.g. ["customer_voice", "transcription_customer"].
    speaker_role_filter: 'customer' filters to prospect speech only — not LD rep speech.
                         Always pass 'customer' in the SDR crew for signal quality.
    match_count: number of results to return (default 10).
    NEVER cite LUCI as the source in outreach — say 'hearing' or 'seeing this pattern'."""
    args: Dict[str, Any] = {
        "query": query,
        "matchThreshold": match_threshold,
        "matchCount": match_count,
    }
    if data_type_filter:
        args["dataTypeFilter"] = data_type_filter   # passes as JSON array to MCP
    if speaker_role_filter:
        args["speakerRoleFilter"] = speaker_role_filter
    return _mcp_call(LEANDATA_MCP_URL, LEANDATA_MCP_API_KEY, "luci_search_portfolio", args)


# ---------------------------------------------------------------------------
# Avoma search (company-level meeting lookup — complements existing list/get tools)
# ---------------------------------------------------------------------------

@tool
def avoma_search_meetings(account_name: str, days_back: int = 180) -> str:
    """Search Avoma for meetings related to a company name in the last N days.
    Use to detect prior LeanData relationship or contact before outreach.
    If no meetings found: set prior_meetings = false and continue — not a failure."""
    return _mcp_call(AVOMA_MCP_URL, AVOMA_API_KEY, "search_meetings", {
        "accountName": account_name,
        "daysBack": days_back,
    })


# ---------------------------------------------------------------------------
# Outreach tools (sequence management and enrollment)
# ---------------------------------------------------------------------------

@tool
def outreach_list_sequences() -> str:
    """List available Outreach sequences. Returns sequence IDs, names, and status.
    Use to confirm a sequence ID is valid before enrolling."""
    return _mcp_call(LEANDATA_MCP_URL, LEANDATA_MCP_API_KEY, "outreach_list_sequences", {})


@tool
def outreach_get_sequence(sequence_id: str) -> str:
    """Get details for a specific Outreach sequence including steps and timing."""
    return _mcp_call(LEANDATA_MCP_URL, LEANDATA_MCP_API_KEY, "outreach_get_sequence", {
        "sequenceId": sequence_id,
    })


@tool
def outreach_add_prospect_to_sequence(
    prospect_email: str,
    sequence_id: str,
    personalization: str,
) -> str:
    """Enroll a prospect in an Outreach sequence with personalized content.
    WRITE OPERATION — only call when enrollment_enabled=True, dry_run=False,
    and human_review_gate=False in qa_config. Never call in testing environment.
    personalization: JSON string with keys ai_subject_1, ai_body_1, ai_body_2,
    ai_body_3, ai_subject_4, ai_body_4.
    Step 1 is MANUAL — it appears in the Outreach task queue for human review
    before it sends. Steps 2-4 fire automatically after Step 1 is sent."""
    return _mcp_call(LEANDATA_MCP_URL, LEANDATA_MCP_API_KEY, "outreach_add_prospect_to_sequence", {
        "prospectEmail": prospect_email,
        "sequenceId": sequence_id,
        "personalization": personalization,
    })


@tool
def outreach_enroll_prospect_s2s(
    prospect_id: str,
    sequence_id: str,
    mailbox_id: str = "",
) -> str:
    """Enroll a prospect in an Outreach sequence using direct S2S JWT authentication.
    Use when the MCP hub enrollment route is unavailable or returns a scope error.
    WRITE OPERATION — only call when enrollment_enabled=True and dry_run=False.
    prospect_id: Outreach numeric prospect ID (e.g. '804416').
    sequence_id: Outreach numeric sequence ID (e.g. '5724').
    mailbox_id: Optional Outreach mailbox ID for sender assignment.
    Step 1 is MANUAL — human must send from Outreach task queue."""
    try:
        access_token = _get_outreach_access_token()
    except Exception as e:
        return f"Error: S2S token exchange failed — {str(e)[:300]}"

    payload: Dict[str, Any] = {
        "data": {
            "type": "sequenceState",
            "relationships": {
                "prospect": {"data": {"type": "prospect", "id": int(prospect_id)}},
                "sequence": {"data": {"type": "sequence", "id": int(sequence_id)}},
            },
        }
    }
    if mailbox_id:
        payload["data"]["relationships"]["mailbox"] = {
            "data": {"type": "mailbox", "id": int(mailbox_id)}
        }

    try:
        resp = requests.post(
            f"{OUTREACH_API_BASE}/sequenceStates",
            json=payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/vnd.api+json",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return json.dumps(resp.json(), indent=2)
    except requests.exceptions.HTTPError as e:
        return f"Error: Outreach API {e.response.status_code}: {e.response.text[:500]}"
    except Exception as e:
        return f"Error calling Outreach S2S API: {str(e)[:300]}"


# ---------------------------------------------------------------------------
# Tool registry — maps server names to their tool functions
# ---------------------------------------------------------------------------

TOOL_REGISTRY: Dict[str, List[Any]] = {
    "salesforce": [salesforce_query, salesforce_describe, salesforce_get_record, salesforce_search],
    "avoma": [avoma_list_meetings, avoma_get_meeting, avoma_get_meeting_notes, avoma_search_meetings],
    "zendesk": [zendesk_get_tickets, zendesk_get_ticket, zendesk_get_ticket_comments],
    "hubspot": [hubspot_search_contacts, hubspot_search_companies, hubspot_search_deals],
    "snowflake": [snowflake_query, snowflake_describe_table],
    "userevidence": [userevidence_search],
    "zoominfo": [zoominfo_enrich_company, zoominfo_search_contacts],
    "luci": [graph_account_network, luci_list_meetings, luci_list_accounts, luci_search_portfolio],
    "outreach": [outreach_list_sequences, outreach_get_sequence, outreach_add_prospect_to_sequence, outreach_enroll_prospect_s2s],
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
