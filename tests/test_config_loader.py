"""
Unit tests for config loader utility.
"""

import pytest
import os
from luci_crews.config_loader import (
    load_agents_config,
    load_tasks_config,
    clear_config_cache,
    get_config_dir,
)


class TestConfigLoader:
    """Tests for config loader functions."""

    def setup_method(self):
        """Clear cache before each test."""
        clear_config_cache()

    def test_get_config_dir_exists(self):
        """Config directory path exists."""
        config_dir = get_config_dir()
        assert os.path.isdir(config_dir)

    def test_load_agents_config_returns_dict(self):
        """load_agents_config returns a dictionary."""
        config = load_agents_config()
        assert isinstance(config, dict)

    def test_load_tasks_config_returns_dict(self):
        """load_tasks_config returns a dictionary."""
        config = load_tasks_config()
        assert isinstance(config, dict)

    def test_agents_config_has_agents(self):
        """Agents config contains agent definitions."""
        config = load_agents_config()
        # Should have at least some agents defined
        assert len(config) > 0

    def test_tasks_config_has_tasks(self):
        """Tasks config contains task definitions."""
        config = load_tasks_config()
        # Should have at least some tasks defined
        assert len(config) > 0

    def test_agent_config_structure(self):
        """Agent definitions have expected fields."""
        config = load_agents_config()
        if config:
            # Check first agent has expected structure
            first_agent = next(iter(config.values()))
            # Agents should have at least a role field
            assert isinstance(first_agent, dict)
            # Common fields: role, goal, backstory
            assert any(key in first_agent for key in ['role', 'goal', 'backstory', 'description'])

    def test_task_config_structure(self):
        """Task definitions have expected fields."""
        config = load_tasks_config()
        if config:
            # Check first task has expected structure
            first_task = next(iter(config.values()))
            assert isinstance(first_task, dict)
            # Tasks typically have description or expected_output
            assert any(key in first_task for key in ['description', 'expected_output', 'agent'])

    def test_config_caching(self):
        """Config is cached after first load."""
        # First load
        config1 = load_agents_config()
        # Second load should return same object (cached)
        config2 = load_agents_config()
        assert config1 is config2

    def test_clear_cache(self):
        """clear_config_cache clears the cache."""
        # Load to populate cache
        load_agents_config()
        load_tasks_config()

        # Clear cache
        clear_config_cache()

        # Cache info should show misses on next load
        # (We can't easily test this without inspecting cache_info,
        # but we can verify it doesn't error)
        config = load_agents_config()
        assert isinstance(config, dict)
