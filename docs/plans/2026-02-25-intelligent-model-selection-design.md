# Intelligent AI Model Selection System

**Date:** February 25, 2026
**Status:** Approved
**Author:** Claude (with Ron Feathers)

## Problem Statement

The current AI model selection system treats role-based model assignments as "required" when they should be "maximum capability allowed." This leads to:

1. **Cost explosions** - Expensive models used for cheap background tasks
2. **Failures without fallback** - Requests fail when assigned model hits quota
3. **Hardcoded bypasses** - 10+ places create LLM() directly, ignoring the system
4. **No visibility** - Can't see what's being spent until the bill arrives

## Design Goals

1. **Single point of entry** - ALL AI requests go through one function
2. **Intelligent selection** - Match model capability to task importance
3. **Quality-ordered fallback** - Graceful degradation when quota is hit
4. **Cost visibility** - Track every request for spend analysis
5. **Spend protection** - Limits to prevent cost explosions

## Core Principle

> **Role assignment = maximum capability ceiling, not minimum requirement**

A Senior Manager assigned Claude Sonnet 4.6 can use that model for important tasks, but background jobs should use cheaper models automatically.

## Architecture

### Single Entry Point

```
┌─────────────────────────────────────────────────────────────┐
│                    ALL AI REQUESTS                          │
│  (Crews, Embeddings, Studio, Custom Analysis, etc.)         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              get_llm_for_task()                             │
│  • Determines task priority (LOW/MEDIUM/HIGH)               │
│  • Looks up user role (if applicable)                       │
│  • Selects appropriate model tier                           │
│  • Builds quality-ordered fallback chain                    │
│  • Logs usage for cost tracking                             │
│  • Enforces spend limits                                    │
│  • Returns LLM with fallback wrapper                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   AI Providers                              │
│         OpenAI  │  Anthropic  │  Google                     │
└─────────────────────────────────────────────────────────────┘
```

**Rule:** Zero direct `LLM()` instantiation anywhere except `ai_settings_helper.py`

### Model Tier System

Models classified by capability level:

| Tier | Models | Use Case |
|------|--------|----------|
| PREMIUM | Claude Sonnet 4.6, GPT-4.1, Gemini 3 Pro | Critical decisions, executive output |
| STANDARD | Claude Haiku 4.5, GPT-4.1 Mini, Gemini 3 Flash | User-triggered analysis |
| ECONOMY | GPT-4.1 Nano | High-volume background tasks |

Database schema addition:
```sql
ALTER TABLE ai_models ADD COLUMN tier TEXT CHECK (tier IN ('ECONOMY', 'STANDARD', 'PREMIUM'));
```

### Task Priority System

Each task declares its importance:

```python
class TaskPriority(Enum):
    LOW = "low"        # Background batch (embeddings, nightly sync)
    MEDIUM = "medium"  # User-triggered (call analysis, project sentiment)
    HIGH = "high"      # Critical automated (dashboard scores, executive briefings)
```

Priority determines model selection strategy:

| Priority | Starting Model | Fallback Strategy |
|----------|----------------|-------------------|
| HIGH | User's assigned model | Quality-ordered (same tier first) |
| MEDIUM | User's assigned model | Quality-ordered (same tier first) |
| LOW | Cheapest available | Cost-ordered (cheapest first) |

### Quality-Ordered Fallback

When assigned model fails (quota/credit error):

**Example: Senior Manager with Claude Sonnet 4.6, HIGH priority task**

```
1. Claude Sonnet 4.6 (PREMIUM, assigned) → quota fail
2. GPT-4.1 (PREMIUM, alternate provider)
3. Gemini 3 Pro (PREMIUM, third provider)
4. GPT-4.1 Mini (STANDARD, step down)
5. Gemini 3 Flash (STANDARD, cheapest standard)
6. GPT-4.1 Nano (ECONOMY, last resort)
```

**Example: Any user, LOW priority task (embeddings)**

```
1. GPT-4.1 Nano (ECONOMY, cheapest)
2. Gemini 3 Flash (STANDARD, if economy unavailable)
3. GPT-4.1 Mini (STANDARD, alternate)
```

### API Design

```python
def get_llm_for_task(
    task_priority: TaskPriority,
    user_id: Optional[str] = None,
    task_name: Optional[str] = None,
) -> LLM:
    """
    Get an LLM configured with intelligent model selection and fallback.

    Args:
        task_priority: Importance level (LOW/MEDIUM/HIGH)
        user_id: Optional user ID for role-based ceiling
        task_name: Optional name for logging/tracking

    Returns:
        LLM instance with fallback chain configured
    """
    pass

def run_with_smart_fallback(
    crew_factory: Callable[[LLM], BaseCrew],
    run_args: Dict[str, Any],
    task_priority: TaskPriority,
    user_id: Optional[str] = None,
    task_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run a crew with intelligent model selection and quality-ordered fallback.

    Replaces the current run_with_fallback() function.
    """
    pass
```

### Crew Integration

Each crew declares its priority:

```python
class CallAnalysisCrew(BaseCrew):
    task_priority = TaskPriority.MEDIUM  # User-triggered
    task_name = "call_analysis"

class ExecutiveBriefingCrew(BaseCrew):
    task_priority = TaskPriority.HIGH  # Critical output
    task_name = "executive_briefing"

class EmbeddingProcessor:
    task_priority = TaskPriority.LOW  # Background batch
    task_name = "embedding_generation"
```

### Multi-Tier Within Crew (CSM Coaching Pattern)

Some crews need different models for different agents:

```python
class CsmCoachingCrew(BaseCrew):
    def __init__(self, user_id=None):
        super().__init__(user_id)

        # Data analysis agents - use cheap model
        self.analysis_llm = get_llm_for_task(
            task_priority=TaskPriority.LOW,
            user_id=user_id,
            task_name="csm_coaching_analysis",
        )

        # Synthesis/coaching agent - use quality model
        self.coaching_llm = get_llm_for_task(
            task_priority=TaskPriority.HIGH,
            user_id=user_id,
            task_name="csm_coaching_synthesis",
        )
```

## Hardcoded Bypasses to Remove

The following direct LLM instantiations must be refactored:

| File | Line | Current | Change To |
|------|------|---------|-----------|
| `main.py` | 622 | `LLM(model=OPENAI_MODEL_NAME)` | `get_llm_for_task(LOW)` |
| `main.py` | 1738 | `LLM(model=OPENAI_MODEL_NAME)` | `get_llm_for_task(MEDIUM, user_id)` |
| `csm_coaching_crew.py` | 38 | `LLM(model=FAST_LLM_MODEL)` | `get_llm_for_task(LOW)` |
| `routes/studio.py` | 96-102 | `LLM(model=OPENAI_MODEL_NAME)` | `get_llm_for_task(MEDIUM, user_id)` |
| `avoma_agent_example.py` | 29 | `LLM(model=OPENAI_MODEL_NAME)` | `get_llm_for_task(LOW)` |
| `base_crew.py` | 90 | `LLM(model=DEFAULT)` | Keep but use new defaults |

### Environment Variable Cleanup

Remove from Railway:
- `OPENAI_MODEL_NAME` - Prevents bypass, model selection is now intelligent

Keep but rename for clarity:
- `FAST_LLM_MODEL` → Remove (no longer needed)
- Keep API keys: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`

## Cost Control

### Usage Logging

New table to track every AI request:

```sql
CREATE TABLE ai_usage_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    user_id UUID REFERENCES users(id),
    task_name TEXT NOT NULL,
    task_priority TEXT NOT NULL,
    model_requested TEXT,
    model_used TEXT NOT NULL,
    provider TEXT NOT NULL,
    tier TEXT NOT NULL,
    fallback_attempts INTEGER DEFAULT 0,
    tokens_input INTEGER,
    tokens_output INTEGER,
    estimated_cost_usd DECIMAL(10,6),
    success BOOLEAN NOT NULL,
    error_message TEXT,
    execution_time_ms INTEGER
);

CREATE INDEX idx_ai_usage_logs_timestamp ON ai_usage_logs(timestamp);
CREATE INDEX idx_ai_usage_logs_task_name ON ai_usage_logs(task_name);
CREATE INDEX idx_ai_usage_logs_user_id ON ai_usage_logs(user_id);
```

### Spend Limits

```python
SPEND_LIMITS = {
    "daily_usd": 100.0,      # Pause all requests if exceeded
    "hourly_usd": 20.0,      # Alert threshold
    "per_request_usd": 1.0,  # Reject suspiciously expensive single requests
}
```

### Circuit Breakers

```python
CIRCUIT_BREAKER_CONFIG = {
    "failures_before_open": 5,      # Open after 5 consecutive failures
    "recovery_timeout_seconds": 300, # Try again after 5 minutes
    "half_open_max_requests": 3,    # Test with 3 requests before full open
}
```

## Migration Strategy

### Phase 1: Database & Core (Day 1)
- Add `tier` column to `ai_models` table
- Backfill tier values for existing models
- Create `ai_usage_logs` table
- Implement `get_llm_for_task()` function
- Implement `run_with_smart_fallback()` function
- Unit tests for fallback logic

### Phase 2: Refactor Existing Fallbacks (Day 2)
- Update 4 crews already using `run_with_fallback`:
  - `account-analysis`
  - `sentiment`
  - `call-analysis`
  - `drilldown`
- Add task priority to each
- Test in production with monitoring

### Phase 3: Remove Hardcoded Bypasses (Day 3)
- Refactor `main.py` sandbox-test endpoint
- Refactor `main.py` custom-analysis endpoint
- Refactor `routes/studio.py` endpoints
- Refactor `csm_coaching_crew.py` tiered pattern
- Remove `OPENAI_MODEL_NAME` from Railway

### Phase 4: Roll Out to Remaining Crews (Days 4-5)
- Add fallback to 30 remaining crew endpoints
- Prioritize by importance:
  - HIGH priority crews first (7 crews)
  - MEDIUM priority crews (15 crews)
  - LOW priority crews (8 crews)

### Phase 5: Cost Visibility (Day 6)
- Enable usage logging
- Create cost tracking queries
- Set up spend limit alerts
- Admin dashboard integration

## Success Criteria

1. **Zero direct LLM() calls** - `grep "LLM(" src/` only shows `ai_settings_helper.py`
2. **All crews have priority** - Every crew declares `task_priority`
3. **Fallback works** - When OpenAI quota hits, requests succeed via Anthropic/Google
4. **Cost tracked** - Every AI request logged with estimated cost
5. **Spend protected** - Daily limit prevents runaway costs
6. **No regressions** - All existing functionality works

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Breaking production during refactor | Phased rollout, feature flags |
| Wrong tier assignment | Review with stakeholders, easy to adjust in DB |
| Fallback latency | Monitor P95 latency, tune timeouts |
| Missing a hardcoded bypass | Grep audit before/after, code review |
| Cost tracking overhead | Async logging, batch inserts |

## Appendix: Model Tier Reference

### PREMIUM Tier
| Provider | Model | Cost (per 1M tokens) |
|----------|-------|---------------------|
| Anthropic | claude-sonnet-4-6-20260217 | $3/$15 |
| OpenAI | gpt-4.1 | $2.50/$10 |
| Google | gemini-3-pro | $1.25/$5 |

### STANDARD Tier
| Provider | Model | Cost (per 1M tokens) |
|----------|-------|---------------------|
| Anthropic | claude-haiku-4-5-20251001 | $0.80/$4 |
| OpenAI | gpt-4.1-mini | $0.40/$1.60 |
| Google | gemini-3-flash | $0.075/$0.30 |
| Google | gemini-2.5-flash | $0.075/$0.30 |

### ECONOMY Tier
| Provider | Model | Cost (per 1M tokens) |
|----------|-------|---------------------|
| OpenAI | gpt-4.1-nano | $0.10/$0.40 |
