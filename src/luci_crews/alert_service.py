"""
Alert Service

Handles crew failure alerting to email and database.
"""
import os
import hashlib
import requests
from datetime import datetime, timedelta
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


def should_alert(
    alert_type: str,
    crew_type: str,
    task_priority: str,
    supabase
) -> bool:
    """
    Check if we should send an alert (deduplication).

    Returns False if:
    - Task priority is LOW
    - Same alert already exists in last 24 hours

    Args:
        alert_type: 'billing_failure' or 'fallback_exhausted'
        crew_type: Name of the crew (e.g., 'executive_briefing')
        task_priority: 'LOW', 'MEDIUM', or 'HIGH'
        supabase: Supabase client instance

    Returns:
        True if alert should be sent, False otherwise
    """
    # Never alert on LOW priority
    if task_priority == "LOW":
        return False

    # Generate dedup hash
    today = datetime.utcnow().strftime('%Y-%m-%d')
    hash_input = f"{crew_type}:{alert_type}:{today}"
    alert_hash = hashlib.md5(hash_input.encode()).hexdigest()

    # Check if we already alerted for this today
    yesterday = datetime.utcnow() - timedelta(hours=24)
    result = supabase.table("crew_alerts").select("id") \
        .eq("alert_hash", alert_hash) \
        .gte("created_at", yesterday.isoformat()) \
        .limit(1) \
        .execute()

    return len(result.data) == 0
