"""
Config Loader - Simple config loading functions for crews

Loads agent and task configurations from YAML files.
Configs are cached in memory to avoid repeated disk reads.
"""

import os
import yaml
import logging
from functools import lru_cache
from typing import Dict, Any

logger = logging.getLogger(__name__)


def get_config_dir() -> str:
    """Get the config directory path."""
    return os.path.join(os.path.dirname(__file__), "config")


@lru_cache(maxsize=1)
def load_agents_config() -> Dict[str, Any]:
    """Load agents configuration from YAML (cached after first load)."""
    filepath = os.path.join(get_config_dir(), "agents.yaml")
    try:
        with open(filepath, 'r') as f:
            config = yaml.safe_load(f) or {}
            logger.debug(f"Loaded agents.yaml ({len(config)} agents)")
            return config
    except Exception as e:
        logger.warning(f"Could not load agents.yaml: {e}")
        return {}


@lru_cache(maxsize=1)
def load_tasks_config() -> Dict[str, Any]:
    """Load tasks configuration from YAML (cached after first load)."""
    filepath = os.path.join(get_config_dir(), "tasks.yaml")
    try:
        with open(filepath, 'r') as f:
            config = yaml.safe_load(f) or {}
            logger.debug(f"Loaded tasks.yaml ({len(config)} tasks)")
            return config
    except Exception as e:
        logger.warning(f"Could not load tasks.yaml: {e}")
        return {}


def clear_config_cache():
    """Clear the config cache (useful for testing or hot reloading)."""
    load_agents_config.cache_clear()
    load_tasks_config.cache_clear()
    logger.debug("Config cache cleared")
