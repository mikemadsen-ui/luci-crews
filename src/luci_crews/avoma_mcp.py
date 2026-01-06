"""
Avoma MCP Client

Provides access to Avoma meetings and transcripts via the Model Context Protocol.
Can be used both as a direct utility and to provide tools to CrewAI agents.
"""

import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# MCP server configuration
AVOMA_MCP_URL = os.environ.get("AVOMA_MCP_URL", "https://mcp.avoma.com/mcp")
AVOMA_API_KEY = os.environ.get("AVOMA_API_KEY")


class AvomaMCPClient:
    """Client for interacting with Avoma via MCP."""

    def __init__(self, api_key: Optional[str] = None, mcp_url: Optional[str] = None):
        self.api_key = api_key or AVOMA_API_KEY
        self.mcp_url = mcp_url or AVOMA_MCP_URL
        self._adapter = None
        self._tools = None

        if not self.api_key:
            logger.warning("AVOMA_API_KEY not set - Avoma MCP client will not function")

    def _get_server_params(self) -> Dict[str, Any]:
        """Get MCP server parameters with authentication."""
        return {
            "url": self.mcp_url,
            "headers": {
                "Authorization": f"Bearer {self.api_key}"
            }
        }

    def get_tools(self) -> List[Any]:
        """
        Get Avoma MCP tools for use with CrewAI agents.

        Returns a list of CrewAI-compatible tools that can be passed to agents.
        Tools include: list_meetings, get_meeting, get_meeting_transcript, get_meeting_notes
        """
        if not self.api_key:
            logger.error("Cannot get tools: AVOMA_API_KEY not set")
            return []

        try:
            from crewai_tools import MCPServerAdapter

            if self._adapter is None:
                self._adapter = MCPServerAdapter(self._get_server_params())
                self._tools = self._adapter.tools
                logger.info(f"Connected to Avoma MCP, got {len(self._tools)} tools")

            return self._tools or []
        except ImportError:
            logger.error("crewai-tools[mcp] not installed. Run: pip install crewai-tools[mcp]")
            return []
        except Exception as e:
            logger.error(f"Failed to connect to Avoma MCP: {e}")
            return []

    def list_meetings(
        self,
        crm_account_id: Optional[str] = None,
        customer_name: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        List meetings from Avoma.

        Args:
            crm_account_id: Salesforce Account ID to filter by
            customer_name: Customer name to search for
            from_date: Start date filter
            to_date: End date filter
            limit: Maximum number of meetings to return

        Returns:
            List of meeting objects
        """
        tools = self.get_tools()
        list_tool = next((t for t in tools if t.name == "list_meetings"), None)

        if not list_tool:
            logger.error("list_meetings tool not found in Avoma MCP")
            return []

        try:
            # Build filter parameters
            params = {"page_size": limit}

            if crm_account_id:
                params["crm_account_ids"] = crm_account_id

            if customer_name:
                params["customer_name"] = customer_name

            if from_date:
                params["from_date"] = from_date.isoformat()

            if to_date:
                params["to_date"] = to_date.isoformat()
            else:
                params["to_date"] = datetime.utcnow().isoformat()

            if not from_date:
                # Default to last 6 months
                params["from_date"] = (datetime.utcnow() - timedelta(days=180)).isoformat()

            result = list_tool._run(**params)
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.error(f"Error listing meetings: {e}")
            return []

    def get_meeting(self, meeting_uuid: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed meeting information.

        Args:
            meeting_uuid: The Avoma meeting UUID

        Returns:
            Meeting details dict or None
        """
        tools = self.get_tools()
        get_tool = next((t for t in tools if t.name == "get_meeting"), None)

        if not get_tool:
            logger.error("get_meeting tool not found in Avoma MCP")
            return None

        try:
            result = get_tool._run(meeting_uuid=meeting_uuid)
            return result
        except Exception as e:
            logger.error(f"Error getting meeting {meeting_uuid}: {e}")
            return None

    def get_meeting_transcript(self, meeting_uuid: str) -> Optional[str]:
        """
        Get the transcript for a meeting.

        Args:
            meeting_uuid: The Avoma meeting UUID

        Returns:
            Transcript text or None
        """
        tools = self.get_tools()
        transcript_tool = next((t for t in tools if t.name == "get_meeting_transcript"), None)

        if not transcript_tool:
            logger.error("get_meeting_transcript tool not found in Avoma MCP")
            return None

        try:
            result = transcript_tool._run(meeting_uuid=meeting_uuid)
            # Handle different response formats
            if isinstance(result, dict):
                return result.get("transcript") or result.get("text") or str(result)
            return str(result) if result else None
        except Exception as e:
            logger.error(f"Error getting transcript for {meeting_uuid}: {e}")
            return None

    def get_meeting_notes(self, meeting_uuid: str) -> Optional[Dict[str, Any]]:
        """
        Get AI-generated notes for a meeting.

        Args:
            meeting_uuid: The Avoma meeting UUID

        Returns:
            Meeting notes dict or None
        """
        tools = self.get_tools()
        notes_tool = next((t for t in tools if t.name == "get_meeting_notes"), None)

        if not notes_tool:
            logger.error("get_meeting_notes tool not found in Avoma MCP")
            return None

        try:
            result = notes_tool._run(meeting_uuid=meeting_uuid)
            return result
        except Exception as e:
            logger.error(f"Error getting notes for {meeting_uuid}: {e}")
            return None

    def fetch_transcriptions_for_account(
        self,
        salesforce_account_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Fetch transcriptions for a Salesforce account, formatted for crew consumption.

        This is a convenience method that matches the format expected by existing crews.

        Args:
            salesforce_account_id: The Salesforce Account ID
            limit: Maximum number of transcriptions to fetch

        Returns:
            List of transcription dicts in the format expected by crews
        """
        meetings = self.list_meetings(crm_account_id=salesforce_account_id, limit=limit)

        transcriptions = []
        for meeting in meetings:
            meeting_uuid = meeting.get("uuid")
            if not meeting_uuid:
                continue

            transcript = self.get_meeting_transcript(meeting_uuid)
            if transcript:
                transcriptions.append({
                    "id": meeting_uuid,
                    "transcription": transcript,
                    "meeting": {
                        "subject": meeting.get("subject"),
                        "meeting_date": meeting.get("start_at"),
                        "url": meeting.get("url"),
                    }
                })

        return transcriptions

    def stop(self):
        """Stop the MCP adapter connection."""
        if self._adapter:
            try:
                self._adapter.stop()
            except Exception as e:
                logger.warning(f"Error stopping MCP adapter: {e}")
            finally:
                self._adapter = None
                self._tools = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


# Singleton instance for convenience
_client: Optional[AvomaMCPClient] = None


def get_avoma_client() -> AvomaMCPClient:
    """Get or create a singleton Avoma MCP client."""
    global _client
    if _client is None:
        _client = AvomaMCPClient()
    return _client


def get_avoma_tools() -> List[Any]:
    """
    Get Avoma MCP tools for use with CrewAI agents.

    Example usage:
        from luci_crews.avoma_mcp import get_avoma_tools

        agent = Agent(
            role="Meeting Analyst",
            tools=get_avoma_tools(),
            ...
        )
    """
    return get_avoma_client().get_tools()
