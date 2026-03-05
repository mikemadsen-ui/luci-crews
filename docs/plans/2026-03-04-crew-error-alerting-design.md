# Crew Error Alerting System - Design Document

**Date:** 2026-03-04
**Author:** Claude
**Status:** Approved

## Problem Statement

Crew failures due to provider billing issues and complete fallback exhaustion currently go undetected until manually discovered in logs. The recent Anthropic credit exhaustion that failed the executive briefing crew demonstrates the need for proactive alerting.

**Example error:**
```
2026-03-04 20:23:03,565 – src.luci_crews.main – ERROR – Executive briefing crew failed:
litellm.BadRequestError: AnthropicException - {"type":"error","error":{"type":"invalid_request_error",
"message":"Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing
to upgrade or purchase credits."},"request_id":"req_011CYifUKtxdFszVQSGGj8qH"}
```

## Requirements

Based on user requirements:

1. **Alert Channels:**
   - Email notifications to admin list
   - Supabase table for admin UI visibility

2. **Alert Criteria:**
   - Billing/credit failures (account-level provider issues)
   - Complete fallback exhaustion (all providers failed)
   - Only alert for MEDIUM and HIGH priority tasks

3. **Alert Recipients:**
   - Admin email list (configured via env var)
   - Not individual users (even for user-triggered crews)

4. **Context Captured:**
   - Who/what triggered the failure
   - Which providers were tried
   - Full error message and context

## Design Overview

**Approach: Centralized Alert Service in luci-crews**

The alert service hooks into the existing `run_with_smart_fallback()` function to detect critical failures, then:
1. Insert alert record to Supabase `crew_alerts` table
2. Call luci-worker HTTP endpoint to send email via existing Gmail infrastructure

This approach works for all crew callers:
- Scheduled pipelines (luci-worker)
- User-triggered API calls (Next.js luci app)
- Direct CrewAI service calls

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     luci-crews (Python)                      │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  run_with_smart_fallback()                             │ │
│  │  - Try providers in fallback chain                     │ │
│  │  - Detect billing failures & exhaustion                │ │
│  │  - On critical failure → call alert_service            │ │
│  └──────────────────────┬─────────────────────────────────┘ │
│                         │                                    │
│  ┌──────────────────────▼─────────────────────────────────┐ │
│  │  alert_service.py                                      │ │
│  │  - should_alert() - deduplication check                │ │
│  │  - create_alert() - insert to crew_alerts table        │ │
│  │  - trigger_email() - POST to luci-worker endpoint      │ │
│  └──────────────────────┬─────────────────────────────────┘ │
│                         │                                    │
└─────────────────────────┼────────────────────────────────────┘
                          │
                          │ HTTP POST /api/alerts/send
                          │
┌─────────────────────────▼────────────────────────────────────┐
│                   luci-worker (TypeScript)                    │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  POST /api/alerts/send                                  │ │
│  │  - Fetch alert from Supabase by ID                      │ │
│  │  - Call notification-service.sendCrewAlert()            │ │
│  └──────────────────────┬──────────────────────────────────┘ │
│                         │                                     │
│  ┌──────────────────────▼──────────────────────────────────┐ │
│  │  notification-service.ts                                │ │
│  │  - Format alert email HTML                              │ │
│  │  - Send via existing Gmail API (email-sender.ts)        │ │
│  │  - Update crew_alerts.email_sent = true                 │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

## Database Schema

### New Table: `crew_alerts`

```sql
CREATE TABLE crew_alerts (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  -- Alert classification
  alert_type TEXT NOT NULL,     -- 'billing_failure' | 'fallback_exhausted'
  severity TEXT NOT NULL,       -- 'critical' | 'error'

  -- Context
  crew_type TEXT NOT NULL,      -- 'executive_briefing', 'call_analysis', etc.
  task_name TEXT,               -- Optional task identifier
  task_priority TEXT NOT NULL,  -- 'LOW' | 'MEDIUM' | 'HIGH'
  user_id UUID,                 -- NULL for scheduled jobs

  -- Failure details
  providers_tried TEXT[] NOT NULL,    -- ['openai/gpt-4.1', 'anthropic/claude-sonnet-4-6']
  exhausted_providers TEXT[],         -- Providers with billing issues
  error_message TEXT NOT NULL,        -- Last error message
  full_error TEXT,                    -- Complete stack trace (optional)

  -- Email tracking
  email_sent BOOLEAN DEFAULT FALSE,
  email_sent_at TIMESTAMPTZ,
  email_error TEXT,

  -- Deduplication
  alert_hash TEXT,  -- Hash of (crew_type, alert_type, date) for dedup

  CONSTRAINT crew_alerts_alert_type_check
    CHECK (alert_type IN ('billing_failure', 'fallback_exhausted')),
  CONSTRAINT crew_alerts_severity_check
    CHECK (severity IN ('critical', 'error')),
  CONSTRAINT crew_alerts_task_priority_check
    CHECK (task_priority IN ('LOW', 'MEDIUM', 'HIGH'))
);

-- Indexes
CREATE INDEX idx_crew_alerts_created ON crew_alerts(created_at DESC);
CREATE INDEX idx_crew_alerts_type ON crew_alerts(alert_type, created_at DESC);
CREATE INDEX idx_crew_alerts_hash ON crew_alerts(alert_hash);
CREATE INDEX idx_crew_alerts_email_sent ON crew_alerts(email_sent, created_at DESC);
```

### Deduplication Strategy

**Hash formula:** `md5(crew_type + alert_type + date)`

**Logic:**
- Before creating an alert, check if same hash exists in last 24 hours
- If exists, skip alert creation (prevents spam)
- This allows one alert per crew+type per day

**Example:**
- First `executive_briefing` billing failure on 2026-03-04 → sends alert
- Second `executive_briefing` billing failure on 2026-03-04 → skipped
- `executive_briefing` billing failure on 2026-03-05 → new alert

## Alert Criteria

### When to Alert

Alerts trigger when **all** of these conditions are met:

1. **Critical failure type:**
   - **Billing failure**: Account exhausted (credit balance, spending limits)
   - **Fallback exhausted**: All providers in fallback chain failed

2. **Task priority threshold:**
   - Only alert for `MEDIUM` and `HIGH` priority tasks
   - `LOW` priority tasks (embeddings, batch jobs) fail silently

3. **Deduplication check passed:**
   - No identical alert in last 24 hours

### What Won't Trigger Alerts

- Single rate limit errors (auto-fallback succeeds)
- Low-priority task failures
- Successful retries (if any provider in fallback chain worked)
- Transient network errors that resolve on retry

### Error Classification

**Billing failures** (account-level, blocks ALL models from provider):
- Pattern matches: `credit balance is too low`, `billing hard limit`, `account.*suspended`
- Severity: `critical`
- Action required: Add credits or fix billing immediately

**Fallback exhausted** (all providers tried and failed):
- After trying all models in fallback chain (default: 6 attempts)
- Severity: `error`
- Action required: Check provider status, verify API keys

## Implementation Details

### 1. Python Alert Service

**File:** `luci-crews/src/luci_crews/alert_service.py`

```python
import os
import hashlib
import requests
from datetime import datetime, timedelta
from typing import Optional, List
from supabase import Client
import logging

logger = logging.getLogger(__name__)

def should_alert(
    alert_type: str,
    crew_type: str,
    task_priority: str,
    supabase: Client
) -> bool:
    """
    Check if we should send an alert (deduplication).

    Returns False if:
    - Task priority is LOW
    - Same alert already exists in last 24 hours
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


def create_alert(
    alert_type: str,
    crew_type: str,
    task_name: Optional[str],
    task_priority: str,
    user_id: Optional[str],
    providers_tried: List[str],
    exhausted_providers: List[str],
    error_message: str,
    supabase: Client
) -> Optional[str]:
    """
    Create an alert record and return alert ID.

    Returns None if alert should be skipped (dedup check failed).
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


def trigger_email(alert_id: str) -> None:
    """
    Trigger email send via luci-worker endpoint.

    Fire-and-forget: errors are logged but don't propagate.
    Alert is still saved to database even if email fails.
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

### 2. Integration with Fallback Logic

**File:** `luci-crews/src/luci_crews/ai_settings_helper.py`

**Modify `run_with_smart_fallback()`** at the end (after all providers fail):

```python
# Existing code...
# All providers failed
from .alert_service import create_alert, trigger_email

# Determine alert type
if exhausted_providers:
    alert_type = "billing_failure"
else:
    alert_type = "fallback_exhausted"

# Create alert
supabase = get_supabase_client()
if supabase:
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

# Raise original error
raise RuntimeError(
    f"All AI providers failed for {task_name or 'crew'}. "
    f"Tried: {', '.join(providers_tried)}. "
    f"Exhausted providers: {', '.join(exhausted_providers) or 'none'}. "
    f"Last error: {str(last_error)[:200]}"
)
```

### 3. TypeScript Email Service

**File:** `luci-worker/src/server.ts`

Add endpoint:

```typescript
app.post('/api/alerts/send', async (req, res) => {
  const { alert_id } = req.body;

  if (!alert_id) {
    return res.status(400).json({ error: 'alert_id required' });
  }

  const { sendCrewAlert } = await import('./lib/notification-service');
  const sent = await sendCrewAlert(supabase, logger, alert_id);

  res.json({ sent });
});
```

**File:** `luci-worker/src/lib/notification-service.ts`

Add function:

```typescript
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

  const sent = await sendEmail(subject, html);

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

## Configuration

### Environment Variables

**luci-crews** (Python):
```bash
LUCI_WORKER_URL=https://luci-worker.railway.app  # or http://localhost:8080 for dev
```

**luci-worker** (TypeScript):
Reuses existing Gmail configuration:
```bash
GMAIL_USER=notifications@leandata.com
GMAIL_CLIENT_ID=<oauth2-client-id>
GMAIL_CLIENT_SECRET=<oauth2-client-secret>
GMAIL_REFRESH_TOKEN=<refresh-token>
NOTIFICATION_EMAIL_TO=admin@leandata.com,ops@leandata.com
```

## Testing Strategy

### Unit Tests

1. **Deduplication logic** (`alert_service.should_alert()`):
   - Same alert within 24h → skipped
   - Different day → allowed
   - Different crew_type → allowed

2. **Priority filtering**:
   - LOW priority → never alerts
   - MEDIUM/HIGH → creates alert

3. **Alert type classification**:
   - Credit exhaustion error → billing_failure
   - All providers failed (no exhaustion) → fallback_exhausted

### Integration Tests

1. **End-to-end alert flow**:
   - Trigger a billing failure (mock Anthropic API)
   - Verify alert created in Supabase
   - Verify email endpoint called
   - Verify email sent flag updated

2. **Email formatting**:
   - Render sample alert emails
   - Verify HTML renders correctly
   - Test with different alert types

### Manual Testing

1. Force a billing failure:
   - Set invalid ANTHROPIC_API_KEY
   - Trigger executive briefing crew
   - Verify alert email received

2. Test deduplication:
   - Trigger same failure twice quickly
   - Verify only one email sent

## Monitoring & Observability

### Metrics to Track

1. **Alert volume**:
   ```sql
   SELECT alert_type, COUNT(*)
   FROM crew_alerts
   WHERE created_at > NOW() - INTERVAL '7 days'
   GROUP BY alert_type;
   ```

2. **Email delivery success rate**:
   ```sql
   SELECT
     COUNT(*) FILTER (WHERE email_sent) AS sent,
     COUNT(*) FILTER (WHERE email_sent = false) AS failed,
     COUNT(*) FILTER (WHERE email_error IS NOT NULL) AS errored
   FROM crew_alerts
   WHERE created_at > NOW() - INTERVAL '7 days';
   ```

3. **Provider health**:
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

### Logs

Alert-related log messages:
- `Created alert {alert_id}: {crew_type} / {alert_type}` - Alert created
- `Skipping duplicate alert: {crew_type} / {alert_type}` - Dedup triggered
- `Crew alert email sent: {crew_type}` - Email successfully sent
- `Failed to trigger alert email: {error}` - Email send failed

## Future Enhancements

1. **Admin UI Dashboard**:
   - View recent alerts in admin panel
   - Acknowledge/resolve alerts
   - View alert trends over time

2. **Slack Integration**:
   - Send alerts to Slack channel
   - Interactive buttons to check provider status

3. **Smart Throttling**:
   - If same crew fails repeatedly, increase dedup window
   - "Alert storm" detection (>10 alerts in 1 hour)

4. **Provider Status Integration**:
   - Check status.openai.com, status.anthropic.com
   - Include status in alert email
   - Don't alert if provider has known outage

5. **Automatic Remediation**:
   - Auto-switch billing account if balance low
   - Rotate API keys if quota exceeded
   - Scale up quotas via provider APIs

## Rollout Plan

### Phase 1: Core Implementation (Week 1)
- Create `crew_alerts` table migration
- Implement `alert_service.py`
- Integrate with `run_with_smart_fallback()`
- Add luci-worker email endpoint
- Deploy to staging

### Phase 2: Testing (Week 1-2)
- Manual testing with forced failures
- Verify deduplication works
- Test email delivery
- Load test (simulate multiple failures)

### Phase 3: Production Deploy (Week 2)
- Deploy to production
- Monitor for first few days
- Verify no alert spam
- Confirm emails received

### Phase 4: Admin UI (Week 3)
- Add alerts page to admin panel
- Show recent alerts
- Add acknowledge/resolve actions

## Success Criteria

1. **Alerting works**: Billing failures send email within 1 minute
2. **No spam**: Deduplication prevents duplicate alerts
3. **Reliable delivery**: >95% email delivery success rate
4. **Low latency**: Alert created and email triggered in <5 seconds
5. **Zero impact**: Alert logic doesn't slow down crew execution

## Dependencies

- Supabase client in luci-crews (already exists)
- Gmail API email sender in luci-worker (already exists)
- HTTP requests library in Python (`requests` - add to pyproject.toml)

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Email delivery fails | Alert still saved to DB, visible in admin UI |
| luci-worker endpoint unavailable | Fire-and-forget design, error logged but doesn't block |
| Alert spam if many crews fail | Deduplication per crew+type+day, alert storm detection in future |
| Performance impact on crew execution | Alert creation is async (fire-and-forget), minimal overhead |

## Appendix

### Example Alert Email

```
Subject: 🚨 Luci Crew Alert: executive_briefing - billing_failure

[HTML email body showing]:
- Crew: executive_briefing
- Alert Type: billing_failure
- Severity: critical
- Priority: MEDIUM
- Time: 2026-03-04 20:23:03

Failure Details:
- Providers Tried: anthropic/claude-sonnet-4-6, openai/gpt-4.1, google/gemini-2.5-flash
- Exhausted: anthropic

Error: Your credit balance is too low to access the Anthropic API...

⚠️ Provider account exhausted - add credits or check billing settings
```
