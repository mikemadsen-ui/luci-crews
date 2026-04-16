# LeanData ICP — SMB (Small & Mid-Market)

> **Source:** Derived from closed won opportunity data, contact roles, and LUCI
> conversation intelligence across LeanData's SMB customer base.
> **Last updated:** 2026-04-16
> **Use:** AI SDR researcher and writer agents — SMB prospecting vertical

---

## What SMB Means Here

**SMB = SaaS companies with 10–500 employees.**
Sweet spot: 50–300 employees, Series A through Series C.
Salesforce as CRM (required — LeanData is Salesforce-native).
10–50 sales reps, no dedicated routing tool.

The defining characteristic of SMB is that **one person owns everything** —
RevOps, Sales Ops, Marketing Ops, and Salesforce admin, all combined into a
single role. They are the champion, the implementer, and often the economic buyer.

---

## Proven Customer Logos (SMB)

> These are confirmed LeanData customers in the 10–500 employee range.
> Safe to use in outreach as social proof.

| Account | Employee Count | Champion Title | ARR Band |
|---------|---------------|----------------|----------|
| Spekit | 187 | VP Revenue Operations | SMB |
| Qualio | 188 | Director Revenue Operations | SMB |
| Aerospike | 171 | VP Revenue Operations | SMB |
| Vestwell | 171 | VP RevOps | SMB |
| ZipHQ | 193 | Director GTM Systems | SMB |
| Medallion | 173 | Director Revenue Operations | SMB |
| Rightworks | 414 | Director Revenue Operations | SMB |
| Cloudinary | 407 | Revenue Operations Head | SMB |
| Industry Dive | 481 | Director RevOps | SMB |
| Mixpanel | 475 | — | SMB |

**Key insight:** All SMB wins had a single RevOps or GTM Systems owner as champion.
The champion IS the buyer. Skip the executive if you can get the RevOps person.

---

## Buying Committee Map

### Primary Target (find and email first)
**Title patterns from closed won SMB deals:**
- VP of Revenue Operations
- Director of Revenue Operations
- Head of Revenue Operations
- Director of GTM Systems
- Head of GTM Systems
- VP of Sales Operations
- Director of Sales Operations
- Revenue Operations Manager (if no Director or VP exists)

**What they own:** Everything. Salesforce admin, lead routing, attribution,
marketing ops, and often the SDR stack. They built the current routing in native
Salesforce flows because no one else was there to do it. Now it's a mess
they can't touch without breaking something.

**SMB-specific:** This person is often the company's first RevOps hire.
They joined 3–18 months ago, inherited a patchwork system, and are now
looking for tools that let them work faster without needing an engineer.

### Secondary Target (if no RevOps contact found)
- Founder or CEO (if company has no dedicated ops hire yet)
- VP of Sales (if they own ops at the company)
- Head of Marketing (if marketing runs revenue ops)

**Note:** At sub-50-employee companies, the Founder or CEO may be the only
person who can make this decision. Do not skip them.

### Executive Sponsor (same person at SMB)
At SMB companies, the primary target IS the executive sponsor. The RevOps
Director who signs off is the same person who will use the product daily.
There is no separate "budget owner" to go around or above them.

---

## Seniority Floor

**SMB primary contact:** Manager+ (VP/Director preferred)
**SMB exception:** Founders and CEOs are valid primary contacts at sub-100-employee companies.
**Do not target:** Pure IC analysts or coordinators — they cannot own the decision.

---

## Pain Themes (SMB-specific)

### 1. "Native Salesforce routing and no one can touch it"
The most common SMB pain. The first RevOps hire inherited routing built
in Salesforce Process Builder or Flows by someone who no longer works there.
Every change requires an engineer. Every audit is a prayer.

> This is the #1 tier-1 signal for SMB — treat `native_ceiling` as tier-1,
> not tier-2 as it is for Enterprise accounts.

**SDR angle:** "How is your routing currently built — native Salesforce flows,
or do you have a dedicated routing layer? Asking because that's usually where
the first RevOps hire at your stage hits a wall."

### 2. "One person doing everything for 50 reps"
SMB RevOps leaders are stretched thin. They are the team. Every manual task
they do is a task a rep isn't getting faster. LeanData is an automation story:
free up the one person doing all of this so they can actually improve the system.

**SDR angle:** "At your stage, the RevOps leader is usually doing admin work
that automation should handle. LeanData is how companies like yours get
30+ hours a month back without hiring."

### 3. "Leads falling through the cracks as we scale"
Routing rules that worked at 10 reps break at 25. New territories, new products,
new SDR/AE splits — each one requires a rule change. At SMB, those changes
pile up and eventually the routing becomes untouchable.

**SDR angle:** "How many reps do you have now? The routing complexity usually
catches up around 20–30 reps — new territories, new hire assignments, round-robin
that stopped working after the last team change."

### 4. First RevOps hire — inherited chaos
When a company makes their first RevOps hire, they walk into inherited Salesforce
complexity. They can't move fast because they don't know what they'll break.
LeanData gives them a visual, ownable system they can understand and change
without needing engineering.

**SDR angle:** "New RevOps hires usually spend their first 90 days just trying
to understand what the current routing is actually doing. LeanData makes that
visible on day one."

---

## Competitive Context (SMB-specific)

**Most common competitors in SMB deals:**
1. **Native Salesforce (Process Builder / Flow)** — Not a tool, but the most
   common "competitor" at SMB. Built by someone who left. No one wants to touch it.
   This is the `native_ceiling` signal — it's tier-1 for SMB.
2. **Chili Piper** — Common at SMB for meeting scheduling. They sometimes push
   routing as an add-on. Weakness: not built for routing, no visual graph.
3. **No tool at all** — Very common sub-100-employee. Routing is whoever's
   Slack message gets answered fastest. Manual triage by the RevOps person.
4. **Internal build** — Rare at SMB (engineering is busy), but happens at
   technical product companies.

**Win angle for SMB:** LeanData is the first real routing system these companies
own. The pitch is: stop spending hours maintaining broken Salesforce flows.
Get a visual, no-code system any RevOps person can own and change without
an engineer, without a ticket, without risk.

---

## Signal Priorities for SMB

Tier-1 signals (highest priority):
1. **new_exec_hire** — First RevOps hire at the company. Highest urgency.
   They're actively trying to figure out what they inherited.
2. **native_ceiling** — Native Salesforce routing detected in tech stack
   (NO dedicated routing tool like Chili Piper, RingLead, or LeanData).
   This is tier-1 for SMB, unlike Enterprise where it's tier-2.
3. **high_intent** — 6sense or Bluebirds signal detected.
4. **tech_stack_hit** — Chili Piper in stack (common at SMB, routing add-on upsell).

Tier-2 signals:
5. **re_engagement** — Prior LeanData contact or demo >12 months ago.
6. **competitive_win** — Same sub-vertical as recent SMB win.
7. **ai_transformation** — AI signals without Agentforce.

---

## Contact Targeting Parameters for ZoomInfo Search

When the researcher agent searches for contacts at SMB prospect accounts,
use these parameters:

```
Title keywords (use OR logic):
  "Revenue Operations" AND (VP OR Director OR Head OR Manager)
  "Sales Operations" AND (VP OR Director OR Head)
  "GTM Operations" AND (Director OR Head OR Manager)
  "GTM Systems" AND (Director OR Head)
  "RevOps" (any seniority — SMB titles are less standardized)

Also include:
  "Founder" (if employee count < 100)
  "CEO" (if employee count < 100 and no RevOps hire detected)

Seniority: Manager, Director, Vice President, C-Level, Owner/Founder
Exclude: "analyst", "coordinator", "specialist" (unless Senior Manager+)

Department: Sales, Revenue Operations, Marketing Operations, General & Administrative

Employee count filter:
  SMB tier 1 (sweet spot): 50–300 employees
  SMB tier 2 (borderline): 10–49 or 300–500 employees
```

---

## Email Personalization Hooks (SMB-specific)

**If they are the first RevOps hire (new_exec_hire signal):**
> "When a first RevOps hire walks into a company, routing is usually the first
> thing that needs to be rebuilt — native Salesforce flows that no one can touch,
> assignments that broke when the team changed. Spekit and Vestwell both fixed
> this in their first 90 days with LeanData."

**If they use Chili Piper (tech_stack_hit):**
> "Chili Piper is great for scheduling — but when routing logic starts living
> there too, you end up maintaining rules in two places. At your stage, that
> double-maintenance usually means one system is always out of date."

**If they have native Salesforce routing (native_ceiling):**
> "Native Salesforce flows are how most companies start. The problem isn't
> the flows — it's that no one can read them, change them, or audit them
> without breaking something. Qualio and Aerospike both ran into this
> at the same stage you're at now."

**If they are scaling fast (funding round or headcount growth):**
> "Routing rules that worked at 15 reps usually break somewhere between
> 25 and 40 — new territories, new AE/SDR splits, round-robin that
> doesn't account for capacity. Companies at your stage usually hit this
> right after a funding round."

---

## Reference Customers to Use in Outreach

Safe to reference in cold emails (all confirmed LeanData customers):
- **Spekit** — first RevOps hire story, native Salesforce routing replacement
- **Qualio** — routing complexity at scale, compliance context
- **Aerospike** — VP RevOps as champion, visual routing story
- **Vestwell** — fintech/SMB crossover, VP RevOps champion
- **Rightworks** — 400+ employee SMB, Director RevOps champion
- **Cloudinary** — developer tools / SaaS SMB
- **Mixpanel** — product analytics company, SMB reference

Do not reference specific ARR, deal terms, or implementation details.

---

## Sample Email Framework (for writer agent)

Writer: you receive `signal_type` (primary) and `signals_used` (all detected). Blend them
naturally like a human SDR who did their homework. Reference `signal_play_catalog.md` for play
framing and blending rules. Never make it feel like a play was selected — make it feel like you
noticed something specific about this company.

```
Subject line options:
- "Routing after [N] reps"
- "Quick question on your Salesforce flows"
- "[Their company] + LeanData — quick question"
- "How Spekit fixed their routing in one sprint"

Opening (1 sentence, pain-specific):
  Reference one signal — the RevOps hire date, the tech stack,
  the headcount growth, or the funding round.

Middle (2–3 sentences):
  Connect to the SMB pattern. Reference one referenceable customer
  from the proof points list (or Spekit/Qualio from ICP file as fallback).
  Frame around the "one person doing everything" or "native routing ceiling" story.

CTA (1 sentence):
  "Worth 20 minutes to see if you're hitting the same wall?"

Signature: [Mike], LeanData
Social proof: "We work with Spekit, Aerospike, and Vestwell on this."
  (or use referenceable_proof_points from research output if populated)
```

---

## Industry Context — Why SMB RevOps Is Under Pressure Right Now
# Source: LeanData Vertical Intelligence Research, April 2026
# Use these stats to add credibility and urgency to email copy.
# Never fabricate stats. Only use what is listed here.

### The macro environment (2025-2026)
- Series A revenue thresholds are up 4x since 2021.
  SMB SaaS companies must grow faster with smaller teams.
- Average RevOps team size at Series A companies: 1 person.
  That one person owns routing, attribution, Salesforce admin,
  and reporting simultaneously.
- SMB SaaS churn rates average 10-15% annually — faster routing
  and better handoffs directly reduce time-to-value and churn.

### Stats the writer agent can reference (with attribution)
- Reps spend 60-65% of their time on non-selling activities.
  69% of reps missed quota in 2024 even as their companies grew revenue.
  (Source: Hyperbound 2025)
  Email use: "At 30 reps, that's 18 people spending most of their day
  not selling. Routing and handoff automation changes that ratio."

- A 5-minute delay in lead response materially reduces conversion.
  (Source: Zams 2025)
  Email use: "Speed to lead is not a nice-to-have when you have
  one RevOps person managing routing manually for 40 reps."

- 46% of RevOps directors say their GTM processes are overly manual
  and lack automation. (Source: Forrester 2024)
  Email use: "Nearly half of RevOps teams are still doing manual
  triage on inbound — even at companies that have 'automation' in their stack."

- Companies with strong sales/marketing alignment see 38% higher win rates —
  yet only 11% of B2B companies prioritize seamless handoffs.
  (Source: ARISE GTM / Influ2 2025)
  Email use: "The handoff gap is where most SMB pipeline leaks.
  Routing is the fix — not more reps."

### Key pain points to reference in email copy

1. Native Salesforce routing ceiling
   Most SMB companies built their first routing in Salesforce Process Builder
   or Flow. As the team scales, those flows become unmaintainable — no visual
   audit trail, no easy change management, engineer required for every update.
   SDR angle: "What does your current routing look like — Salesforce flows,
   or do you have a dedicated layer?"

2. One RevOps person doing everything
   At 50–200 employees, there is typically one person running all of RevOps.
   Every manual routing task steals time from strategic work.
   SDR angle: "How much of your week is spent on routing maintenance
   vs. actually improving the GTM system?"

3. Speed-to-lead failure at scale
   Manual lead assignment from a form submission to a rep takes minutes at best.
   At 30+ reps with territories and round-robin, it breaks down entirely.
   SDR angle: "From form submit to rep assignment — what does that
   flow look like today, and how long does it take?"

4. Scaling beyond the routing rules
   Every new territory, new hire, or new round-robin group requires
   a rule change. At SMB, those changes stack up until no one is sure
   what the current state of routing is.
   SDR angle: "When you add a new AE or change territories, how long
   does it take to update routing? Who makes that change?"

5. First RevOps hire inheriting chaos
   New RevOps hires at SMB companies rarely get a clean handoff.
   They inherit undocumented Salesforce configurations built by
   someone who left, and have to reverse-engineer the routing logic
   before they can improve anything.
   SDR angle: "How long did it take you to understand what the
   routing was actually doing when you got here?"

### Persona-specific angles

VP / Director of Revenue Operations:
- Core concern: Work smarter with no team, fast time-to-value, clean system
- Lead with: "One RevOps person shouldn't spend 10+ hours a week on
  routing maintenance. LeanData cuts that to under 30 minutes."
- Frame LeanData as a force multiplier — one person, full routing control

Head of GTM Systems:
- Core concern: Clean Salesforce architecture, no custom code
- Lead with: Salesforce-native, no middleware, visual graph any admin can own
- Frame as: "Replace the Salesforce flows with something you can actually audit"

Founder / CEO (sub-100 employees):
- Core concern: Pipeline predictability, not losing leads at this stage
- Lead with: Speed-to-lead and lead fall-through
- Frame as: "Every lead you're losing now costs more to replace than
  fixing the routing. This is a $30K revenue decision, not a $10K software decision."

Revenue Operations Manager:
- Core concern: Daily CRM hygiene, fewer escalations from reps about wrong assignments
- Lead with: "Reps stop asking RevOps 'why did this go to me' when routing
  is visual and self-explanatory."
- Frame as: eliminate the daily routing triage work
