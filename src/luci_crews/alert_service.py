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


def create_alert(
    alert_type: str,
    crew_type: str,
    task_name: Optional[str],
    task_priority: str,
    user_id: Optional[str],
    providers_tried: List[str],
    exhausted_providers: List[str],
    error_message: str,
    supabase
) -> Optional[str]:
    """
    Create an alert record and return alert ID.

    Returns None if alert should be skipped (dedup check failed).

    Args:
        alert_type: 'billing_failure' or 'fallback_exhausted'
        crew_type: Name of the crew
        task_name: Optional task identifier
        task_priority: 'LOW', 'MEDIUM', or 'HIGH'
        user_id: User ID if user-triggered, None for scheduled
        providers_tried: List of providers attempted (e.g., ['openai/gpt-4.1'])
        exhausted_providers: Providers with account-level failures
        error_message: Error message to store
        supabase: Supabase client instance

    Returns:
        Alert ID if created, None if skipped
    """
    if not should_alert(alert_type, crew_type, task_priority, supabase):
        logger.info(f"Skipping duplicate alert: {crew_type} / {alert_type}")
        return None

    # Generate hash for dedup
    today = datetime.utcnow().strftime('%Y-%m-%d')
    hash_input = f"{crew_type}:{alert_type}:{today}"
    alert_hash = hashlib.md5(hash_input.encode()).hexdigest()

    severity = "critical" if alert_type == "billing_failure" else "error"

    alert_data = {
        "alert_type": alert_type,
        "severity": severity,
        "crew_type": crew_type,
        "task_name": task_name,
        "task_priority": task_priority,
        "user_id": user_id,
        "providers_tried": providers_tried,
        "exhausted_providers": exhausted_providers,
        "error_message": error_message[:500],  # Truncate for storage
        "alert_hash": alert_hash,
    }

    try:
        result = supabase.table("crew_alerts").insert(alert_data).execute()

        if result.data and len(result.data) > 0:
            alert_id = result.data[0]["id"]
            logger.info(f"Created alert {alert_id}: {crew_type} / {alert_type}")
            return alert_id
    except Exception as e:
        logger.error(f"Failed to create alert: {e}")

    return None
