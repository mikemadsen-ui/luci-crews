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
