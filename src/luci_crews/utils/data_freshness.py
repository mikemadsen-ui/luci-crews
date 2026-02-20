"""
Data freshness utilities for tracking staleness of underlying data sources.

This module provides helpers to collect and format metadata about when
data was last synced from external sources (Salesforce, Avoma, etc.)
"""

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional


def calculate_data_freshness(
    sync_timestamps: Dict[str, Optional[str]],
    staleness_threshold_hours: int = 24
) -> Dict[str, Any]:
    """
    Calculate data freshness metadata from sync timestamps.

    Args:
        sync_timestamps: Dict mapping data source names to last_synced_at ISO strings
                        e.g., {"accounts": "2026-02-19T10:00:00Z", "cases": "2026-02-18T08:00:00Z"}
        staleness_threshold_hours: Hours after which data is considered stale (default: 24)

    Returns:
        Dict with structure:
        {
            "sources": {"accounts": {"last_sync": "2026-02-19T10:00:00Z", "age_hours": 2}},
            "oldest_sync": "2026-02-18T08:00:00Z",
            "oldest_age_hours": 26,
            "is_stale": True,
            "warnings": ["Cases data is 26 hours old (last synced 2026-02-18T08:00:00Z)"]
        }
    """
    now = datetime.now(timezone.utc)
    sources = {}
    warnings = []
    oldest_timestamp = None
    oldest_age_hours = 0

    for source_name, timestamp_str in sync_timestamps.items():
        if not timestamp_str:
            sources[source_name] = {
                "last_sync": None,
                "age_hours": None
            }
            warnings.append(f"{source_name.capitalize()} has no sync timestamp")
            continue

        try:
            # Parse ISO timestamp
            sync_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            age_seconds = (now - sync_time).total_seconds()
            age_hours = round(age_seconds / 3600, 1)

            sources[source_name] = {
                "last_sync": timestamp_str,
                "age_hours": age_hours
            }

            # Track oldest
            if oldest_timestamp is None or sync_time < datetime.fromisoformat(oldest_timestamp.replace('Z', '+00:00')):
                oldest_timestamp = timestamp_str
                oldest_age_hours = age_hours

            # Check staleness
            if age_hours > staleness_threshold_hours:
                warnings.append(
                    f"{source_name.capitalize()} data is {age_hours:.1f} hours old "
                    f"(last synced {timestamp_str})"
                )
        except (ValueError, AttributeError) as e:
            sources[source_name] = {
                "last_sync": timestamp_str,
                "age_hours": None,
                "error": str(e)
            }
            warnings.append(f"{source_name.capitalize()} has invalid timestamp format: {timestamp_str}")

    is_stale = oldest_age_hours > staleness_threshold_hours if oldest_timestamp else False

    return {
        "sources": sources,
        "oldest_sync": oldest_timestamp,
        "oldest_age_hours": oldest_age_hours if oldest_timestamp else None,
        "is_stale": is_stale,
        "warnings": warnings if warnings else None
    }


def extract_sync_timestamps(
    data_objects: Dict[str, Any]
) -> Dict[str, Optional[str]]:
    """
    Extract last_synced_at timestamps from data objects.

    Args:
        data_objects: Dict mapping source names to data objects/lists
                     e.g., {"accounts": accountData, "cases": casesData}

    Returns:
        Dict mapping source names to ISO timestamp strings
    """
    timestamps = {}

    for source_name, data in data_objects.items():
        if not data:
            timestamps[source_name] = None
            continue

        # Handle list of objects (e.g., cases, transcriptions)
        if isinstance(data, list):
            if len(data) > 0 and isinstance(data[0], dict):
                # Get the oldest sync from the list
                sync_times = [
                    obj.get('last_synced_at')
                    for obj in data
                    if obj.get('last_synced_at')
                ]
                if sync_times:
                    # Sort and take oldest
                    sync_times.sort()
                    timestamps[source_name] = sync_times[0]
                else:
                    timestamps[source_name] = None
            else:
                timestamps[source_name] = None

        # Handle single object (e.g., account data)
        elif isinstance(data, dict):
            timestamps[source_name] = data.get('last_synced_at')

        else:
            timestamps[source_name] = None

    return timestamps
