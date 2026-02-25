# Intelligent AI Model Selection - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform AI model selection from "role = required model" to "role = maximum capability ceiling" with intelligent fallback.

**Architecture:** Single entry point (`get_llm_for_task()`) for ALL AI requests. Models classified by tier (ECONOMY/STANDARD/PREMIUM). Tasks declare priority (LOW/MEDIUM/HIGH). Fallback chains built dynamically based on tier, trying same-tier alternatives before stepping down.

**Tech Stack:** Python 3.11, CrewAI, Supabase (PostgreSQL), FastAPI

**Beads Tracking:** Issues created under epic `luci-crews-9ty` through `luci-crews-t7k`

---

## Phase 1: Database & Core

### Task 1: Add Model Tier Migration

**Files:**
- Create: `supabase/migrations/210_add_model_tiers.sql` (in main luci repo)

**Step 1: Create migration file**

```sql
-- Migration: Add tier column to ai_models for intelligent model selection
-- Tiers: ECONOMY (cheapest), STANDARD (balanced), PREMIUM (best)

-- Add tier column
ALTER TABLE ai_models ADD COLUMN IF NOT EXISTS tier TEXT;

-- Add constraint
ALTER TABLE ai_models ADD CONSTRAINT ai_models_tier_check
  CHECK (tier IS NULL OR tier IN ('ECONOMY', 'STANDARD', 'PREMIUM'));

-- Backfill existing models with appropriate tiers
-- PREMIUM tier
UPDATE ai_models SET tier = 'PREMIUM' WHERE model_id IN (
  'claude-sonnet-4-6-20260217',
  'claude-sonnet-4-5-20250929',
  'gpt-4.1',
  'gpt-4o',
  'gemini-3-pro',
  'gemini-2.5-pro'
);

-- STANDARD tier
UPDATE ai_models SET tier = 'STANDARD' WHERE model_id IN (
  'claude-haiku-4-5-20251001',
  'claude-3-5-haiku-20241022',
  'gpt-4.1-mini',
  'gpt-4o-mini',
  'gemini-3-flash',
  'gemini-2.5-flash',
  'gemini-2.0-flash'
);

-- ECONOMY tier
UPDATE ai_models SET tier = 'ECONOMY' WHERE model_id IN (
  'gpt-4.1-nano'
);

-- Set default for any unclassified models
UPDATE ai_models SET tier = 'STANDARD' WHERE tier IS NULL;

-- Make tier NOT NULL after backfill
ALTER TABLE ai_models ALTER COLUMN tier SET NOT NULL;

-- Create index for tier lookups
CREATE INDEX IF NOT EXISTS idx_ai_models_tier ON ai_models(tier);
```

**Step 2: Apply migration locally**

Run (in main luci repo):
```bash
npx supabase db push
```
Expected: Migration applies successfully

**Step 3: Commit migration**

```bash
git add supabase/migrations/210_add_model_tiers.sql
git commit -m "feat: add tier column to ai_models for intelligent selection"
```

**Beads:** Close `luci-crews-ay2` when complete

---

### Task 2: Implement TaskPriority Enum

**Files:**
- Modify: `src/luci_crews/ai_settings_helper.py:1-20`

**Step 1: Add TaskPriority enum after imports**

Add after line 14 (after `from supabase import create_client, Client`):

```python
from enum import Enum


class TaskPriority(Enum):
    """Task importance level for model selection.

    LOW: Background batch tasks (embeddings, nightly sync)
         Uses cheapest available model regardless of user role.

    MEDIUM: User-triggered analysis (call analysis, project sentiment)
            Uses user's assigned model with quality-ordered fallback.

    HIGH: Critical automated tasks (dashboard scores, executive briefings)
          Uses user's assigned model with quality-ordered fallback.
    """
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ModelTier(Enum):
    """Model capability tier for fallback ordering."""
    ECONOMY = "ECONOMY"
    STANDARD = "STANDARD"
    PREMIUM = "PREMIUM"


# Tier ordering for fallback (highest to lowest)
TIER_ORDER = [ModelTier.PREMIUM, ModelTier.STANDARD, ModelTier.ECONOMY]
```

**Step 2: Run linter to verify syntax**

Run: `python -m py_compile src/luci_crews/ai_settings_helper.py`
Expected: No output (success)

**Step 3: Commit**

```bash
git add src/luci_crews/ai_settings_helper.py
git commit -m "feat: add TaskPriority and ModelTier enums"
```

**Beads:** Close `luci-crews-owx` when complete

---

### Task 3: Add Model Tier Constants

**Files:**
- Modify: `src/luci_crews/ai_settings_helper.py`

**Step 1: Add model tier mapping after TIER_ORDER**

```python
# Model tier classification (mirrors database, used as fallback)
MODEL_TIERS = {
    # PREMIUM - highest capability
    "claude-sonnet-4-6-20260217": ModelTier.PREMIUM,
    "claude-sonnet-4-5-20250929": ModelTier.PREMIUM,
    "gpt-4.1": ModelTier.PREMIUM,
    "gpt-4o": ModelTier.PREMIUM,
    "gemini-3-pro": ModelTier.PREMIUM,
    "gemini-2.5-pro": ModelTier.PREMIUM,

    # STANDARD - balanced
    "claude-haiku-4-5-20251001": ModelTier.STANDARD,
    "claude-3-5-haiku-20241022": ModelTier.STANDARD,
    "gpt-4.1-mini": ModelTier.STANDARD,
    "gpt-4o-mini": ModelTier.STANDARD,
    "gemini-3-flash": ModelTier.STANDARD,
    "gemini-2.5-flash": ModelTier.STANDARD,
    "gemini-2.0-flash": ModelTier.STANDARD,

    # ECONOMY - cheapest
    "gpt-4.1-nano": ModelTier.ECONOMY,
}


def get_model_tier(model_id: str) -> ModelTier:
    """Get the tier for a model, defaulting to STANDARD if unknown."""
    return MODEL_TIERS.get(model_id, ModelTier.STANDARD)


# Provider ordering within each tier (for fallback diversity)
TIER_PROVIDERS = {
    ModelTier.PREMIUM: [
        ("anthropic", "claude-sonnet-4-6-20260217"),
        ("openai", "gpt-4.1"),
        ("google", "gemini-3-pro"),
    ],
    ModelTier.STANDARD: [
        ("google", "gemini-3-flash"),
        ("openai", "gpt-4.1-mini"),
        ("anthropic", "claude-haiku-4-5-20251001"),
    ],
    ModelTier.ECONOMY: [
        ("openai", "gpt-4.1-nano"),
    ],
}
```

**Step 2: Run linter**

Run: `python -m py_compile src/luci_crews/ai_settings_helper.py`
Expected: No output (success)

**Step 3: Commit**

```bash
git add src/luci_crews/ai_settings_helper.py
git commit -m "feat: add model tier constants and helper"
```

---

### Task 4: Implement get_llm_for_task()

**Files:**
- Modify: `src/luci_crews/ai_settings_helper.py`

**Step 1: Add the core function**

Add before `run_with_fallback()`:

```python
def build_fallback_chain(
    starting_model: str,
    starting_provider: str,
    task_priority: TaskPriority,
) -> List[tuple]:
    """
    Build a quality-ordered fallback chain starting from the given model.

    For HIGH/MEDIUM priority: Start with assigned model, try same-tier alternates,
    then step down to lower tiers.

    For LOW priority: Start with cheapest (ECONOMY), work up if needed.

    Returns:
        List of (provider, model_id, api_key_env_var) tuples
    """
    chain = []
    seen = set()

    if task_priority == TaskPriority.LOW:
        # Cost-ordered: Start with cheapest
        for tier in reversed(TIER_ORDER):  # ECONOMY -> STANDARD -> PREMIUM
            for provider, model_id in TIER_PROVIDERS.get(tier, []):
                env_var = f"{provider.upper()}_API_KEY"
                if env_var == "GOOGLE_API_KEY":
                    env_var = "GOOGLE_API_KEY"
                api_key = os.getenv(env_var)
                if api_key and (provider, model_id) not in seen:
                    chain.append((provider, model_id, env_var))
                    seen.add((provider, model_id))
    else:
        # Quality-ordered: Start with assigned model
        starting_tier = get_model_tier(starting_model)
        env_var_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
        }

        # First, add the assigned model
        env_var = env_var_map.get(starting_provider, "OPENAI_API_KEY")
        if os.getenv(env_var):
            chain.append((starting_provider, starting_model, env_var))
            seen.add((starting_provider, starting_model))

        # Then add same-tier alternatives from other providers
        starting_tier_idx = TIER_ORDER.index(starting_tier)

        for tier in TIER_ORDER[starting_tier_idx:]:  # Same tier and below
            for provider, model_id in TIER_PROVIDERS.get(tier, []):
                env_var = env_var_map.get(provider, "OPENAI_API_KEY")
                api_key = os.getenv(env_var)
                if api_key and (provider, model_id) not in seen:
                    chain.append((provider, model_id, env_var))
                    seen.add((provider, model_id))

    return chain


def get_llm_for_task(
    task_priority: TaskPriority,
    user_id: Optional[str] = None,
    task_name: Optional[str] = None,
) -> tuple:
    """
    Get model configuration for a task based on priority and user role.

    This is the SINGLE ENTRY POINT for all AI model selection.

    Args:
        task_priority: Importance level (LOW/MEDIUM/HIGH)
        user_id: Optional user ID for role-based ceiling
        task_name: Optional name for logging

    Returns:
        Tuple of (provider, model_id, api_key_env_var, fallback_chain)
    """
    # Get user's assigned model (if user_id provided)
    if user_id and task_priority != TaskPriority.LOW:
        settings = get_ai_settings_for_user(user_id)
        starting_provider = settings.provider
        starting_model = settings.model_id
        logger.info(f"[{task_name or 'unknown'}] User {user_id} assigned: {starting_provider}/{starting_model}")
    else:
        # LOW priority or no user: use cheapest
        starting_provider = "google"
        starting_model = "gemini-3-flash"
        logger.info(f"[{task_name or 'unknown'}] Using economy model for {task_priority.value} priority")

    # Build the fallback chain
    fallback_chain = build_fallback_chain(
        starting_model=starting_model,
        starting_provider=starting_provider,
        task_priority=task_priority,
    )

    if not fallback_chain:
        raise RuntimeError("No AI providers configured. Set API keys for OpenAI, Anthropic, or Google.")

    primary = fallback_chain[0]
    logger.info(f"[{task_name or 'unknown'}] Primary: {primary[0]}/{primary[1]}, Fallbacks: {len(fallback_chain)-1}")

    return primary[0], primary[1], primary[2], fallback_chain
```

**Step 2: Run linter**

Run: `python -m py_compile src/luci_crews/ai_settings_helper.py`
Expected: No output (success)

**Step 3: Commit**

```bash
git add src/luci_crews/ai_settings_helper.py
git commit -m "feat: implement get_llm_for_task() single entry point"
```

**Beads:** Close `luci-crews-0tu` when complete

---

### Task 5: Implement run_with_smart_fallback()

**Files:**
- Modify: `src/luci_crews/ai_settings_helper.py`

**Step 1: Add enhanced fallback function**

Replace or add alongside `run_with_fallback()`:

```python
def run_with_smart_fallback(
    crew_factory: Callable,
    run_args: Dict[str, Any],
    task_priority: TaskPriority,
    user_id: Optional[str] = None,
    task_name: Optional[str] = None,
    max_retries: int = 6,
) -> Dict[str, Any]:
    """
    Run a crew with intelligent model selection and quality-ordered fallback.

    This function:
    1. Determines the best starting model based on task priority and user role
    2. Builds a quality-ordered fallback chain
    3. Tries each model in sequence until success
    4. Logs usage for cost tracking

    Args:
        crew_factory: Callable that takes an LLM and returns a crew instance
        run_args: Arguments to pass to crew.run()
        task_priority: Task importance (LOW/MEDIUM/HIGH)
        user_id: Optional user ID for role-based model ceiling
        task_name: Optional name for logging
        max_retries: Maximum number of models to try

    Returns:
        The crew result dict with metadata about model used

    Raises:
        RuntimeError: If all models fail
    """
    # Get model configuration and fallback chain
    primary_provider, primary_model, _, fallback_chain = get_llm_for_task(
        task_priority=task_priority,
        user_id=user_id,
        task_name=task_name,
    )

    last_error = None
    providers_tried = []

    for i, (provider, model_id, env_var) in enumerate(fallback_chain[:max_retries]):
        providers_tried.append(f"{provider}/{model_id}")

        try:
            logger.info(f"[{task_name or 'crew'}] Attempt {i+1}/{min(len(fallback_chain), max_retries)}: {provider}/{model_id}")

            # Create LLM for this provider
            llm = create_llm_for_provider(provider, model_id, os.getenv(env_var))

            # Create and run the crew
            crew = crew_factory(llm)
            result = crew.run(**run_args)

            logger.info(f"[{task_name or 'crew'}] Success with {provider}/{model_id}")

            # Add metadata
            if isinstance(result, dict):
                result["_model_used"] = model_id
                result["_provider_used"] = provider
                result["_task_priority"] = task_priority.value
                result["_providers_tried"] = providers_tried
                result["_fallback_count"] = i

            return result

        except Exception as e:
            last_error = e
            error_str = str(e).lower()

            if is_quota_error(e):
                logger.warning(f"[{task_name or 'crew'}] {provider} quota/credit error, trying next...")
                continue
            else:
                # Non-quota error - log but still try next provider
                logger.error(f"[{task_name or 'crew'}] {provider} error: {str(e)[:200]}")
                # For non-quota errors, we could either:
                # 1. Raise immediately (strict)
                # 2. Try next provider (lenient)
                # Using lenient approach for better availability
                continue

    # All providers failed
    raise RuntimeError(
        f"All AI providers failed for {task_name or 'crew'}. "
        f"Tried: {', '.join(providers_tried)}. "
        f"Last error: {str(last_error)[:200]}"
    )
```

**Step 2: Run linter**

Run: `python -m py_compile src/luci_crews/ai_settings_helper.py`
Expected: No output (success)

**Step 3: Commit**

```bash
git add src/luci_crews/ai_settings_helper.py
git commit -m "feat: implement run_with_smart_fallback() with tier-based fallback"
```

**Beads:** Close `luci-crews-11u` when complete

---

### Task 6: Write Unit Tests for Fallback Logic

**Files:**
- Create: `tests/test_model_selection.py`

**Step 1: Create test file**

```python
"""Tests for intelligent model selection and fallback logic."""

import os
import pytest
from unittest.mock import patch, MagicMock

from src.luci_crews.ai_settings_helper import (
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
    })
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
    @patch("src.luci_crews.ai_settings_helper.get_ai_settings_for_user")
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
    })
    def test_low_priority_ignores_user_role(self):
        provider, model, env_var, chain = get_llm_for_task(
            task_priority=TaskPriority.LOW,
            user_id="user-123",  # Should be ignored
            task_name="test",
        )

        # Should start with cheapest, not user's assigned
        # First available economy model
        assert chain[0][1] in ["gpt-4.1-nano", "gemini-3-flash"]


class TestRunWithSmartFallback:
    """Tests for run_with_smart_fallback() execution."""

    @patch.dict(os.environ, {
        "OPENAI_API_KEY": "test-key",
        "ANTHROPIC_API_KEY": "test-key",
        "GOOGLE_API_KEY": "test-key",
    })
    @patch("src.luci_crews.ai_settings_helper.create_llm_for_provider")
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
    @patch("src.luci_crews.ai_settings_helper.create_llm_for_provider")
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
```

**Step 2: Run tests**

Run: `pytest tests/test_model_selection.py -v`
Expected: All tests pass

**Step 3: Commit**

```bash
git add tests/test_model_selection.py
git commit -m "test: add unit tests for intelligent model selection"
```

**Beads:** Close `luci-crews-a5q` when complete

---

## Phase 2: Refactor Existing Crews

### Task 7: Update call-analysis Crew

**Files:**
- Modify: `src/luci_crews/main.py:876-896`
- Modify: `src/luci_crews/crews/call_analysis_crew.py`

**Step 1: Add task_priority to CallAnalysisCrew**

In `src/luci_crews/crews/call_analysis_crew.py`, after line 23:

```python
class CallAnalysisCrew(BaseCrew):
    """Crew for analyzing individual call transcripts."""

    task_priority = TaskPriority.MEDIUM  # User-triggered analysis
    task_name = "call_analysis"
```

Add import at top:
```python
from ..ai_settings_helper import TaskPriority
```

**Step 2: Update main.py to use run_with_smart_fallback**

Replace lines 876-896 in `src/luci_crews/main.py`:

```python
        # Use intelligent model selection with quality-ordered fallback
        from .ai_settings_helper import run_with_smart_fallback, TaskPriority

        def crew_factory(llm):
            return CallAnalysisCrew(user_id=request.userId, llm=llm)

        run_args = {
            "transcript_segments": request.transcriptSegments,
            "speakers": request.speakers,
            "project_name": request.projectName,
            "account_name": request.accountName,
            "meeting_subject": request.meetingSubject,
            "meeting_date": request.meetingDate,
            "attendees": request.attendees,
            "implementation_stage": request.implementationStage,
            "project_context": request.projectContext,
        }

        result = run_with_smart_fallback(
            crew_factory=crew_factory,
            run_args=run_args,
            task_priority=TaskPriority.MEDIUM,
            user_id=request.userId,
            task_name="call_analysis",
        )
```

**Step 3: Test locally**

Run: `python -c "from src.luci_crews.crews.call_analysis_crew import CallAnalysisCrew; print(CallAnalysisCrew.task_priority)"`
Expected: `TaskPriority.MEDIUM`

**Step 4: Commit**

```bash
git add src/luci_crews/main.py src/luci_crews/crews/call_analysis_crew.py
git commit -m "feat: update call-analysis to use smart fallback with MEDIUM priority"
```

**Beads:** Close `luci-crews-mil` when complete

---

### Task 8-10: Update Remaining 3 Crews

Repeat Task 7 pattern for:
- `account-analysis` (MEDIUM priority) - `luci-crews-iiu`
- `sentiment` (MEDIUM priority) - `luci-crews-bk9`
- `drilldown` (MEDIUM priority) - `luci-crews-dpl`

Each follows same pattern:
1. Add `task_priority` class attribute
2. Update endpoint to use `run_with_smart_fallback()`
3. Test and commit

---

## Phase 3: Remove Hardcoded Bypasses

### Task 11: Refactor sandbox-test Endpoint

**Files:**
- Modify: `src/luci_crews/main.py:621-626`

**Step 1: Replace hardcoded LLM**

Change from:
```python
llm = LLM(
    model=os.environ.get("OPENAI_MODEL_NAME", "gpt-4o-mini"),
    api_key=os.environ.get("OPENAI_API_KEY"),
)
```

To:
```python
from .ai_settings_helper import get_llm_for_task, create_llm_for_provider, TaskPriority

provider, model_id, env_var, _ = get_llm_for_task(
    task_priority=TaskPriority.LOW,  # Sandbox test is low priority
    task_name="sandbox_test",
)
llm = create_llm_for_provider(provider, model_id, os.getenv(env_var))
```

**Step 2: Commit**

```bash
git add src/luci_crews/main.py
git commit -m "refactor: sandbox-test uses get_llm_for_task() instead of hardcoded model"
```

**Beads:** Close `luci-crews-ejo` when complete

---

### Task 12: Refactor custom-analysis Endpoint

**Files:**
- Modify: `src/luci_crews/main.py:1738-1741`

**Step 1: Replace hardcoded LLM (same pattern as Task 11)**

```python
provider, model_id, env_var, _ = get_llm_for_task(
    task_priority=TaskPriority.MEDIUM,  # User-triggered
    user_id=request.userId if hasattr(request, 'userId') else None,
    task_name="custom_analysis",
)
llm = create_llm_for_provider(provider, model_id, os.getenv(env_var))
```

**Step 2: Commit**

```bash
git add src/luci_crews/main.py
git commit -m "refactor: custom-analysis uses get_llm_for_task() instead of hardcoded model"
```

**Beads:** Close `luci-crews-yws` when complete

---

### Task 13: Refactor studio.py Endpoints

**Files:**
- Modify: `src/luci_crews/routes/studio.py:83-102`

**Step 1: Add import at top**

```python
from ..ai_settings_helper import get_llm_for_task, create_llm_for_provider, TaskPriority
```

**Step 2: Replace all hardcoded LLM() calls**

Find all instances of:
```python
llm = LLM(model=..., api_key=...)
```

Replace with:
```python
provider, model_id, env_var, _ = get_llm_for_task(
    task_priority=TaskPriority.MEDIUM,
    task_name="studio",
)
llm = create_llm_for_provider(provider, model_id, os.getenv(env_var))
```

**Step 3: Commit**

```bash
git add src/luci_crews/routes/studio.py
git commit -m "refactor: studio routes use get_llm_for_task() instead of hardcoded model"
```

**Beads:** Close `luci-crews-c42` when complete

---

### Task 14: Refactor csm_coaching_crew.py

**Files:**
- Modify: `src/luci_crews/crews/csm_coaching_crew.py:36-47`

**Step 1: Replace hardcoded tiered LLMs**

Change from:
```python
self.fast_llm = LLM(
    model=os.getenv("FAST_LLM_MODEL", "gpt-4o-mini"),
    api_key=os.environ.get("OPENAI_API_KEY"),
)
self.quality_llm = self.llm
```

To:
```python
from ..ai_settings_helper import get_llm_for_task, create_llm_for_provider, TaskPriority

# Fast model for data analysis agents
fast_provider, fast_model, fast_env, _ = get_llm_for_task(
    task_priority=TaskPriority.LOW,
    task_name="csm_coaching_analysis",
)
self.fast_llm = create_llm_for_provider(fast_provider, fast_model, os.getenv(fast_env))

# Quality model for coaching synthesis
quality_provider, quality_model, quality_env, _ = get_llm_for_task(
    task_priority=TaskPriority.HIGH,
    user_id=user_id,
    task_name="csm_coaching_synthesis",
)
self.quality_llm = create_llm_for_provider(quality_provider, quality_model, os.getenv(quality_env))

logger.info(f"[CSM Coaching] Tiered: analysis={fast_provider}/{fast_model}, synthesis={quality_provider}/{quality_model}")
```

**Step 2: Commit**

```bash
git add src/luci_crews/crews/csm_coaching_crew.py
git commit -m "refactor: csm_coaching uses get_llm_for_task() for tiered model selection"
```

**Beads:** Close `luci-crews-6rj` when complete

---

### Task 15: Remove OPENAI_MODEL_NAME from Railway

**Step 1: Remove the environment variable**

Run:
```bash
railway variables delete OPENAI_MODEL_NAME
```

Or via Railway dashboard: Remove `OPENAI_MODEL_NAME` variable

**Step 2: Verify removal**

Run:
```bash
railway variables | grep MODEL
```
Expected: No `OPENAI_MODEL_NAME` in output

**Step 3: Document in commit**

```bash
git commit --allow-empty -m "ops: remove OPENAI_MODEL_NAME from Railway - model selection is now intelligent"
```

**Beads:** Close `luci-crews-ypr` when complete

---

## Phase 4: Rollout to Remaining Crews

### Task 16-45: Add Smart Fallback to 30 Remaining Crews

For each crew endpoint without fallback, follow this pattern:

1. **Determine priority:**
   - HIGH: Executive briefings, dashboard scores, forecasts
   - MEDIUM: User-triggered analysis (most crews)
   - LOW: Background batch jobs

2. **Add task_priority to crew class**

3. **Update endpoint to use run_with_smart_fallback()**

4. **Test and commit**

**Crew Priority Assignments:**

| Priority | Crews |
|----------|-------|
| HIGH | executive-briefing, qbr-summary, strategic-action |
| MEDIUM | sales_pipeline, account, implementation, sc-prep, feature-extraction, agenda-generation, call-verification, project-analysis, email-draft, renewal-readiness, expansion-specialist, opportunity, meddpicc-gap-actions, competitive, support_resolution, support_training, all coaching crews |
| LOW | sandbox-test (already done), embedding-related |

---

## Phase 5: Cost Visibility (Future)

### Task 46: Create ai_usage_logs Table

See design doc for schema. Implementation deferred to after core rollout.

---

## Verification Checklist

After implementation, verify:

```bash
# 1. No direct LLM() calls outside ai_settings_helper.py
grep -r "LLM(" src/luci_crews --include="*.py" | grep -v ai_settings_helper.py | grep -v "# LLM"
# Expected: No results (or only comments)

# 2. All crews have task_priority
grep -r "task_priority" src/luci_crews/crews --include="*.py"
# Expected: Every crew file listed

# 3. No OPENAI_MODEL_NAME in Railway
railway variables | grep OPENAI_MODEL_NAME
# Expected: No results

# 4. Tests pass
pytest tests/test_model_selection.py -v
# Expected: All pass
```

---

## Rollback Plan

If issues arise:

1. **Revert to old fallback:**
   - Change `run_with_smart_fallback` calls back to `run_with_fallback`
   - Re-add `OPENAI_MODEL_NAME` to Railway

2. **Database rollback:**
   - Tier column is additive, no rollback needed

3. **Full revert:**
   - `git revert` the implementation commits
   - Redeploy previous version
