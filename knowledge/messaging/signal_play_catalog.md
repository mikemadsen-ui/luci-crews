# Signal Play Catalog

---

## Core Philosophy

The goal is not to "select a play" — it is to write like a thoughtful human SDR who reviewed
everything they know about this account and connected the dots naturally.

Real SDRs don't think "I'll use the tech stack play today." They think: "This company is running
RingLead, just hired a new VP Ops, and 6sense shows them in Consideration stage. The new VP is
probably the one evaluating routing tools right now. I'll open with the hire, reference the
RingLead pain in the body, and use Goosehead as the proof point since they're a similar size."

That's the standard. The catalog is a reference tool — not a decision tree.

---

## Signal Detection

The researcher identifies ALL signals present and sets:
- `signal_type`: the PRIMARY signal (strongest/most specific)
- `signals_used`: ALL signals detected (for writer context)
- `signal_priority`: 1-10 rank based on hierarchy below

### Signal Priority Hierarchy (1 = strongest)

| Priority | Signal Type | Trigger |
|----------|-------------|---------|
| 1 | `champion_move` | UserGems contact (LeadSource='UserGems') |
| 2 | `agentforce_partner` | Agentforce in ZoomInfo tech stack |
| 3 | `renewal_trigger` | Closed-lost CloseDate 6-8 months ago |
| 4 | `high_intent` | 6sense/Bluebirds tier-1 signal |
| 5 | `tech_stack_hit` | Competitor routing tool in stack |
| 6 | `new_exec_hire` | ICP title joined in last 90 days |
| 7 | `re_engagement` | prior_ld_contact=true, >12 months ago |
| 8 | `competitive_win` | Same sub-vertical as recent LD win |
| 9 | `ai_transformation` | AI initiative signals, no Agentforce |
| 10 | `native_ceiling` | No routing tool, SFDC present |

---

## Writer Instruction

You receive `signals_used` (all signals) and `signal_type` (primary). Your job is to blend them
naturally — not to mechanically apply one play.

### Rules for Blending Signals

- **Step 1:** Lead with the PRIMARY signal. Optionally weave in ONE secondary signal if it
  strengthens the angle. Never reference more than 2 signals in a single email.
- **Step 2:** Ask a curiosity question that connects to the primary signal context.
  If `re_engagement`, open with "Checking back in."
- **Step 3:** Customer proof point. Choose the proof point that best matches the primary
  signal vertical.
- **Step 4:** Breakup. No signals referenced.

### Signal Stacking Examples (how a human would blend)

**tech_stack_hit + new_exec_hire:**
> "Saw [Name] joined as [Title] — new ops leaders usually take a hard look at routing,
> especially when RingLead is in the stack."

*(Lead with the hire, reinforce with the tech signal)*

**high_intent + competitive_win:**
> "Routing seems to be on your radar. Goosehead was in a similar spot — dealing with daily
> routing fires and no visibility into why leads were going to the wrong agent."

*(Lead with intent implicitly, ground with proof)*

**renewal_trigger + re_engagement:**
> "Checking back in — it's been about 6 months. A lot has changed in what we can do for
> routing since we last spoke."

*(Combine prior relationship + renewal timing naturally)*

**champion_move (standalone — most powerful play):**
> "Saw you came from [Company] — you know what good routing looks like. Worth seeing what
> that could look like here at [New Company]?"

*(No blending needed — the champion signal is strong enough to stand alone)*

---

## Plays Reference

---

### Play 1: Tech Stack Hit (Competitive Takeout)

**Signal type:** `tech_stack_hit`
**Detection:** ZoomInfo tech stack contains RingLead, Chili Piper, Calendly, Traction Complete, Openprise
**Best step:** 1
**Standalone angle:** Visibility and control gap in the current tool
**Blends well with:** `new_exec_hire`, `high_intent`, `competitive_win`

**Real customer voice** (use as framing reference — do not quote directly):
- "Rule by rule by rule — no way to see the whole workflow" (LinearB on RingLead)
- "I hate their reporting engines. Hate all of it." (Device42 on Chili Piper)

**Good:** "Saw you're running routing through RingLead — is the workflow visibility what you'd expect at scale?"
**Bad:** "Your competitors are switching away from RingLead."

---

### Play 2: Homegrown / Salesforce Native Ceiling

**Signal type:** `native_ceiling`
**Detection:** No routing tool in ZoomInfo tech stack, Salesforce present, employees > 500 or sales team > 50
**Best step:** 1 or 3
**Standalone angle:** What breaks when you outgrow native Salesforce assignment rules
**Blends well with:** `new_exec_hire`, `high_intent`

**Real customer voice:**
- "We didn't want to wait sprint cycles to change routing" (Infor)
- "Basic SFDC routing causes SDR notification issues and slows SLAs" (Terminal)

**Good:** "Most teams outgrow Salesforce native routing around 50 reps — is that starting to show up?"
**Bad:** "You should replace your Salesforce routing setup."

---

### Play 3: New Exec Hire

**Signal type:** `new_exec_hire`
**Detection:** graph_account_network or ZoomInfo shows VP/Director Revenue Ops, Sales Ops, or GTM Ops joined in last 90 days
**Best step:** 1
**Standalone angle:** New leaders inherit routing complexity before anything else in first 90 days
**Blends well with:** `tech_stack_hit`, `high_intent`, `competitive_win`, `native_ceiling`

**Good:** "Saw [Name] joined as [Title] — new ops leaders usually inherit routing complexity before anything else."
**Bad:** "Congratulations on the new hire at [Company]."

**Notes:** If the new exec IS the target contact, do not reference the hire — address a different angle.

---

### Play 4: Company AI Transformation

**Signal type:** `ai_transformation`
**Detection:** AI-related keywords in company news, job postings referencing AI automation, or AI tools in tech stack (but not Agentforce — use Play 9)
**Best step:** 1
**Standalone angle:** AI workflows need clean routing as the foundation — bad data routing = bad AI output
**Blends well with:** `agentforce_partner`, `new_exec_hire`

**Good:** "Saw [Company] is leaning into AI-powered sales workflows. Routing accuracy is the foundation everything else sits on."

---

### Play 5: High Intent Signal

**Signal type:** `high_intent`
**Detection:** 6sense Consideration or Decision stage, Bluebirds HIGH, ZoomInfo intent HIGH
**Best step:** 1 (highest urgency)
**Standalone angle:** Act on the intent without revealing the source
**Blends well with:** `tech_stack_hit`, `new_exec_hire`, `competitive_win`

**Good:** "Routing seems to be on your radar right now — worth a quick conversation about what you're evaluating?"
**Bad:** "Our intent data shows you're researching routing tools." — NEVER name the signal source.

---

### Play 6: Re-engagement

**Signal type:** `re_engagement`
**Detection:** prior_ld_contact = true, closed-lost CloseDate > 12 months ago
**Best step:** 2 (open Step 2 with "Checking back in.")
**Standalone angle:** Acknowledge familiarity, pivot to what has changed
**Blends well with:** `renewal_trigger`, `tech_stack_hit`

**Good:** "Checking back in — a lot has changed in routing since we last spoke."
**Bad:** "We spoke in 2022 but you went with a competitor."

---

### Play 7: Competitive Win (Look-alike)

**Signal type:** `competitive_win`
**Detection:** Prospect in same LD_Industry__c or LD_Sub_Industry__c as recent closed-won customer
**Best step:** 1 or 3
**Standalone angle:** What the comparable company was experiencing — not that they switched
**Blends well with:** `high_intent`, `tech_stack_hit`

**Good:** "Goosehead was dealing with daily routing fires — leads to wrong agents, no audit trail for compliance."
**Bad:** "Goosehead just switched to us."

**Notes:** 3+ wins in sub-vertical = use freely. 1 win = use carefully, no pattern claim.

---

### Play 8: Champion Play (UserGems)

**Signal type:** `champion_move`
**Detection:** Contact at account where LeadSource = 'UserGems' in Salesforce (UserGems fires automatically when a champion from a LeanData customer moves to a new company)
**Best step:** 1
**Standalone angle:** You know what good routing looks like — worth bringing it to the new company
**Blends well with:** Nothing — this play is strong enough to stand alone. Don't dilute it.

**Good:** "Saw you came from [Company] — you know what good routing looks like. Worth seeing what that could look like here?"
**Bad:** "We see you previously worked at our customer."

**Notes:** The UserGems contact IS the target contact. Email goes directly to them. Highest priority play.

---

### Play 9: Partner Play (Agentforce)

**Signal type:** `agentforce_partner`
**Detection:** "Agentforce" in ZoomInfo tech stack
**Best step:** 1
**Standalone angle:** LeanData BookIt connects scheduling directly into Agentforce workflows — one less handoff, AI-powered meeting booking
**Blends well with:** `ai_transformation`, `new_exec_hire`

**Good:** "Saw you're running Agentforce. BookIt plugs scheduling directly into those flows — worth seeing how it works together?"
**Bad:** "LeanData has a Salesforce partnership."

---

### Play 10: Renewal Trigger

**Signal type:** `renewal_trigger`
**Detection:** Most recent closed-lost CloseDate was 6-8 months ago (assumes annual contract — 6 months post-loss = approaching renewal window)
**Best step:** 1
**Standalone angle:** Timing may be better now — worth a quick look before they renew the incumbent
**Blends well with:** `re_engagement`, `tech_stack_hit`

**Good:** "It's been about 6 months since we last spoke — timing might be better for a quick look at what's new before your next renewal cycle."
**Bad:** "Your contract with [competitor] is coming up."

**Rules:** Never name the competitor. Never reference why they didn't buy.

---

### Play 11: Event Invitation

**Signal type:** `event_invitation`
**Detection:** LIST-BASED — curated list of accounts in event city. Pass play_type="event_invitation" in API request.
**Best step:** 1 (3-4 weeks before event)
**Standalone angle:** Relevant session at a local event LeanData is sponsoring

**Good:** "We're hosting a session at [Event] in [City] on [topic] — given what you're working on, might be worth 30 minutes."

---

### Play 12: Switch & Save

**Signal type:** `switch_and_save`
**Detection:** LIST-BASED — requires competitor renewal date intelligence. Not auto-detectable.
**Best step:** 1
**Standalone angle:** Migration timing, cost comparison

---

### Play 13: Bridge to Value (Product Gap)

**Signal type:** `bridge_to_value`
**Detection:** Specific competitor in stack + known product gap from battlecard
**Best step:** 3 (after establishing interest)
**Standalone angle:** Specific capability the incumbent lacks

**Notes:** Requires updated battlecard. Do not use without verified product gap.
