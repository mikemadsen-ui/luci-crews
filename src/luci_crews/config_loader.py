"""
Config Loader - Simple config loading functions for crews

Loads agent and task configurations from YAML files.
"""

import os
import yaml
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def get_config_dir() -> str:
    """Get the config directory path."""
    return os.path.join(os.path.dirname(__file__), "config")


def load_agents_config() -> Dict[str, Any]:
    """Load agents configuration from YAML."""
    filepath = os.path.join(get_config_dir(), "agents.yaml")
    try:
        with open(filepath, 'r') as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning(f"Could not load agents.yaml: {e}")
        return {}


def load_tasks_config() -> Dict[str, Any]:
    """Load tasks configuration from YAML."""
    filepath = os.path.join(get_config_dir(), "tasks.yaml")
    try:
        with open(filepath, 'r') as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning(f"Could not load tasks.yaml: {e}")
        return {}
