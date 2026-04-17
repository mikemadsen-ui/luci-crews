# AI SDR — Next Steps & Backlog

Last updated: 2026-04-17

---

## Immediate — Staging enrollment test

- [ ] **Add Railway staging env vars** — OUTREACH_INSTALL_ID and OUTREACH_MAILBOX_ID
      not yet in Railway staging (only in local .env). Add before running staging test.
      OUTREACH_INSTALL_ID = 9fea8966-8dab-45fb-b7d0-c89ae01785b2
      OUTREACH_MAILBOX_ID = 596

- [ ] **Everi enrollment run on staging** — run against Railway staging URL with
      enrollmentEnabled=true. Local testing not feasible (30K TPM rate limit stalls writer).
      ```
      curl -X POST https://luci-crews-staging.up.railway.app/api/crew/ai-sdr \
        -H "Content-Type: application/json" \
        -d '{
          "accounts": [
            {"account_name": "Everi Holdings Inc.",
             "salesforce_id": "0015A00001xvRmBQAU"}
          ],
          "vertical": "fintech",
          "dryRun": false,
          "enrollmentEnabled": true
        }'
      ```
      Expected: enrolled=true, sequence_state_id present, Step 1 appears in Outreach task queue.

- [ ] **Confirm Supabase rows** appear in ai_sdr_batch_runs and ai_sdr_account_results
      after the staging run.

- [ ] **Check Outreach task queue** for Step 1 manual task after enrollment.
      Note: Step 1 will show ai_subject_1 template variable unresolved — this is expected.
      The subject/body content is in review_queue_entry.sequence_steps[0].
      Variable population fix is v1.1 backlog.

---

## Waiting on Ron

- [ ] **Anthropic API key tier on Railway** — individual plan = 30K TPM, stalls at
      writer step (41K tokens). Need a team/higher-tier key on Railway for production batches.
- [ ] **Add Railway env vars** — OUTREACH_INSTALL_ID and OUTREACH_MAILBOX_ID not yet
      in Railway staging (only in local .env). Add before running staging enrollment test.

---

## ✅ S2S enrollment confirmed working locally (direct API test)

- [x] INSTALL_ID: 9fea8966-8dab-45fb-b7d0-c89ae01785b2 (added to .env)
- [x] MAILBOX_ID: 596 (mike.madsen@leandata.com, Gmail connected)
- [x] sequenceState 747809 created: prospect 804416, sequence 5724
- [x] Step 1 confirmed in Outreach task queue as manual task

## ✅ Full enrollment flow wired (pending Railway validation)

- [x] outreach_enroll_prospect_s2s updated: accepts prospect_email, looks up Outreach
      prospect ID by email automatically
- [x] Enrollment agent given outreach_enroll_prospect_s2s as tool
- [x] tasks.yaml: enrollment task calls outreach_enroll_prospect_s2s (not broken MCP proxy)
- [x] human_review_gate: enabled: false in ai_sdr_qa_config.yaml
- [x] human_input=False on enroll_prospect task (EOFError fix)

---

## After staging enrollment confirmed

- [ ] **Referenceable proof points filter** — NVIDIA and Peek appeared as fintech proof
      points but are not approved logos. Fix STEP 3c to filter referenceable_proof_points
      against approved logos list from ICP file (Stripe, Ramp, Brex, PayPal, Plaid).
      Only return customers that appear in the vertical ICP approved list.

- [ ] **Full crew enrollment test** — after env vars added to Railway staging:
      - Approve human_input gate if re-enabled (Gate 1)
      - Confirm Step 1 appears in Outreach task queue (Gate 2)
      - Confirm all 6 variables populated: ai_subject_1, ai_body_1, ai_body_2,
        ai_body_3, ai_subject_4, ai_body_4 (NOTE: variable population is v1.1 backlog —
        enrollment creates the sequenceState; content is in review_queue_entry)

---

## SMB validation (ICP file done — needs test accounts)

- [ ] Run 2-3 SMB test accounts against staging to validate icp_smb.md
      Suggested test accounts: find a comparable SMB prospect in SFDC for validation.
- [ ] Confirm SMB title matching works (Founder/CEO path for sub-100 employee accounts)
- [ ] Confirm referenceable_proof_points returns SMB-vertical customers

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
- [x] PR #4 merged (contact lookup, placeholder safety, writer quality, model fixes) ✅
- [x] Railway staging MCP connectivity confirmed (Ron tested — 68 seconds) ✅
- [x] OUTREACH_PRIVATE_KEY + OUTREACH_S2S_APP_UID in Railway staging ✅
- [x] LD taxonomy fields created (LD_Super_Industry__c, LD_Industry__c, LD_Sub_Industry__c)
- [x] 40,170 accounts classified in Salesforce taxonomy ✅
- [x] STEP 3c — referenceable customer lookup added to tasks.yaml ✅
- [x] SMB ICP file built: knowledge/messaging/icp_smb.md ✅
- [x] SMB title matching updated in STEP 3b (GTM, RevOps, Founder/CEO) ✅
- [x] Referenceable proof points rule added to draft_email FORMATTING HARD RULES ✅
- [x] {"raw": ...} wrapper fix: 5-attempt JSON extraction in _result_to_clean_dict ✅
- [x] Outreach S2S JWT auth: outreach_enroll_prospect_s2s() wired in mcp_client.py ✅
- [x] S2S enrollment confirmed working (sequenceState 747809, prospect 804416, seq 5724) ✅
- [x] outreach_enroll_prospect_s2s: accepts prospect_email, looks up Outreach ID ✅
- [x] Enrollment agent: outreach_enroll_prospect_s2s added as tool ✅
- [x] tasks.yaml: enrollment task updated to call outreach_enroll_prospect_s2s ✅
- [x] human_review_gate: enabled: false (ready for live enrollment test) ✅

---

## V1.1 Backlog (post-launch fixes)

- [ ] **Sequence variable population** — ai_subject_1/ai_body_1 etc. not injected into
      Outreach template at enrollment time. The sequenceState is created but the template
      variables remain as placeholders. Need to PATCH prospect custom attributes in Outreach
      after enrollment, or set mailMessage content per step.
- [ ] **Referenceable proof points filter** — NVIDIA and Peek appeared as unapproved
      fintech proof points. Filter against approved logos list in ICP file.
- [ ] **Researcher early-exit** — accounts like OneStream take ~2 min to skip
      instead of <30s. Need hard-stop immediately after SFDC validation fails.
      Currently the researcher completes its full loop before returning skip.
      Tracked in tasks.yaml comment.
- [ ] **contact_source field** — not surfacing in review_queue_entry output JSON.
      Currently set internally but not passed through to the QA schema.
- [ ] **Supabase flagged/enrolled counts in batch run row** — currently set to 0.
      Requires parsing account_results rows to compute. Low priority.

---

## Future workstreams (post-v1)

- [ ] EMEA ICP file and validation (Outreach sequence ID: 5734)
- [ ] Reply handler (services/reply_monitor.py) — monitors mike.madsen@leandata.com,
      classifies replies, routes to human or auto-responds
- [ ] Gmail OAuth setup for reply monitoring
- [ ] Production account list (beyond test fixtures)
- [ ] Scheduled batch runs (cron or Railway scheduled job)
