"""
Account lookup utilities for resolving account data from Supabase.

This module provides shared account lookup functionality used by multiple
API endpoints to resolve account details from either UUID or Salesforce ID.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from ..config_store import get_supabase

logger = logging.getLogger(__name__)


@dataclass
class AccountData:
    """Container for account lookup results."""
    name: Optional[str] = None
    account_tier: Optional[str] = None
    contract_value: Optional[float] = None

    @property
    def found(self) -> bool:
        """Return True if account was found (has a name)."""
        return self.name is not None


def lookup_account(
    account_id: Optional[str] = None,
    salesforce_account_id: Optional[str] = None,
) -> AccountData:
    """
    Look up account details from Supabase by ID or Salesforce ID.

    Attempts to fetch account data using either the internal UUID (account_id)
    or the Salesforce Account ID. Returns AccountData with name, tier, and
    contract value if found.

    Args:
        account_id: Internal Supabase UUID for the account
        salesforce_account_id: Salesforce Account ID (18-char ID)

    Returns:
        AccountData with account details, or empty AccountData if not found
        or if Supabase is not configured.

    Example:
        >>> result = lookup_account(account_id="abc-123")
        >>> if result.found:
        ...     print(f"Account: {result.name}, Tier: {result.account_tier}")
    """
    if not account_id and not salesforce_account_id:
        return AccountData()

    supabase = get_supabase()
    if not supabase:
        logger.warning("Supabase not configured - cannot look up account")
        return AccountData()

    try:
        query = supabase.table("accounts").select("name, account_tier, contract_value")

        if account_id:
            query = query.eq("id", account_id)
        elif salesforce_account_id:
            query = query.eq("salesforce_id", salesforce_account_id)

        result = query.limit(1).execute()

        if result.data and len(result.data) > 0:
            account_data = result.data[0]
            logger.info(f"Fetched account from Supabase: {account_data.get('name')}")
            return AccountData(
                name=account_data.get("name"),
                account_tier=account_data.get("account_tier"),
                contract_value=account_data.get("contract_value"),
            )

        return AccountData()

    except Exception as e:
        logger.error(f"Error looking up account: {e}")
        return AccountData()
