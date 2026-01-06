"""
Mavenlink API Client

Provides access to Mavenlink workspace data including participants.
Used to find customer contact emails for Avoma meeting searches.
"""

import os
import ssl
import json
import logging
import urllib.request
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

MAVENLINK_API_URL = "https://api.mavenlink.com/api/v1"
MAVENLINK_API_TOKEN = os.environ.get("MAVENLINK_API_TOKEN")

# Email domains that are internal (LeanData employees)
INTERNAL_DOMAINS = {"leandata.com", "leandatainc.com"}


class MavenlinkClient:
    """Client for interacting with the Mavenlink API."""

    def __init__(self, api_token: Optional[str] = None):
        self.api_token = api_token or MAVENLINK_API_TOKEN
        if not self.api_token:
            logger.warning("MAVENLINK_API_TOKEN not set - Mavenlink client will not function")

    def _get_ssl_context(self) -> ssl.SSLContext:
        """Get SSL context for requests."""
        ctx = ssl.create_default_context()
        return ctx

    def _make_request(self, endpoint: str) -> Optional[Dict[str, Any]]:
        """Make authenticated request to Mavenlink API."""
        if not self.api_token:
            logger.error("Cannot make request: MAVENLINK_API_TOKEN not set")
            return None

        url = f"{MAVENLINK_API_URL}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        try:
            req = urllib.request.Request(url, headers=headers)
            ctx = self._get_ssl_context()
            with urllib.request.urlopen(req, context=ctx, timeout=30) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            logger.error(f"Mavenlink API error: {e.code} - {e.reason}")
            return None
        except Exception as e:
            logger.error(f"Mavenlink request failed: {e}")
            return None

    def get_workspace_participants(self, workspace_id: str) -> List[Dict[str, Any]]:
        """
        Get all participants for a Mavenlink workspace.

        Args:
            workspace_id: The Mavenlink workspace ID

        Returns:
            List of participant dicts with email and name
        """
        data = self._make_request(f"/workspaces/{workspace_id}?include=participants")
        if not data:
            return []

        users = data.get("users", {})
        participants = []

        for user_id, user in users.items():
            email = user.get("email_address")
            if email:
                participants.append({
                    "id": user_id,
                    "email": email,
                    "name": user.get("full_name", ""),
                    "headline": user.get("headline", ""),
                })

        return participants

    def get_customer_emails(self, workspace_id: str) -> List[str]:
        """
        Get customer (external) email addresses from a workspace.

        Filters out LeanData internal emails to return only customer contacts.

        Args:
            workspace_id: The Mavenlink workspace ID

        Returns:
            List of customer email addresses
        """
        participants = self.get_workspace_participants(workspace_id)
        customer_emails = []

        for p in participants:
            email = p.get("email", "").lower()
            if not email:
                continue

            # Extract domain
            domain = email.split("@")[-1] if "@" in email else ""

            # Skip internal domains
            if domain in INTERNAL_DOMAINS:
                continue

            customer_emails.append(email)

        logger.info(f"Found {len(customer_emails)} customer emails in workspace {workspace_id}")
        return customer_emails

    def get_customer_email_domains(self, workspace_id: str) -> List[str]:
        """
        Get unique customer email domains from a workspace.

        Args:
            workspace_id: The Mavenlink workspace ID

        Returns:
            List of unique customer email domains
        """
        emails = self.get_customer_emails(workspace_id)
        domains = set()

        for email in emails:
            domain = email.split("@")[-1] if "@" in email else ""
            if domain:
                domains.add(domain)

        return list(domains)


# Singleton instance
_client: Optional[MavenlinkClient] = None


def get_mavenlink_client() -> MavenlinkClient:
    """Get or create a singleton Mavenlink client."""
    global _client
    if _client is None:
        _client = MavenlinkClient()
    return _client


def get_customer_emails_for_workspace(workspace_id: str) -> List[str]:
    """
    Convenience function to get customer emails for a workspace.

    Args:
        workspace_id: The Mavenlink workspace ID

    Returns:
        List of customer email addresses
    """
    return get_mavenlink_client().get_customer_emails(workspace_id)
