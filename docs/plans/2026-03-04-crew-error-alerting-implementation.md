# Crew Error Alerting System - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add email and database alerting for crew failures due to billing issues and complete fallback exhaustion.

**Architecture:** Hook into existing `run_with_smart_fallback()` to detect critical failures, save alerts to Supabase `crew_alerts` table, and trigger email via luci-worker's existing Gmail infrastructure. Includes deduplication to prevent alert spam.

**Tech Stack:** Python (luci-crews), TypeScript (luci-worker), Supabase PostgreSQL, Gmail API

---

## Task 1: Add Python Dependencies

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add requests library to dependencies**

Edit `pyproject.toml` and add `requests>=2.31.0` to the dependencies array:

```toml
dependencies = [
    "crewai[anthropic,google-genai,tools]>=0.86.0",
    "crewai-tools[mcp]>=0.33.0",
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "python-dotenv>=1.0.0",
    "supabase>=2.0.0",
    "httpx>=0.27.0",
    "pydantic>=2.0.0",
    "urllib3>=2.6.3",
    "requests>=2.31.0",
]
```

**Step 2: Install dependencies**

Run: `cd /Users/ron.feathers/GitHub/LUCI/luci-crews && pip install -e .`
Expected: Successfully installed packages with no errors

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "feat: add requests dependency for alert email triggering

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Create Database Migration

**Files:**
- Create: `/Users/ron.feathers/GitHub/LUCI/luci/supabase/migrations/XXX_add_crew_alerts_table.sql`

**Step 1: Create migration file**

Create new migration file (use next sequential number):

```sql
-- Add crew_alerts table for tracking crew failures
CREATE TABLE crew_alerts (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  -- Alert classification
  alert_type TEXT NOT NULL,
  severity TEXT NOT NULL,

  -- Context
  crew_type TEXT NOT NULL,
  task_name TEXT,
  task_priority TEXT NOT NULL,
  user_id UUID REFERENCES users(id),

  -- Failure details
  providers_tried TEXT[] NOT NULL,
  exhausted_providers TEXT[],
  error_message TEXT NOT NULL,
  full_error TEXT,

  -- Email tracking
  email_sent BOOLEAN DEFAULT FALSE,
  email_sent_at TIMESTAMPTZ,
  email_error TEXT,

  -- Deduplication
  alert_hash TEXT,

  CONSTRAINT crew_alerts_alert_type_check
    CHECK (alert_type IN ('billing_failure', 'fallback_exhausted')),
  CONSTRAINT crew_alerts_severity_check
    CHECK (severity IN ('critical', 'error')),
  CONSTRAINT crew_alerts_task_priority_check
    CHECK (task_priority IN ('LOW', 'MEDIUM', 'HIGH'))
);

-- Indexes for common queries
CREATE INDEX idx_crew_alerts_created ON crew_alerts(created_at DESC);
CREATE INDEX idx_crew_alerts_type ON crew_alerts(alert_type, created_at DESC);
CREATE INDEX idx_crew_alerts_hash ON crew_alerts(alert_hash);
CREATE INDEX idx_crew_alerts_email_sent ON crew_alerts(email_sent, created_at DESC);

-- RLS policies (admin-only access)
ALTER TABLE crew_alerts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Admin users can view all alerts"
  ON crew_alerts FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM user_roles
      WHERE user_roles.user_id = auth.uid()
      AND user_roles.role = 'admin'
    )
  );
```

**Step 2: Note - Migration will be applied separately**

This migration needs to be applied to Supabase via the deployment process. For now, we'll test with local Supabase instance or staging.

**Step 3: Commit**

```bash
git add supabase/migrations/XXX_add_crew_alerts_table.sql
git commit -m "feat: add crew_alerts table migration

Tracks crew failures with email status and deduplication support.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Create Alert Service Module

**Files:**
- Create: `src/luci_crews/alert_service.py`
- Create: `tests/test_alert_service.py`

**Step 1: Write failing test for should_alert()**

Create `tests/test_alert_service.py`:

```python
"""Tests for alert service."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock
from src.luci_crews.alert_service import should_alert


def test_should_alert_returns_false_for_low_priority():
    """LOW priority tasks should never alert."""
    supabase = Mock()

    result = should_alert(
        alert_type="billing_failure",
        crew_type="test_crew",
        task_priority="LOW",
        supabase=supabase
    )

    assert result is False
    supabase.table.assert_not_called()


def test_should_alert_returns_false_for_duplicate_in_24h():
    """Same alert within 24h should be skipped."""
    # Mock Supabase to return existing alert
    supabase = Mock()
    supabase.table.return_value.select.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value.data = [{"id": "123"}]

    result = should_alert(
        alert_type="billing_failure",
        crew_type="test_crew",
        task_priority="MEDIUM",
        supabase=supabase
    )

    assert result is False


def test_should_alert_returns_true_for_new_alert():
    """New alert should be allowed."""
    # Mock Supabase to return no existing alerts
    supabase = Mock()
    supabase.table.return_value.select.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value.data = []

    result = should_alert(
        alert_type="billing_failure",
        crew_type="test_crew",
        task_priority="MEDIUM",
        supabase=supabase
    )

    assert result is True
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/ron.feathers/GitHub/LUCI/luci-crews && pytest tests/test_alert_service.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.luci_crews.alert_service'"

**Step 3: Implement should_alert() function**

Create `src/luci_crews/alert_service.py`:

```python
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
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/ron.feathers/GitHub/LUCI/luci-crews && pytest tests/test_alert_service.py::test_should_alert_returns_false_for_low_priority -v`
Expected: PASS

Run: `cd /Users/ron.feathers/GitHub/LUCI/luci-crews && pytest tests/test_alert_service.py::test_should_alert_returns_false_for_duplicate_in_24h -v`
Expected: PASS

Run: `cd /Users/ron.feathers/GitHub/LUCI/luci-crews && pytest tests/test_alert_service.py::test_should_alert_returns_true_for_new_alert -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/luci_crews/alert_service.py tests/test_alert_service.py
git commit -m "feat: add alert deduplication check

Prevents alert spam by checking for duplicates within 24h window.
LOW priority tasks never alert.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Add create_alert() Function

**Files:**
- Modify: `src/luci_crews/alert_service.py`
- Modify: `tests/test_alert_service.py`

**Step 1: Write failing test for create_alert()**

Add to `tests/test_alert_service.py`:

```python
from src.luci_crews.alert_service import create_alert


def test_create_alert_returns_none_when_should_not_alert():
    """Alert creation should be skipped if dedup check fails."""
    supabase = Mock()
    # Mock existing alert (should_alert returns False)
    supabase.table.return_value.select.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value.data = [{"id": "123"}]

    result = create_alert(
        alert_type="billing_failure",
        crew_type="test_crew",
        task_name="test_task",
        task_priority="MEDIUM",
        user_id="user123",
        providers_tried=["openai/gpt-4.1"],
        exhausted_providers=["anthropic"],
        error_message="Test error",
        supabase=supabase
    )

    assert result is None


def test_create_alert_inserts_and_returns_id():
    """Successful alert creation returns alert ID."""
    supabase = Mock()
    # No existing alert
    supabase.table.return_value.select.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value.data = []
    # Mock insert result
    supabase.table.return_value.insert.return_value.execute.return_value.data = [{"id": "alert-id-123"}]

    result = create_alert(
        alert_type="billing_failure",
        crew_type="test_crew",
        task_name="test_task",
        task_priority="MEDIUM",
        user_id="user123",
        providers_tried=["openai/gpt-4.1", "anthropic/claude-sonnet-4-6"],
        exhausted_providers=["anthropic"],
        error_message="Test error message",
        supabase=supabase
    )

    assert result == "alert-id-123"
    # Verify insert was called
    supabase.table.return_value.insert.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/ron.feathers/GitHub/LUCI/luci-crews && pytest tests/test_alert_service.py::test_create_alert_returns_none_when_should_not_alert -v`
Expected: FAIL with "ImportError: cannot import name 'create_alert'"

**Step 3: Implement create_alert() function**

Add to `src/luci_crews/alert_service.py`:

```python
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
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/ron.feathers/GitHub/LUCI/luci-crews && pytest tests/test_alert_service.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/luci_crews/alert_service.py tests/test_alert_service.py
git commit -m "feat: add create_alert function

Inserts alert records to crew_alerts table with full context.
Skips if deduplication check fails.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Add trigger_email() Function

**Files:**
- Modify: `src/luci_crews/alert_service.py`
- Modify: `tests/test_alert_service.py`

**Step 1: Write failing test for trigger_email()**

Add to `tests/test_alert_service.py`:

```python
from unittest.mock import patch
from src.luci_crews.alert_service import trigger_email


@patch('src.luci_crews.alert_service.requests.post')
def test_trigger_email_calls_worker_endpoint(mock_post):
    """trigger_email should POST to luci-worker endpoint."""
    mock_post.return_value.ok = True

    trigger_email("alert-id-123")

    # Verify POST was called with correct URL and payload
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert "alert_id" in call_args.kwargs['json']
    assert call_args.kwargs['json']['alert_id'] == "alert-id-123"
    assert call_args.kwargs['timeout'] == 5


@patch('src.luci_crews.alert_service.requests.post')
def test_trigger_email_handles_failure_gracefully(mock_post):
    """Email trigger failures should not raise exceptions."""
    mock_post.side_effect = Exception("Connection failed")

    # Should not raise
    trigger_email("alert-id-123")
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/ron.feathers/GitHub/LUCI/luci-crews && pytest tests/test_alert_service.py::test_trigger_email_calls_worker_endpoint -v`
Expected: FAIL with "ImportError: cannot import name 'trigger_email'"

**Step 3: Implement trigger_email() function**

Add to `src/luci_crews/alert_service.py`:

```python
def trigger_email(alert_id: str) -> None:
    """
    Trigger email send via luci-worker endpoint.

    Fire-and-forget: errors are logged but don't propagate.
    Alert is still saved to database even if email fails.

    Args:
        alert_id: ID of the alert to send email for
    """
    worker_url = os.getenv("LUCI_WORKER_URL", "http://localhost:8080")

    try:
        response = requests.post(
            f"{worker_url}/api/alerts/send",
            json={"alert_id": alert_id},
            timeout=5  # Quick timeout for fire-and-forget
        )

        if not response.ok:
            logger.warning(f"Email trigger failed: {response.status_code}")
    except Exception as e:
        logger.warning(f"Failed to trigger alert email: {e}")
        # Don't raise - alert is still saved to DB
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/ron.feathers/GitHub/LUCI/luci-crews && pytest tests/test_alert_service.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/luci_crews/alert_service.py tests/test_alert_service.py
git commit -m "feat: add trigger_email function

POSTs to luci-worker to send alert email via Gmail API.
Fire-and-forget design - errors logged but don't block.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Integrate Alert Service with Fallback Logic

**Files:**
- Modify: `src/luci_crews/ai_settings_helper.py`

**Step 1: Add import statements**

Add to top of `src/luci_crews/ai_settings_helper.py` (after existing imports):

```python
# Import alert service (add after existing imports)
from .alert_service import create_alert, trigger_email
```

**Step 2: Add alerting logic to run_with_smart_fallback()**

In `run_with_smart_fallback()` function, find the section at the end where all providers have failed (after the for loop). Replace the existing raise statement with:

```python
    # All providers failed - create alert before raising
    from .alert_service import create_alert, trigger_email

    # Determine alert type
    if exhausted_providers:
        alert_type = "billing_failure"
    else:
        alert_type = "fallback_exhausted"

    # Create alert
    supabase = get_supabase_client()
    if supabase:
        try:
            alert_id = create_alert(
                alert_type=alert_type,
                crew_type=task_name or "unknown",
                task_name=task_name,
                task_priority=task_priority.value,
                user_id=user_id,
                providers_tried=providers_tried,
                exhausted_providers=list(exhausted_providers),
                error_message=str(last_error),
                supabase=supabase
            )

            # Trigger email if alert was created
            if alert_id:
                trigger_email(alert_id)
        except Exception as alert_err:
            # Log but don't let alert failures block the original error
            logger.error(f"Failed to create alert: {alert_err}")

    # Raise original error
    raise RuntimeError(
        f"All AI providers failed for {task_name or 'crew'}. "
        f"Tried: {', '.join(providers_tried)}. "
        f"Exhausted providers: {', '.join(exhausted_providers) or 'none'}. "
        f"Last error: {str(last_error)[:200]}"
    )
```

**Step 3: Test integration manually**

This requires actual Supabase connection and will be tested in end-to-end testing. For now, verify code compiles:

Run: `cd /Users/ron.feathers/GitHub/LUCI/luci-crews && python -m py_compile src/luci_crews/ai_settings_helper.py`
Expected: No output (successful compilation)

**Step 4: Commit**

```bash
git add src/luci_crews/ai_settings_helper.py
git commit -m "feat: integrate alert service with fallback logic

Creates alert and triggers email when all providers fail.
Handles both billing failures and complete exhaustion.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Add TypeScript Email Endpoint

**Files:**
- Modify: `/Users/ron.feathers/GitHub/LUCI/luci-worker/src/server.ts`

**Step 1: Add /api/alerts/send endpoint**

Find the section in `createServer()` function where other POST endpoints are defined. Add the new endpoint:

```typescript
// Add after other API endpoints
app.post('/api/alerts/send', async (req, res) => {
  const { alert_id } = req.body;

  if (!alert_id) {
    return res.status(400).json({ error: 'alert_id required' });
  }

  try {
    const { sendCrewAlert } = await import('./lib/notification-service');
    const sent = await sendCrewAlert(supabase, logger, alert_id);

    res.json({ sent });
  } catch (error: any) {
    logger.error(`Alert send error: ${error.message}`);
    res.status(500).json({ error: error.message });
  }
});
```

**Step 2: Verify TypeScript compiles**

Run: `cd /Users/ron.feathers/GitHub/LUCI/luci-worker && npm run typecheck`
Expected: Error about `sendCrewAlert` not existing (we'll add it next)

**Step 3: Commit**

```bash
cd /Users/ron.feathers/GitHub/LUCI/luci-worker
git add src/server.ts
git commit -m "feat: add /api/alerts/send endpoint

Receives alert_id from luci-crews and triggers email send.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Add TypeScript Email Service Function

**Files:**
- Modify: `/Users/ron.feathers/GitHub/LUCI/luci-worker/src/lib/notification-service.ts`

**Step 1: Add sendCrewAlert function**

Add to end of `notification-service.ts`:

```typescript
/**
 * Send a crew alert email.
 * Fetches alert from Supabase and sends formatted email via Gmail API.
 */
export async function sendCrewAlert(
  supabase: SupabaseClient,
  logger: { log: Function; warn: Function; error: Function },
  alertId: string,
): Promise<boolean> {
  if (!isEmailConfigured()) {
    logger.warn('Email not configured — skipping crew alert');
    return false;
  }

  // Fetch alert
  const { data: alert, error } = await supabase
    .from('crew_alerts')
    .select('*')
    .eq('id', alertId)
    .single();

  if (error || !alert) {
    logger.error(`Alert not found: ${alertId}`);
    return false;
  }

  const subject = `🚨 Luci Crew Alert: ${alert.crew_type} - ${alert.alert_type}`;

  const html = `
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:600px;margin:0 auto;">
      <div style="background:#dc2626;color:white;padding:16px 24px;border-radius:8px 8px 0 0;">
        <h1 style="margin:0;font-size:18px;">🚨 Crew Failure Alert</h1>
      </div>
      <div style="background:white;padding:20px 24px;border:1px solid #e2e8f0;border-top:none;">
        <p style="margin:0 0 8px;font-size:14px;"><strong>Crew:</strong> ${alert.crew_type}</p>
        <p style="margin:0 0 8px;font-size:14px;"><strong>Alert Type:</strong> ${alert.alert_type}</p>
        <p style="margin:0 0 8px;font-size:14px;"><strong>Severity:</strong> ${alert.severity}</p>
        <p style="margin:0 0 8px;font-size:14px;"><strong>Priority:</strong> ${alert.task_priority}</p>
        <p style="margin:0 0 16px;font-size:14px;"><strong>Time:</strong> ${new Date(alert.created_at).toLocaleString()}</p>

        <h3 style="margin:16px 0 8px;font-size:15px;">Failure Details</h3>
        <p style="margin:0 0 8px;font-size:13px;"><strong>Providers Tried:</strong> ${alert.providers_tried.join(', ')}</p>
        ${alert.exhausted_providers?.length > 0 ? `<p style="margin:0 0 8px;font-size:13px;color:#dc2626;"><strong>Exhausted:</strong> ${alert.exhausted_providers.join(', ')}</p>` : ''}

        <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:6px;padding:12px;margin-top:12px;">
          <p style="margin:0;font-size:12px;color:#991b1b;font-family:monospace;white-space:pre-wrap;">${alert.error_message}</p>
        </div>

        <div style="margin-top:16px;padding:12px;background:#fef3c7;border:1px solid #fcd34d;border-radius:6px;">
          <p style="margin:0;font-size:13px;color:#92400e;">
            ${alert.alert_type === 'billing_failure'
              ? '⚠️ Provider account exhausted - add credits or check billing settings'
              : '⚠️ All fallback providers failed - check provider status and quotas'}
          </p>
        </div>
      </div>
      <div style="padding:12px 24px;font-size:11px;color:#9ca3af;border:1px solid #e2e8f0;border-top:none;border-radius:0 0 8px 8px;background:#f9fafb;">
        Alert ID: ${alert.id} &middot; ${new Date().toISOString()}
      </div>
    </div>`;

  const plainText = `
LUCI Crew Alert

Crew: ${alert.crew_type}
Alert Type: ${alert.alert_type}
Severity: ${alert.severity}
Priority: ${alert.task_priority}
Time: ${new Date(alert.created_at).toLocaleString()}

Providers Tried: ${alert.providers_tried.join(', ')}
${alert.exhausted_providers?.length > 0 ? `Exhausted: ${alert.exhausted_providers.join(', ')}` : ''}

Error: ${alert.error_message}

${alert.alert_type === 'billing_failure'
  ? 'ACTION REQUIRED: Provider account exhausted - add credits or check billing settings'
  : 'ACTION REQUIRED: All fallback providers failed - check provider status and quotas'}

Alert ID: ${alert.id}
  `.trim();

  const sent = await sendEmail(subject, html, plainText);

  if (sent) {
    await supabase.from('crew_alerts').update({
      email_sent: true,
      email_sent_at: new Date().toISOString(),
    }).eq('id', alertId);
    logger.log(`Crew alert email sent: ${alert.crew_type}`);
  } else {
    await supabase.from('crew_alerts').update({
      email_error: 'Failed to send via Gmail API',
    }).eq('id', alertId);
    logger.error(`Failed to send crew alert email: ${alertId}`);
  }

  return sent;
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd /Users/ron.feathers/GitHub/LUCI/luci-worker && npm run typecheck`
Expected: No errors

**Step 3: Build to verify**

Run: `cd /Users/ron.feathers/GitHub/LUCI/luci-worker && npm run build`
Expected: Build succeeds with no errors

**Step 4: Commit**

```bash
cd /Users/ron.feathers/GitHub/LUCI/luci-worker
git add src/lib/notification-service.ts
git commit -m "feat: add sendCrewAlert email service

Fetches alert from Supabase and sends formatted email.
Updates email_sent status after delivery.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Environment Configuration

**Files:**
- Modify: `/Users/ron.feathers/GitHub/LUCI/luci-crews/.env.example`
- Modify: `/Users/ron.feathers/GitHub/LUCI/luci-worker/.env.example`

**Step 1: Update luci-crews .env.example**

Add to `/Users/ron.feathers/GitHub/LUCI/luci-crews/.env.example`:

```bash
# Alert Configuration
LUCI_WORKER_URL=http://localhost:8080  # URL of luci-worker service (use Railway URL in production)
```

**Step 2: Update luci-worker .env.example**

Verify these already exist in `/Users/ron.feathers/GitHub/LUCI/luci-worker/.env.example`:

```bash
# Gmail API Configuration (for alert emails)
GMAIL_USER=notifications@leandata.com
GMAIL_CLIENT_ID=<oauth2-client-id>
GMAIL_CLIENT_SECRET=<oauth2-client-secret>
GMAIL_REFRESH_TOKEN=<refresh-token>
NOTIFICATION_EMAIL_TO=admin@leandata.com,ops@leandata.com
```

**Step 3: Commit**

```bash
cd /Users/ron.feathers/GitHub/LUCI/luci-crews
git add .env.example
git commit -m "docs: add LUCI_WORKER_URL to env example

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 10: End-to-End Testing

**Files:**
- Create: `/Users/ron.feathers/GitHub/LUCI/luci-crews/tests/test_alert_integration.py`

**Step 1: Create integration test**

Create `tests/test_alert_integration.py`:

```python
"""
Integration test for alert system.

This test requires:
- Supabase connection with crew_alerts table
- luci-worker running locally or mock server
"""
import pytest
from unittest.mock import Mock, patch
from src.luci_crews.alert_service import create_alert, trigger_email
from src.luci_crews.ai_settings_helper import get_supabase_client


@pytest.mark.skip(reason="Requires Supabase and luci-worker setup")
def test_alert_flow_integration():
    """
    End-to-end test of alert creation and email trigger.

    This test is skipped by default. To run:
    1. Ensure Supabase is running with crew_alerts table
    2. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY
    3. Run: pytest tests/test_alert_integration.py -v -s
    """
    supabase = get_supabase_client()

    # Create alert
    alert_id = create_alert(
        alert_type="billing_failure",
        crew_type="test_integration_crew",
        task_name="test_task",
        task_priority="MEDIUM",
        user_id=None,
        providers_tried=["anthropic/claude-sonnet-4-6", "openai/gpt-4.1"],
        exhausted_providers=["anthropic"],
        error_message="Integration test error message",
        supabase=supabase
    )

    assert alert_id is not None

    # Trigger email (this will attempt to POST to luci-worker)
    # In real test, you'd want to mock the requests.post call
    with patch('src.luci_crews.alert_service.requests.post') as mock_post:
        mock_post.return_value.ok = True
        trigger_email(alert_id)
        mock_post.assert_called_once()

    # Cleanup - delete test alert
    supabase.table("crew_alerts").delete().eq("id", alert_id).execute()
```

**Step 2: Run Python tests**

Run: `cd /Users/ron.feathers/GitHub/LUCI/luci-crews && pytest tests/ -v`
Expected: All tests PASS (integration test skipped)

**Step 3: Manual testing plan**

Document manual test steps in commit message (to be executed after deployment):

1. Set invalid ANTHROPIC_API_KEY in luci-crews
2. Trigger executive briefing crew
3. Verify alert appears in crew_alerts table
4. Verify email received
5. Attempt same failure again within 24h - verify no duplicate email

**Step 4: Commit**

```bash
cd /Users/ron.feathers/GitHub/LUCI/luci-crews
git add tests/test_alert_integration.py
git commit -m "test: add integration test for alert system

Includes manual testing plan for post-deployment validation.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 11: Documentation

**Files:**
- Create: `/Users/ron.feathers/GitHub/LUCI/luci-crews/docs/ALERTING.md`

**Step 1: Create alerting documentation**

Create `docs/ALERTING.md`:

```markdown
# Crew Error Alerting

Automatic alerting for crew failures due to billing issues and provider exhaustion.

## How It Works

When `run_with_smart_fallback()` exhausts all providers:

1. **Alert Created**: Record inserted to `crew_alerts` table
2. **Email Triggered**: HTTP POST to luci-worker `/api/alerts/send`
3. **Email Sent**: Gmail API sends formatted alert email

## Alert Types

### Billing Failure (Critical)
- Provider account exhausted (credit balance, spending limits)
- Examples: "credit balance is too low", "billing hard limit"
- **Action**: Add credits or fix billing immediately

### Fallback Exhausted (Error)
- All providers tried and failed (no account issues)
- **Action**: Check provider status, verify API keys

## Configuration

### luci-crews (Python)

```bash
# .env
LUCI_WORKER_URL=https://luci-worker.railway.app
```

### luci-worker (TypeScript)

```bash
# .env (reuses existing Gmail setup)
GMAIL_USER=notifications@leandata.com
GMAIL_CLIENT_ID=<oauth2-client-id>
GMAIL_CLIENT_SECRET=<oauth2-client-secret>
GMAIL_REFRESH_TOKEN=<refresh-token>
NOTIFICATION_EMAIL_TO=admin@leandata.com,ops@leandata.com
```

## Alert Criteria

Alerts are sent when:
- ✅ Task priority is MEDIUM or HIGH
- ✅ Billing failure OR all providers failed
- ✅ No duplicate alert in last 24 hours

Alerts are NOT sent for:
- ❌ LOW priority tasks
- ❌ Single rate limit errors (fallback succeeds)
- ❌ Duplicate alerts within 24h window

## Deduplication

One alert per `crew_type + alert_type + date`:

- First `executive_briefing` billing failure on March 4 → ✅ Alert sent
- Second `executive_briefing` billing failure on March 4 → ❌ Skipped (duplicate)
- `executive_briefing` billing failure on March 5 → ✅ New alert

## Database Schema

```sql
SELECT * FROM crew_alerts ORDER BY created_at DESC LIMIT 10;
```

Key columns:
- `alert_type`: 'billing_failure' | 'fallback_exhausted'
- `severity`: 'critical' | 'error'
- `crew_type`: Which crew failed
- `providers_tried`: Array of providers attempted
- `exhausted_providers`: Providers with billing issues
- `email_sent`: Email delivery status

## Monitoring

### Recent Alerts
```sql
SELECT alert_type, crew_type, COUNT(*)
FROM crew_alerts
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY alert_type, crew_type
ORDER BY COUNT(*) DESC;
```

### Email Delivery Rate
```sql
SELECT
  COUNT(*) FILTER (WHERE email_sent) AS sent,
  COUNT(*) FILTER (WHERE email_sent = false) AS failed
FROM crew_alerts
WHERE created_at > NOW() - INTERVAL '7 days';
```

### Provider Health
```sql
SELECT
  UNNEST(exhausted_providers) AS provider,
  COUNT(*) AS exhaustion_count
FROM crew_alerts
WHERE alert_type = 'billing_failure'
  AND created_at > NOW() - INTERVAL '7 days'
GROUP BY provider
ORDER BY exhaustion_count DESC;
```

## Troubleshooting

### Alert created but email not sent

Check luci-worker logs for email send errors:
```bash
# Railway logs
railway logs -s luci-worker | grep "Crew alert"
```

### Email not received

1. Verify `NOTIFICATION_EMAIL_TO` is set correctly
2. Check Gmail API OAuth token is valid
3. Check spam folder
4. Query `crew_alerts` table for `email_error` column

### Too many alerts

- Check deduplication is working (alert_hash present)
- Verify LOW priority tasks aren't alerting
- Consider extending dedup window if needed

## Testing

### Manual Test

1. Set invalid API key:
   ```bash
   export ANTHROPIC_API_KEY="invalid-key"
   ```

2. Trigger crew that uses Anthropic:
   ```bash
   curl -X POST http://localhost:8000/api/crew/executive-briefing \
     -H "Content-Type: application/json" \
     -d '{"userId": null}'
   ```

3. Verify alert:
   ```sql
   SELECT * FROM crew_alerts ORDER BY created_at DESC LIMIT 1;
   ```

4. Check email inbox

### Unit Tests

```bash
cd luci-crews
pytest tests/test_alert_service.py -v
```
```

**Step 2: Commit**

```bash
cd /Users/ron.feathers/GitHub/LUCI/luci-crews
git add docs/ALERTING.md
git commit -m "docs: add alerting system documentation

Covers configuration, monitoring, and troubleshooting.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 12: Final Verification

**Step 1: Run all Python tests**

Run: `cd /Users/ron.feathers/GitHub/LUCI/luci-crews && pytest tests/ -v`
Expected: All tests PASS

**Step 2: Verify TypeScript builds**

Run: `cd /Users/ron.feathers/GitHub/LUCI/luci-worker && npm run build`
Expected: Build succeeds

**Step 3: Review all changes**

Run:
```bash
cd /Users/ron.feathers/GitHub/LUCI/luci-crews
git log --oneline -10
```

Expected to see all commits from this implementation.

**Step 4: Create summary commit if needed**

If any files were missed or need cleanup, make those changes and commit.

---

## Deployment Checklist

Before deploying to production:

- [ ] Apply Supabase migration (`crew_alerts` table)
- [ ] Set `LUCI_WORKER_URL` env var in luci-crews Railway service
- [ ] Verify `GMAIL_*` and `NOTIFICATION_EMAIL_TO` env vars in luci-worker
- [ ] Deploy luci-crews with new code
- [ ] Deploy luci-worker with new code
- [ ] Test manually by forcing a billing failure
- [ ] Monitor logs for first real alert
- [ ] Verify email delivery

## Success Criteria

✅ Billing failures create alerts and send emails
✅ Deduplication prevents spam (no duplicates within 24h)
✅ Email delivery rate >95%
✅ Alert creation <5 seconds
✅ No impact on crew execution performance

---

## Notes

- Alert creation is fire-and-forget - errors logged but don't block crew
- Email delivery happens async via luci-worker
- LOW priority tasks never alert
- Deduplication uses MD5 hash of crew_type + alert_type + date
