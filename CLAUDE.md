# luci-crews — Claude Code Context

## What this repo is
Production CrewAI backend (FastAPI) powering LeanData's AI agent workflows.
Deployed on Railway. TypeScript frontend (leandata/LUCI) calls REST endpoints.
Results saved to Supabase. Currently working on: AI SDR crew on branch feature/ai-sdr.

## Repo structure
src/luci_crews/
├── crews/              ← one .py file per crew (e.g. ai_sdr_crew.py)
├── config/
│   ├── agents.yaml     ← all agent definitions (NO tool refs here)
│   └── tasks.yaml      ← task definitions (tools wired here)
├── api/                ← FastAPI route handlers
└── main.py             ← app entrypoint

knowledge/
└── messaging/
    ├── icp_fintech.md            ← fintech ICP, buying committee, pain themes, email framework
    ├── icp_insurance.md          ← insurance ICP, buying committee, pain themes, email framework
    └── messaging_library_template.md  ← marketing fills this in (TBD)

## How crews are invoked
- Railway runs the FastAPI service
- TypeScript calls: POST /api/crew/ai-sdr with JSON body
- Results returned as structured JSON saved to Supabase
- New crew needs: crew .py file + agents.yaml entries + tasks.yaml entries + API endpoint

## YAML conventions — follow these exactly
- agents.yaml: role, goal, backstory, verbose: false, allow_delegation: false
- NO tool references in agents.yaml — tools belong in tasks.yaml or crew .py
- Section headers: # === CREW NAME === with blank lines before/after
- Snake_case agent names (e.g. sdr_prospect_researcher, not SDRResearcher)
- goal: single line with > block scalar
- backstory: multi-paragraph > block scalar, use bullet points for frameworks

## MCP available (leandata-salesforce aggregator)
- salesforce_query, salesforce_get_record, salesforce_search
- zoominfo_search_companies, zoominfo_enrich_company (credits — confirm account first)
- zoominfo_search_contacts (find ICP contacts — does NOT consume credits)
- luci_search_portfolio, luci_search_account, luci_list_accounts (UUID IDs only)
- avoma_search_meetings, avoma_get_meeting_notes
- outreach_list_sequences, outreach_get_sequence (READ)
- outreach_add_prospect_to_sequence (WRITE — gated by enrollment_enabled flag)
- Gmail API for monitoring replies (inbox: mike.madsen@leandata.com for testing)

---

## AI SDR — Full Workflow

### What this crew does
Batch job that runs against a defined list of prospect accounts across 4 scenarios.
For each account: finds the right contact, researches them, crafts a personalized
outbound email, enrolls them in the scenario's Outreach sequence, populates each
sequence email step with unique content per contact, monitors Gmail for replies,
and generates a response action based on reply type.

### Batch job input schema
{
  "accounts": [{ "account_name": "string", "salesforce_id": "string" }],
  "vertical": "fintech | insurance | smb | emea",
  "enrollment_enabled": false,
  "reply_inbox": "mike.madsen@leandata.com"
}

### The 4 scenarios

Scenario 1 — Fintech
- ICP file: knowledge/messaging/icp_fintech.md
- Outreach sequence ID: 5724 ("FY26 Q2 - AI SDR Pilot (FinTech)")
- Target titles: VP/Director/Sr Director Revenue Operations, Head GTM Operations
- Seniority floor: Director+
- Reference logos: Stripe, Ramp, Brex, PayPal

Scenario 2 — Insurance
- ICP file: knowledge/messaging/icp_insurance.md
- Outreach sequence ID: 5732 ("FY26 Q2 - AI SDR Pilot (Insurance)")
- Target titles: VP/Director Revenue Operations, Head Salesforce Solutions
- Seniority floor: Senior Manager+
- Reference logos: Goosehead Insurance (SDR-sourced $273K ARR), Unum Group

Scenario 3 — SMB
- ICP file: TBD
- Outreach sequence ID: 5733 ("FY26 Q2 - AI SDR Pilot (SMB)")
- Build after fintech and insurance complete

Scenario 4 — EMEA (English-speaking, ex-UKI)
- ICP file: TBD
- Outreach sequence ID: 5734 ("FY26 Q2 - AI SDR Pilot (EMEA)")
- Build after fintech and insurance complete

---

## Agent workflow (runs per contact, per scenario)

### Step 1: Research (sdr_prospect_researcher)
1. salesforce_query: confirm account is a prospect
   - No existing LeanData customer relationship
   - No active open opportunity (IsClosed = false)
   - If either check fails: skip account, log reason
2. zoominfo_enrich_company: firmographic enrichment
3. zoominfo_search_contacts: find target contact using ICP title params for vertical
4. luci_search_portfolio: surface pain signals (match_threshold 0.35)
5. avoma_search_meetings: check for past meetings (last 180 days)

### Step 2: Signal reading (sdr_signal_reader)
- Compile research into max 3 signals per contact as list of strings
- If no signals: use ICP-level personalization hooks from vertical's ICP file

### Step 3: Draft (sdr_email_writer)
- Load ICP file for vertical
- Draft initial outbound email: 3 sentences max in body
- Generate unique personalized content for EACH step in the scenario's sequence
  (every sequence step gets its own version — not the same message repeated)

### Step 4: QA and score (sdr_qa_reviewer)
- Score confidence 0.0 to 1.0:
  0.9+    ICP title exact match + 2 or more signals used
  0.7-0.89  Title approximate match + 1 signal or ICP hook
  0.5-0.69  Contact found, weak title match, no signals
  below 0.5  Auto-flag, do not enroll
- Flag record if: confidence below 0.5, no email found, title mismatch, generic body

### Step 5: Enroll (sdr_enrollment_agent)
- If enrollment_enabled = true AND flagged = false:
  Call outreach_add_prospect_to_sequence with scenario sequence ID
  Populate ALL 6 variables upfront at enrollment time:
    ai_subject_1, ai_body_1, ai_body_2, ai_body_3, ai_subject_4, ai_body_4
- If enrollment_enabled = false:
  Write full record to review_queue.json for human review

SEQUENCE STEP STRUCTURE (all 4 sequences):
- Step 1: MANUAL — appears in Outreach task queue for human review before sending
- Step 2: Automated — fires on Day 4 after Step 1 is manually sent
- Step 3: Automated — fires on Day 10
- Step 4: Automated — fires on Day 18 (new thread, breakup email)

V1 QA GATES — two gates before a prospect receives Step 1:
1. human_input: true on enroll_prospect task — crew pauses for human approval
   before calling outreach_add_prospect_to_sequence
2. Step 1 manual task in Outreach — contact sits in task queue; human reviews
   and sends. Steps 2-4 fire automatically only after Step 1 is sent.

### Step 6: Monitor and respond (sdr_reply_handler)
Monitor reply_inbox continuously. On reply, classify and act:
NOTE: Do not monitor for replies until Step 1 has been manually sent.
Reply monitoring for Steps 2, 3, 4 is standard once Step 1 is sent.

MEETING REQUEST (prospect asks for meeting, demo, call):
- Reply with account owner's BookIt/calendar link
- Do not negotiate timing — just send the link
- Log: "meeting_requested"

REJECTION (not interested, wrong person, unsubscribe):
- Hard rejection or unsubscribe: do NOT reply, remove from sequence immediately
- Soft rejection: generate 1-2 sentence value-based response (non-pushy)
- Log: "rejected" or "unsubscribed"

QUESTIONS (prospect asks something substantive):
- Classify: can this be answered with value messaging?
- If yes (what does LeanData do, customer examples, general pricing range):
  Reply with value-based messaging, CC account owner
  Log: "replied_value"
- If needs human (technical details, security/legal, pricing negotiation):
  Draft reply but route to human for review before sending
  Notify account owner
  Log: "routed_to_human"

NO REPLY / BOUNCE:
- Sequence continues on its own cadence via Outreach
- Log: "no_reply" or "bounced"

---

## Output schemas

Enrollment output (per contact):
{
  "account_name": "string",
  "salesforce_id": "string",
  "vertical": "string",
  "target_contact": {
    "name": "string",
    "title": "string",
    "email": "string",
    "linkedin": "string or null"
  },
  "sequence_id": "string",
  "sequence_steps": [
    { "step_number": 1, "subject": "string", "body": "string" }
  ],
  "enrolled": true,
  "confidence": 0.0,
  "signals_used": ["string"],
  "flagged": false,
  "flag_reason": null
}

Reply handling output (per reply):
{
  "contact_email": "string",
  "account_name": "string",
  "reply_received_at": "ISO timestamp",
  "reply_classification": "meeting_request | rejection | question | unsubscribe",
  "action_taken": "sent_booking_link | sent_value_response | routed_to_human | removed_from_sequence",
  "response_sent": "string or null",
  "routed_to": "string or null",
  "logged_at": "ISO timestamp"
}

---

## Constraints — never violate

- NEVER enroll if enrollment_enabled = false — write to review_queue only
- NEVER enroll a contact from an existing LeanData customer account
- NEVER enroll a contact from an account with any open opportunity (IsClosed = false)
- NEVER reply to a hard rejection or unsubscribe — remove from sequence and stop
- NEVER send a reply requiring human judgment without routing to human first
- NEVER call zoominfo_enrich_company before salesforce_query confirms prospect status
- ZoomInfo managementLevel = full strings only ("Vice President" not "VP")
- LUCI requires UUID account IDs — not Salesforce 18-char IDs
- LUCI match_threshold: use 0.35 (0.5 returns nothing for most signal queries)
- All test emails route through mike.madsen@leandata.com (update when alias is ready)

---

## Known MCP gotchas
- Salesforce JSON: double-parse — outer list → text key → inner JSON → records
- LUCI UUIDs ≠ Salesforce 18-char IDs — always resolve via luci_list_accounts
- ZoomInfo enrich consumes credits; search does not — search first, enrich only if needed
- Outreach enrollment gated by enrollment_enabled flag (S2S bug open with support)
- Snowflake: use PENDO.ACCOUNT_HISTORY not GAINSIGHT_CUSTOMER_SUCCESS tables

---

## Build status (feature/ai-sdr branch)

Last updated: 2026-04-14

PRs:
- PR #1 (initial AI SDR build): MERGED into ronfeathers-LD/luci-crews:main
- PR #2 (ronfeathers-LD/luci-crews#4 — contact lookup, placeholder safety, writer quality,
  model fixes): PENDING Ron review. Reviewer tagged @ronfeathers-LD.

Infrastructure:
- Backend service (Railway, FastAPI, Supabase): done
- POST /api/crew/ai-sdr endpoint: done (routes/ai_sdr.py)
- Supabase logging: done (ai_sdr_batch_runs + ai_sdr_account_results tables created in staging)
- Gmail monitoring: not started (using mike.madsen@leandata.com for testing)
- Railway staging deployment: BLOCKED — MCP server (mcp-hub.leandata.workers.dev)
  IP-restricts Railway egress IPs. LEANDATA_MCP_API_KEY is valid (confirmed locally).
  Fix: Neil needs to whitelist Railway staging egress IPs on the MCP server.

Sequence structure (all 4 sequences):
- Step 1: MANUAL task in Outreach queue (human review gate — v1 QA mechanism)
- Steps 2-4: Automated, fire after Step 1 is manually sent
- Two v1 gates: (1) human_input=enrollment_enabled on enroll_prospect task, (2) Step 1 manual

Scenario 1 — Fintech: DONE + VALIDATED
- Outreach sequence: done (ID 5724)
- agents.yaml, tasks.yaml, ai_sdr_crew.py, endpoint: all done
- Validated locally: Everi (0.92, Dustin Dunn VP Sales Ops), OneStream (skip correct),
  IDeaS (prior_ld_contact=true, re-engagement framing)

Scenario 2 — Insurance: DONE + VALIDATED
- Outreach sequence: done (ID 5732)
- Validated locally: Humana (Brenda Hutton from SFDC contacts, 0.92, no banned logos),
  Aon (prior_ld_contact=true from closed-lost opps)
- Approved logos: Goosehead, Unum, Aflac ONLY (guardrails in icp_insurance.md)

Scenario 3 — SMB:
- Outreach sequence: done (ID 5733)
- ICP file: TBD

Scenario 4 — EMEA:
- Outreach sequence: done (ID 5734)
- ICP file: TBD

Quality fixes committed (all on feature/ai-sdr):
- Placeholder safety: null contact = no draft, QA flag, enroll hard skip
- 75-word limit (writer + QA reviewer synced, was 90)
- Banned: em dashes, ellipses, false urgency, proof point adjectives
- Step 2: curiosity question rule (ONE question, no pain diagnosis)
- Salesforce contact lookup before ZoomInfo (STEP 3b, saves credits)
- Closed-lost opp check sets prior_ld_contact in STEP 1
- Model fallback fix: claude-sonnet-4-6 removed from FALLBACK_PROVIDERS

Known issues / v1.1 backlog:
- Researcher early-exit: accounts like OneStream take ~2 min to skip instead of <30s.
  Needs hard-stop after SFDC validation fails. Tracked in tasks.yaml comment.
- Rate limit: 30K TPM on individual Anthropic plan throttles batches of 3+ accounts.
  Need higher-tier key on Railway for production.
- Outreach S2S permission: Sequence Enrollment scope not enabled on LeanData integration.
  Ron needs: Outreach > Settings > Apps > API > LeanData > enable Sequence Enrollment scope.
- draft_email task STEP 2 subject line says "4 words or fewer, lowercase" — inconsistent
  with agents.yaml rule of "2-5 words, sentence case". Fix in next pass.
- contact_source field (salesforce vs zoominfo) not surfacing in review_queue_entry output.

---

## Last session summary
2026-04-14 — AI SDR v1 fully built and validated locally (fintech + insurance, 5 accounts).
PR #1 merged. PR #2 open (GitHub #4), Ron tagged for review.
Staging live but MCP tools blocked — Neil needs to whitelist Railway egress IPs.
Full next steps: docs/AI_SDR_NEXT_STEPS.md
