"""
Config Store - Manages crew configurations with Supabase persistence

Reads from YAML files as defaults, stores overrides in Supabase.
"""

import os
import yaml
import json
import logging
from typing import Dict, Any, Optional
from supabase import create_client, Client

logger = logging.getLogger(__name__)

# Supabase client
_supabase: Optional[Client] = None


def get_supabase() -> Optional[Client]:
    """Get or create Supabase client."""
    global _supabase
    if _supabase is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if url and key:
            _supabase = create_client(url, key)
        else:
            logger.warning("Supabase not configured - configs will not persist")
    return _supabase


def get_config_dir() -> str:
    """Get the config directory path."""
    return os.path.join(os.path.dirname(__file__), "config")


def load_yaml_file(filename: str) -> Dict[str, Any]:
    """Load a YAML file from the config directory."""
    filepath = os.path.join(get_config_dir(), filename)
    try:
        with open(filepath, 'r') as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Error loading {filename}: {e}")
        return {}


def get_db_overrides(config_type: str) -> Dict[str, Any]:
    """Get config overrides from Supabase."""
    supabase = get_supabase()
    if not supabase:
        return {}

    try:
        result = supabase.table("crew_configs").select("*").eq("config_type", config_type).execute()
        overrides = {}
        for row in result.data or []:
            name = row.get("name")
            config = row.get("config")
            if name and config:
                overrides[name] = config if isinstance(config, dict) else json.loads(config)
        return overrides
    except Exception as e:
        logger.error(f"Error fetching {config_type} overrides from Supabase: {e}")
        return {}


def save_db_override(config_type: str, name: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Save a config override to Supabase. Returns dict with success and optional error."""
    supabase = get_supabase()
    if not supabase:
        error = "Supabase not configured (missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY)"
        logger.error(error)
        return {"success": False, "error": error}

    try:
        # Check if exists
        existing = supabase.table("crew_configs").select("id").eq("config_type", config_type).eq("name", name).execute()

        if existing.data:
            # Update
            supabase.table("crew_configs").update({
                "config": config,
                "updated_at": "now()"
            }).eq("config_type", config_type).eq("name", name).execute()
        else:
            # Insert
            supabase.table("crew_configs").insert({
                "config_type": config_type,
                "name": name,
                "config": config
            }).execute()

        logger.info(f"Saved {config_type} config for '{name}'")
        return {"success": True}
    except Exception as e:
        error = f"Database error: {str(e)}"
        logger.error(f"Error saving {config_type} config for '{name}': {e}")
        return {"success": False, "error": error}


def delete_db_override(config_type: str, name: str) -> bool:
    """Delete a config override from Supabase."""
    supabase = get_supabase()
    if not supabase:
        return False

    try:
        supabase.table("crew_configs").delete().eq("config_type", config_type).eq("name", name).execute()
        logger.info(f"Deleted {config_type} config for '{name}'")
        return True
    except Exception as e:
        logger.error(f"Error deleting {config_type} config for '{name}': {e}")
        return False


# =============================================================================
# Public API
# =============================================================================

def get_agents() -> Dict[str, Any]:
    """Get all agent configurations (YAML defaults + DB overrides)."""
    agents = load_yaml_file("agents.yaml")
    overrides = get_db_overrides("agent")

    # Merge overrides
    for name, config in overrides.items():
        if name in agents:
            agents[name].update(config)
        else:
            agents[name] = config

    return agents


def get_tasks() -> Dict[str, Any]:
    """Get all task configurations (YAML defaults + DB overrides)."""
    tasks = load_yaml_file("tasks.yaml")
    overrides = get_db_overrides("task")

    # Merge overrides
    for name, config in overrides.items():
        if name in tasks:
            tasks[name].update(config)
        else:
            tasks[name] = config

    return tasks


def get_agent(name: str) -> Optional[Dict[str, Any]]:
    """Get a specific agent configuration."""
    agents = get_agents()
    return agents.get(name)


def get_task(name: str) -> Optional[Dict[str, Any]]:
    """Get a specific task configuration."""
    tasks = get_tasks()
    return tasks.get(name)


def update_agent(name: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Update an agent configuration (saves to Supabase)."""
    # Get current config
    current = get_agent(name)
    if current:
        # Merge with new config
        updated = {**current, **config}
    else:
        updated = config

    # Save to database
    result = save_db_override("agent", name, updated)
    if result.get("success"):
        return {"success": True, "agent": updated}
    else:
        return {"success": False, "error": result.get("error", "Failed to save to database")}


def update_task(name: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Update a task configuration (saves to Supabase)."""
    # Get current config
    current = get_task(name)
    if current:
        # Merge with new config
        updated = {**current, **config}
    else:
        updated = config

    # Save to database
    result = save_db_override("task", name, updated)
    if result.get("success"):
        return {"success": True, "task": updated}
    else:
        return {"success": False, "error": result.get("error", "Failed to save to database")}


def reset_agent(name: str) -> Dict[str, Any]:
    """Reset an agent to its YAML default (removes DB override)."""
    if delete_db_override("agent", name):
        # Return the YAML default
        agents = load_yaml_file("agents.yaml")
        return {"success": True, "agent": agents.get(name)}
    return {"success": False, "error": "Failed to reset"}


def reset_task(name: str) -> Dict[str, Any]:
    """Reset a task to its YAML default (removes DB override)."""
    if delete_db_override("task", name):
        # Return the YAML default
        tasks = load_yaml_file("tasks.yaml")
        return {"success": True, "task": tasks.get(name)}
    return {"success": False, "error": "Failed to reset"}
