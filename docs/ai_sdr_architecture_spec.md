# AI SDR Crew — Architecture Spec
# Hand this to Claude Code alongside the build brief.
# Covers the pieces not defined in the build brief:
# batch loop pattern, Gmail monitoring, dry_run wiring,
# QA config integration, and Supabase logging hooks.

---

## 1. Batch Loop Pattern — use this exact pattern in crew.py

Do NOT use crew.kickoff_for_each() for v1.
Use a sequential external loop — one account at a time.
This allows per-account error handling without killing the whole batch.

```python
# In ai_sdr_crew.py or the API route handler

results = []
skipped = []

for account in accounts:
    try:
        result = crew.kickoff(inputs={
            "account_name": account["account_name"],
            "salesforce_id": account["salesforce_id"],
            "vertical": vertical,
            "enrollment_enabled": enrollment_enabled,
            "dry_run": dry_run,
            "reply_inbox": reply_inbox,
            "sequence_id": SEQUENCE_IDS.get(vertical),
            "qa_config": load_qa_config()  # loads ai_sdr_qa_config.yaml
        })
        results.append(result)
    except Exception as e:
        skipped.append({
            "account_name": account["account_name"],
            "salesforce_id": account["salesforce_id"],
            "skip_reason": f"crew_error: {str(e)}",
            "skipped_at": datetime.utcnow().isoformat()
        })
        continue

return {
    "results": results,
    "skipped": skipped,
    "total_accounts": len(accounts),
    "processed": len(results),
    "skipped_count": len(skipped)
}
```

---

## 2. Sequence ID mapping — define as constants in crew.py

```python
SEQUENCE_IDS = {
    "fintech": "5724",      # FY26 Q2 - AI SDR Pilot (FinTech)
    "insurance": None,       # TBD — do not enroll until sequence is created
    "smb": None,             # TBD
    "emea": None             # TBD
}
```

---

## 3. QA Config integration — load at crew startup

```python
def load_qa_config():
    config_path = os.path.join(
        os.path.dirname(__file__),
        "../config/ai_sdr_qa_config.yaml"
    )
    with open(config_path, "r") as f:
        return yaml.safe_load(f)
```

---

## 4. dry_run wiring — must flow through every agent

Enrollment agent: if dry_run or not enrollment_enabled → write to review_queue only
Reply handler: if dry_run → classify and log, do NOT send any response
Writer agent: dry_run does not affect writer output

---

## 5. Gmail monitoring — separate process from batch job

Reply handler runs as a SEPARATE background process.
Batch job: triggered manually or via API, processes account list, terminates.
Reply handler: long-running background service, polls Gmail every 5 minutes.

File: src/luci_crews/services/reply_monitor.py
For v1 testing: run manually with dry_run=True, log output to console.
Do not deploy as background service until batch job is validated.

---

## 6. Crew.py structure

```python
ai_sdr_crew = Crew(
    agents=[...],
    tasks=[...],
    process=Process.sequential,
    memory=True,
    verbose=True,       # flip to False for production
    max_rpm=10,         # rate limit MCP calls — important for ZoomInfo credits
)

reply_handler_crew = Crew(
    agents=[sdr_reply_handler],
    tasks=[handle_reply_task],
    process=Process.sequential,
    memory=False,       # stateless — each reply is independent
    verbose=True,
)
```

---

## 7. tasks.yaml context fields

Each task reads output from previous tasks via the context field:
- gather_signals reads from research_prospect
- draft_email reads from research_prospect + gather_signals
- review_and_score reads from all three previous tasks

---

## 8. API endpoint — POST /api/crew/ai-sdr

Validate vertical has sequence configured before running.
Load QA config at request time.
Return run_id, results, skipped, counts.
Default: enrollment_enabled=false, dry_run=true.

---

## 9. V1 test fixture

File: tests/fixtures/sdr_dry_run_fintech.json
Use 3 accounts:
- 1 that should pass all checks
- 1 that should be skipped (existing customer or in pipeline)
- 1 with partial data (test graceful degradation)

Success criteria:
- Valid JSON with results array
- At least 1 record with target_contact populated
- At least 1 draft_email with subject and body
- Skipped accounts have skip_reason
- No outreach_add_prospect_to_sequence calls in logs
- Runtime under 3 minutes for 3 accounts
