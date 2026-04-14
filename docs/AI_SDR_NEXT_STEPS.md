# AI SDR — Next Steps & Backlog

Last updated: 2026-04-14

---

## Waiting on Ron

- [ ] **PR #4 review and merge** — contact lookup, placeholder safety, writer quality, model fixes
      ronfeathers-LD/luci-crews#4
- [ ] **Railway MCP IP restriction** — MCP server (mcp-hub.leandata.workers.dev) is
      blocking Railway's egress IPs. Ron needs to allowlist Railway staging IPs.
      Local runs with the staging key work fine — this is purely a network allowlist issue.
- [ ] **Outreach Sequence Enrollment permission** — Outreach > Settings > Apps > API >
      LeanData integration > enable Sequence Enrollment scope.
      Enrollment flow cannot be tested until this is fixed.
- [ ] **Anthropic API key tier on Railway** — individual plan = 30K TPM, throttles at
      3+ accounts. Need a team/higher-tier key on Railway for production batches.

---

## After PR #4 merges — staging validation

- [ ] Health check: `curl https://luci-crews-staging.up.railway.app/health`
- [ ] Confirm /api/crew/ai-sdr is registered in openapi.json routes
- [ ] Run Everi dry run against staging URL (not localhost) once MCP IP restriction is fixed
- [ ] Confirm Supabase rows appear in ai_sdr_batch_runs and ai_sdr_account_results

---

## After Outreach permission is fixed — enrollment flow test

- [ ] Run Everi with enrollmentEnabled=true, dryRun=false
- [ ] Approve human_input gate (Gate 1)
- [ ] Confirm Step 1 appears in Outreach task queue (Gate 2)
- [ ] Confirm all 6 variables populated: ai_subject_1, ai_body_1, ai_body_2,
      ai_body_3, ai_subject_4, ai_body_4

---

## ✅ Completed

- [x] ai_sdr_crew.py — built, Anthropic-only, 5-task chain, memory=False
- [x] POST /api/crew/ai-sdr endpoint registered and tested
- [x] agents.yaml — 5 SDR agents defined
- [x] tasks.yaml — 5 SDR tasks with full context chain
- [x] ai_sdr_qa_config.yaml — QA + Supabase logging config
- [x] Supabase logging wired into batch run and per-account result
- [x] Supabase tables created in luci-staging: ai_sdr_batch_runs,
      ai_sdr_account_results, ai_sdr_reply_events
- [x] Fintech validated: Everi (0.92, Dustin Dunn VP Sales Ops)
- [x] Fintech skip validated: OneStream (account_in_active_pipeline)
- [x] Insurance validated: Humana (Brenda Hutton from Salesforce, 0.92, no banned logos)
- [x] Insurance re-engagement validated: IDeaS and Aon (prior_ld_contact=true)
- [x] Salesforce contact lookup before ZoomInfo (STEP 3b)
- [x] Closed-lost opp check sets prior_ld_contact in STEP 1
- [x] Insurance logo guardrails (Goosehead, Unum, Aflac only)
- [x] Placeholder safety: null contact guard, QA flag, enroll hard skip
- [x] 75-word limit (writer + QA reviewer synced)
- [x] Step 2 curiosity rule: ONE question, no pain diagnosis
- [x] Banned: ellipses, em dashes, false urgency, proof point adjectives
- [x] Social proof placement enforced (before CTA, never after signature)
- [x] Model fallback fix: claude-sonnet-4-6 removed from FALLBACK_PROVIDERS
- [x] PR #1 merged (AI SDR v1 initial build)
- [x] PR #2 merged (Supabase logging, config enable)
- [x] PR #4 open (contact lookup, placeholder safety, writer quality, model fixes)

---

## V1.1 Backlog (post-launch fixes)

- [ ] **Researcher early-exit** — accounts like OneStream take ~2 min to skip
      instead of <30s. Need hard-stop immediately after SFDC validation fails.
      Currently the researcher completes its full loop before returning skip.
      Tracked in tasks.yaml comment.
- [ ] **contact_source field** — not surfacing in review_queue_entry output JSON.
      Currently set internally but not passed through to the QA schema.
- [ ] **draft_email subject line inconsistency** — tasks.yaml STEP 2 still says
      "4 words or fewer, lowercase" but agents.yaml says "2-5 words, sentence case".
      Fix in next pass.
- [ ] **Supabase flagged/enrolled counts in batch run row** — currently set to 0.
      Requires parsing account_results rows to compute. Low priority.

---

## Future workstreams (post-v1)

- [ ] SMB ICP file and validation
- [ ] EMEA ICP file and validation
- [ ] Reply handler (services/reply_monitor.py) — monitors mike.madsen@leandata.com,
      classifies replies, routes to human or auto-responds
- [ ] Gmail OAuth setup for reply monitoring
- [ ] Production account list (beyond test fixtures)
- [ ] Scheduled batch runs (cron or Railway scheduled job)
