"""Tests for intelligent model selection and fallback logic."""

import os
import pytest
from unittest.mock import patch, MagicMock

from luci_crews.ai_settings_helper import (
    TaskPriority,
    ModelTier,
    get_model_tier,
    build_fallback_chain,
    get_llm_for_task,
    run_with_smart_fallback,
    TIER_ORDER,
)


class TestModelTier:
    """Tests for model tier classification."""

    def test_premium_models_classified_correctly(self):
        assert get_model_tier("claude-sonnet-4-6-20260217") == ModelTier.PREMIUM
        assert get_model_tier("gpt-4.1") == ModelTier.PREMIUM
        assert get_model_tier("gemini-3-pro") == ModelTier.PREMIUM

    def test_standard_models_classified_correctly(self):
        assert get_model_tier("gpt-4.1-mini") == ModelTier.STANDARD
        assert get_model_tier("gemini-3-flash") == ModelTier.STANDARD
        assert get_model_tier("claude-haiku-4-5-20251001") == ModelTier.STANDARD

    def test_economy_models_classified_correctly(self):
        assert get_model_tier("gpt-4.1-nano") == ModelTier.ECONOMY

    def test_unknown_model_defaults_to_standard(self):
        assert get_model_tier("unknown-model-xyz") == ModelTier.STANDARD


class TestBuildFallbackChain:
    """Tests for fallback chain construction."""

    @patch.dict(os.environ, {
        "OPENAI_API_KEY": "test-key",
        "ANTHROPIC_API_KEY": "test-key",
        "GOOGLE_API_KEY": "test-key",
    })
    def test_low_priority_starts_with_cheapest(self):
        chain = build_fallback_chain(
            starting_model="claude-sonnet-4-6-20260217",
            starting_provider="anthropic",
            task_priority=TaskPriority.LOW,
        )
        # First model should be from ECONOMY tier
        assert chain[0][1] == "gpt-4.1-nano"

    @patch.dict(os.environ, {
        "OPENAI_API_KEY": "test-key",
        "ANTHROPIC_API_KEY": "test-key",
        "GOOGLE_API_KEY": "test-key",
    })
    def test_high_priority_starts_with_assigned(self):
        chain = build_fallback_chain(
            starting_model="claude-sonnet-4-6-20260217",
            starting_provider="anthropic",
            task_priority=TaskPriority.HIGH,
        )
        # First model should be the assigned one
        assert chain[0][0] == "anthropic"
        assert chain[0][1] == "claude-sonnet-4-6-20260217"

    @patch.dict(os.environ, {
        "OPENAI_API_KEY": "test-key",
        "ANTHROPIC_API_KEY": "test-key",
        "GOOGLE_API_KEY": "test-key",
    })
    def test_fallback_chain_includes_same_tier_alternates(self):
        chain = build_fallback_chain(
            starting_model="claude-sonnet-4-6-20260217",
            starting_provider="anthropic",
            task_priority=TaskPriority.HIGH,
        )
        # Should include other PREMIUM models
        providers_in_chain = [c[0] for c in chain]
        assert "openai" in providers_in_chain
        assert "google" in providers_in_chain

    @patch.dict(os.environ, {
        "OPENAI_API_KEY": "test-key",
        # No Anthropic or Google keys
    }, clear=True)
    def test_chain_only_includes_available_providers(self):
        chain = build_fallback_chain(
            starting_model="gpt-4.1",
            starting_provider="openai",
            task_priority=TaskPriority.MEDIUM,
        )
        # Should only have OpenAI models
        for provider, model, env_var in chain:
            assert provider == "openai"


class TestGetLlmForTask:
    """Tests for get_llm_for_task() entry point."""

    @patch.dict(os.environ, {
        "OPENAI_API_KEY": "test-key",
        "ANTHROPIC_API_KEY": "test-key",
        "GOOGLE_API_KEY": "test-key",
    })
    @patch("luci_crews.ai_settings_helper.get_ai_settings_for_user")
    def test_respects_user_role_for_high_priority(self, mock_settings):
        mock_settings.return_value = MagicMock(
            provider="anthropic",
            model_id="claude-sonnet-4-6-20260217",
        )

        provider, model, env_var, chain = get_llm_for_task(
            task_priority=TaskPriority.HIGH,
            user_id="user-123",
            task_name="test",
        )

        assert provider == "anthropic"
        assert model == "claude-sonnet-4-6-20260217"
        mock_settings.assert_called_once_with("user-123")

    @patch.dict(os.environ, {
        "OPENAI_API_KEY": "test-key",
        "GOOGLE_API_KEY": "test-key",
    }, clear=True)
    def test_low_priority_ignores_user_role(self):
        provider, model, env_var, chain = get_llm_for_task(
            task_priority=TaskPriority.LOW,
            user_id="user-123",  # Should be ignored
            task_name="test",
        )

        # Should start with cheapest available
        # First model in chain should be economy tier (gpt-4.1-nano if OpenAI available)
        assert chain[0][1] == "gpt-4.1-nano"


class TestRunWithSmartFallback:
    """Tests for run_with_smart_fallback() execution."""

    @patch.dict(os.environ, {
        "OPENAI_API_KEY": "test-key",
        "ANTHROPIC_API_KEY": "test-key",
        "GOOGLE_API_KEY": "test-key",
    })
    @patch("luci_crews.ai_settings_helper.create_llm_for_provider")
    def test_returns_result_on_first_success(self, mock_create_llm):
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm

        mock_crew = MagicMock()
        mock_crew.run.return_value = {"success": True, "data": "test"}

        def crew_factory(llm):
            return mock_crew

        result = run_with_smart_fallback(
            crew_factory=crew_factory,
            run_args={"arg1": "value1"},
            task_priority=TaskPriority.MEDIUM,
            task_name="test",
        )

        assert result["success"] is True
        assert "_model_used" in result
        assert "_provider_used" in result
        assert result["_fallback_count"] == 0

    @patch.dict(os.environ, {
        "OPENAI_API_KEY": "test-key",
        "ANTHROPIC_API_KEY": "test-key",
        "GOOGLE_API_KEY": "test-key",
    })
    @patch("luci_crews.ai_settings_helper.create_llm_for_provider")
    def test_falls_back_on_quota_error(self, mock_create_llm):
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm

        call_count = [0]

        def mock_run(**kwargs):
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception("429 quota exceeded")
            return {"success": True}

        mock_crew = MagicMock()
        mock_crew.run = mock_run

        def crew_factory(llm):
            return mock_crew

        result = run_with_smart_fallback(
            crew_factory=crew_factory,
            run_args={},
            task_priority=TaskPriority.MEDIUM,
            task_name="test",
        )

        assert result["success"] is True
        assert result["_fallback_count"] == 2  # Failed twice, succeeded on third
