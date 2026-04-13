# AI SDR Crew — Build Brief
# Hand this to Claude Code as the first message of the build session

## Goal
Build a CrewAI crew that researches prospect accounts, finds the right
contact using ICP parameters, drafts a personalized outreach email, and
outputs a human-review queue as structured JSON. Nothing touches Outreach
until a human reviews and approves. The crew plugs into the existing
FastAPI service on Railway as a new endpoint: POST /api/crew/ai-sdr.

## Architecture context
- This is a new crew added to the existing luci-crews FastAPI backend
- Pattern to follow: look at an existing crew file in src/luci_crews/crews/
  to understand how crews are structured, how agents are loaded, how tasks
  are chained, and how results are returned
- New files needed:
  1. src/luci_crews/crews/ai_sdr_crew.py
  2. Entries in src/luci_crews/config/agents.yaml (section: AI SDR CREW)
  3. Entries in src/luci_crews/config/tasks.yaml (section: AI SDR CREW)
  4. New API route: POST /api/crew/ai-sdr (follow existing route pattern)

## Agents — build one at a time, test before moving to next

### Agent 1: sdr_prospect_researcher
role: "SDR Prospect Researcher"
goal: Validate that an account is a genuine prospect, enrich it with
      firmographic data, and find the highest-priority contact to reach
      using ICP title parameters based on the vertical (fintech or insurance).
backstory: Expert in B2B account research who has profiled thousands of
           prospect accounts. Understands that wasted outreach on existing
           customers or accounts already in pipeline costs the team credibility.
           Always validates before enriching. Knows that the right contact
           matters more than the right message.

### Agent 2: sdr_signal_reader
role: "SDR Signal Intelligence Analyst"
goal: Surface conversation signals, intent patterns, and account context
      from LUCI and Avoma that can make outreach feel personal and timely.
backstory: Expert in reading conversation intelligence data to find the
           signals that make cold outreach feel warm. Knows that a reference
           to a recent pain point, a tool they mentioned, or a growth milestone
           is worth more than any generic personalization token.

### Agent 3: sdr_email_writer
role: "SDR Email Writer"
goal: Draft a concise, personalized outreach email using the account research
      and signals surfaced, following the messaging framework in the ICP file
      for the relevant vertical. Emails should be 3 sentences max in the body.
backstory: Expert in B2B cold email who has written thousands of outbound
           emails for SaaS companies. Knows that the best cold email shows
           you did your homework, connects to a real pain, and asks for one
           small thing. Never writes feature lists. Never writes "I hope this
           finds you well." Always writes like a human, not a robot.

### Agent 4: sdr_qa_reviewer
role: "SDR Output QA Reviewer"
goal: Score the output for quality and confidence, flag any records that
      should not be sent (wrong contact type, low signal, missing data),
      and format the final JSON review queue.
backstory: Quality-obsessed reviewer who has seen bad outreach damage pipeline
           and good outreach open doors. Knows that a flagged record saved
           from sending is better than a bad email that burns a prospect.

## Tasks — one per agent, chained sequentially

### Task 1: research_prospect (owned by sdr_prospect_researcher)
For each account in the input list:
1. salesforce_query: confirm Account.Type != 'Customer'
   - If customer: skip, add to skipped_accounts with reason "existing customer"
2. salesforce_query: check for open opportunities (IsClosed = false)
   - If any open opps exist: skip, add to skipped_accounts with reason "in pipeline"
3. zoominfo_enrich_company: get firmographic data
4. zoominfo_search_contacts: find target contact using ICP params
   - Fintech: "Revenue Operations" OR "Sales Operations" + VP/Director/Head/Sr Director
   - Insurance: same + "Salesforce" + Head/Senior Manager
   - Seniority: Director+ for fintech, Senior Manager+ for insurance
   - Return top 1 contact (highest seniority match)
Output: enriched account object with validated prospect status and target contact

### Task 2: gather_signals (owned by sdr_signal_reader)
For each validated prospect account:
1. luci_search_portfolio: semantic search for pain signals
   - Query: "lead routing problems revenue operations [company name]"
   - match_threshold: 0.35
   - data_type_filter: ["customer_voice", "transcription_customer"]
2. avoma_search_meetings: check for any past meetings (last 180 days)
   - If meetings found: note subject and date (signals prior relationship)
Compile signals into a list of strings: max 3 signals per account
If no signals found: return empty list (writer will use ICP-level personalization)
Output: signals list per account

### Task 3: draft_email (owned by sdr_email_writer)
Using account data + contact + signals + ICP file for the vertical:
1. Load the relevant ICP file (fintech or insurance) for messaging framework
2. Select the most relevant pain theme and opening hook
3. Draft email:
   - Subject: one of the subject line options from the ICP file, customized
   - Body: 3 sentences max
     - Sentence 1: personalized opening (use a signal if available,
       otherwise use ICP-level hook based on company profile)
     - Sentence 2: connect to relevant customer story (Stripe/Ramp for
       fintech; Goosehead/Unum for insurance)
     - Sentence 3: soft CTA ("Worth 20 minutes to see if you're running
       into the same thing?")
   - Signature: [Name], LeanData | "We work with [logo1] and [logo2] on this."
Output: draft_email object with subject and body

### Task 4: review_and_score (owned by sdr_qa_reviewer)
For each draft:
1. Score confidence (0.0 to 1.0):
   - 0.9+ : target contact found, title matches ICP exactly, 2+ signals used
   - 0.7–0.89: contact found, title approximate match, 1 signal or ICP hook
   - 0.5–0.69: contact found but title is weak match, no signals
   - Below 0.5: auto-flag
2. Flag record if any of:
   - confidence < 0.5
   - No email found for contact
   - Contact title doesn't match ICP parameters
   - Email body is generic (no company-specific reference)
3. Format final output as JSON matching output schema in CLAUDE.md
Output: final review_queue.json

## Input schema
POST /api/crew/ai-sdr
```json
{
  "accounts": [
    { "account_name": "Acme Corp", "salesforce_id": "0015A00000XXXXXX" }
  ],
  "vertical": "fintech",
  "dry_run": true
}
```

## Output schema
```json
[{
  "account_name": "string",
  "salesforce_id": "string",
  "vertical": "fintech | insurance",
  "target_contact": {
    "name": "string",
    "title": "string",
    "email": "string",
    "linkedin": "string or null"
  },
  "draft_email": {
    "subject": "string",
    "body": "string"
  },
  "confidence": 0.85,
  "signals_used": ["string"],
  "flagged": false,
  "flag_reason": null
}]
```

## Constraints — non-negotiable
- NEVER call outreach_add_prospect_to_sequence
- NEVER call zoominfo_enrich_company before SFDC validation passes
- Skip Account.Type = 'Customer'
- Skip accounts with any open opportunity (IsClosed = false)
- dry_run: true must produce output JSON but make zero external writes
- ZoomInfo managementLevel = full strings ("Vice President" not "VP")
- LUCI UUIDs only — not Salesforce IDs

## Build order — one agent at a time
1. Add sdr_prospect_researcher to agents.yaml
2. Add research_prospect task to tasks.yaml
3. Build ai_sdr_crew.py skeleton with just the researcher agent
4. Test: POST /api/crew/ai-sdr with 2 dry-run accounts, confirm SFDC
   validation logic works and ZoomInfo returns a contact
5. Only then add sdr_signal_reader — repeat pattern
6. Add sdr_email_writer
7. Add sdr_qa_reviewer
8. Wire the POST /api/crew/ai-sdr endpoint

## Success test (v1)
Run against 3 accounts from the fintech dry-run fixture.
Expected:
- Valid review_queue.json with 1 record per account (or skipped with reason)
- Each record has target_contact with a real email
- Each draft_email has a subject and body referencing the account
- No calls to outreach_add_prospect_to_sequence in logs
- Runtime under 3 minutes for 3 accounts

## Out of scope for v1
- Scenarios 3 and 4 (not yet defined)
- Automatic Outreach enrollment (blocked on Outreach S2S bug)
- Scheduling or cron-based triggers
- Supabase write logic (return JSON from endpoint only for now)
- Multi-contact outreach per account
