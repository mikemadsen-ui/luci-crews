# AI SDR — Next Steps & Backlog

Last updated: 2026-04-16

---

## Immediate — Run staging validation

- [ ] **Everi dry run on staging** — confirm full pipeline works end-to-end on Railway
      ```
      curl -X POST https://luci-crews-staging.up.railway.app/api/crew/ai-sdr \
        -H "Content-Type: application/json" \
        -d '{
          "accounts": [
            {"account_name": "Everi Holdings Inc.",
             "salesforce_id": "0015A00001xvRmBQAU"}
          ],
          "vertical": "fintech",
          "dryRun": true,
          "enrollmentEnabled": false
        }'
      ```
      Expected: Dustin Dunn VP Sales Ops, signal_type = enum string,
      referenceable_proof_points populated, zero em dashes, social proof before CTA.

- [ ] **Confirm Supabase rows** appear in ai_sdr_batch_runs and ai_sdr_account_results
      after the staging run.

---

## Waiting on Ron

- [ ] **Outreach Sequence Enrollment scope** — Outreach > Settings > Apps > API >
      LeanData integration > enable Sequence Enrollment scope.
      S2S fallback (outreach_enroll_prospect_s2s) is wired but not yet tested.
- [ ] **Anthropic API key tier on Railway** — individual plan = 30K TPM, throttles at
      3+ accounts. Need a team/higher-tier key on Railway for production batches.

---

## After Outreach scope is enabled — enrollment flow test

- [ ] Test S2S enrollment:
      prospect_id: 804416 (Mike Madsen test record)
      sequence_id: 5724 (Fintech AI SDR sequence)
      Call outreach_enroll_prospect_s2s('804416', '5724')
- [ ] Run Everi with enrollmentEnabled=true, dryRun=false
- [ ] Approve human_input gate (Gate 1)
- [ ] Confirm Step 1 appears in Outreach task queue (Gate 2)
- [ ] Confirm all 6 variables populated: ai_subject_1, ai_body_1, ai_body_2,
      ai_body_3, ai_subject_4, ai_body_4

---

## SMB validation (ICP file done — needs test accounts)

- [ ] Run 2-3 SMB test accounts against staging to validate icp_smb.md
      Suggested test accounts: Spekit, Qualio (already in SFDC as customers — skip)
      Find a comparable SMB prospect in SFDC for validation.
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
      (SOQL by LD_Industry__c, fallback to LD_Super_Industry__c, top 3 by seniority)
- [x] SMB ICP file built: knowledge/messaging/icp_smb.md ✅
      (10+ reference customers, pain themes, title matching, signal priorities)
- [x] SMB title matching updated in STEP 3b (GTM, RevOps, Founder/CEO) ✅
- [x] Referenceable proof points rule added to draft_email FORMATTING HARD RULES ✅
- [x] {"raw": ...} wrapper fix: 5-attempt JSON extraction in _result_to_clean_dict ✅
- [x] Outreach S2S JWT auth: outreach_enroll_prospect_s2s() wired in mcp_client.py ✅

---

## V1.1 Backlog (post-launch fixes)

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
