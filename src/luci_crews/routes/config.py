"""Configuration management endpoints for Crew Studio.

This module contains endpoints for managing agent and task configurations:
- Get/update/reset agent configurations
- Get/update/reset task configurations
- Configurations are stored in Supabase with YAML files as defaults
"""

import logging

from fastapi import APIRouter, HTTPException

from ..models import ConfigUpdateRequest
from .. import config_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])


# =============================================================================
# Agent Configuration Endpoints
# =============================================================================


@router.get("/agents")
async def get_agents_config():
    """Get all agent configurations (YAML defaults + DB overrides)."""
    try:
        agents = config_store.get_agents()
        return {"agents": agents}
    except Exception as e:
        logger.error(f"Error getting agents config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_name}")
async def get_agent_config(agent_name: str):
    """Get a specific agent configuration."""
    try:
        agent = config_store.get_agent(agent_name)
        if agent is None:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
        return {"agent": agent, "name": agent_name}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting agent '{agent_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/agents/{agent_name}")
async def update_agent_config(agent_name: str, config: ConfigUpdateRequest):
    """Update an agent configuration (persists to Supabase)."""
    try:
        # Convert to dict, removing None values
        config_dict = {k: v for k, v in config.dict().items() if v is not None}

        if not config_dict:
            raise HTTPException(status_code=400, detail="No configuration provided")

        result = config_store.update_agent(agent_name, config_dict)

        if result.get("success"):
            logger.info(f"Updated agent '{agent_name}'")
            return {"success": True, "agent": result.get("agent"), "name": agent_name}
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to update"))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating agent '{agent_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/agents/{agent_name}")
async def reset_agent_config(agent_name: str):
    """Reset an agent to its YAML defaults (removes DB overrides)."""
    try:
        result = config_store.reset_agent(agent_name)

        if result.get("success"):
            logger.info(f"Reset agent '{agent_name}' to defaults")
            return {"success": True, "agent": result.get("agent"), "name": agent_name}
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to reset"))

    except Exception as e:
        logger.error(f"Error resetting agent '{agent_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Task Configuration Endpoints
# =============================================================================


@router.get("/tasks")
async def get_tasks_config():
    """Get all task configurations (YAML defaults + DB overrides)."""
    try:
        tasks = config_store.get_tasks()
        return {"tasks": tasks}
    except Exception as e:
        logger.error(f"Error getting tasks config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_name}")
async def get_task_config(task_name: str):
    """Get a specific task configuration."""
    try:
        task = config_store.get_task(task_name)
        if task is None:
            raise HTTPException(status_code=404, detail=f"Task '{task_name}' not found")
        return {"task": task, "name": task_name}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting task '{task_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/tasks/{task_name}")
async def update_task_config(task_name: str, config: ConfigUpdateRequest):
    """Update a task configuration (persists to Supabase)."""
    try:
        # Convert to dict, removing None values
        config_dict = {k: v for k, v in config.dict().items() if v is not None}

        if not config_dict:
            raise HTTPException(status_code=400, detail="No configuration provided")

        result = config_store.update_task(task_name, config_dict)

        if result.get("success"):
            logger.info(f"Updated task '{task_name}'")
            return {"success": True, "task": result.get("task"), "name": task_name}
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to update"))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating task '{task_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tasks/{task_name}")
async def reset_task_config(task_name: str):
    """Reset a task to its YAML defaults (removes DB overrides)."""
    try:
        result = config_store.reset_task(task_name)

        if result.get("success"):
            logger.info(f"Reset task '{task_name}' to defaults")
            return {"success": True, "task": result.get("task"), "name": task_name}
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to reset"))

    except Exception as e:
        logger.error(f"Error resetting task '{task_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))
