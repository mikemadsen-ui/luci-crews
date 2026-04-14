# LeanData ICP — Financial Technology (Fintech)

> **Source:** Derived from closed won opportunity data, contact roles, and LUCI
> conversation intelligence across LeanData's fintech customer base.
> **Last updated:** 2026-04-12
> **Use:** AI SDR researcher and writer agents — fintech prospecting vertical

---

## Proven Customer Logos (Fintech)

| Account | Sub-Vertical | Initial ARR | Lead Source |
|---------|-------------|-------------|-------------|
| Stripe | Payments | $399K | Organic |
| Ramp | Payments | $45K | Sales |
| Brex | Payments | $15K | Sales |
| PayPal | Payments | $360K | Sales |
| Bluevine | Lending | $19K | Sales |
| OFX | Payments | $38K | Web Referral |
| Flex | Payments | $22K | Organic |
| One Park Financial | Lending | $24K | Sales |
| Figure Technologies | Lending | $12K | Sales |

**Key insight:** Stripe ($740K ARR), Ramp ($258K), and PayPal ($360K) are
marquee logos that create social proof in fintech prospecting conversations.
Use them as reference points — fintech RevOps leaders know these companies.

---

## Buying Committee Map

### Primary Target (find and email first)
**Title patterns that appear as Champion or Decision Maker in closed won deals:**
- VP of Revenue Operations
- Senior Director, Revenue Operations
- Director of Revenue Operations
- Head of Sales Operations & Enablement
- Senior Manager, GTM Operations
- Head of GTM Systems

**What they own:** Lead routing, Salesforce architecture, GTM tech stack,
RevOps tooling decisions. They feel the pain of broken routing daily.
They are the champion who sells LeanData internally.

### Secondary Target (find as influencer/validator)
- Sales Operations Manager
- Revenue Operations Manager
- Revenue Operations Analyst
- Salesforce Administrator

**What they own:** Day-to-day Salesforce administration and routing maintenance.
Often the person who discovered the problem and escalated it. Useful as a
warm intro to the primary contact.

### Executive Sponsor (reference in email, don't cold email directly)
- CRO
- VP of Sales
- Head of Performance Marketing & Operations
- President, North America

**What they own:** Budget and strategic GTM direction. They approve the
purchase but are rarely the initiator.

---

## Seniority Floor

**Fintech primary contact:** Director+ (Senior Manager accepted if GTM/RevOps focus)
**Do not target:** Individual contributor RevOps analysts as primary outreach
(they are influencers, not decision makers in fintech deals)

---

## Pain Themes (from actual customer conversations)

These are the problems your fintech prospects are experiencing right now.
Use these to frame outreach — they are real, not assumed.

### 1. Routing complexity at scale
Fintech companies scale fast. Their routing rules multiply, break, and become
impossible to audit. From actual customer conversations:

> "We basically have our routing rules duplicate, one in Chili Piper, one in
> Gradientworks today — we wanna make one change, that means two individual
> systems need to be updated and tested." — RevOps leader, evaluating LeanData

> "Before implementing LeanData when we were running routing through Openprise,
> there was essentially 3 ways something could route... I wanted to do a one-time
> routing job to try to clean that up." — RevOps leader, post-implementation

**SDR angle:** If they're using Chili Piper, ZoomInfo/RingLead, or any combination
of tools for routing, they likely have this problem.

### 2. Leads going cold / speed to lead failure
Fintech companies generate significant inbound but lose revenue when leads
aren't routed and contacted fast enough.

> "Only 40% of leads were contacted within the SLA. Our SLA at the time was
> 24 hours — each marketing lead roughly cost us about $100. We were losing
> so much money prior to revamping our graph with LeanData." — RevOps leader, Uber

> "Leads going cold — it wasn't being routed, and so we set up contact routing
> via LeanData so that we can route re-engage contacts. That was a huge revenue
> lever for us." — RevOps leader, Uber

**SDR angle:** Ask about their speed-to-lead SLA and whether they can measure it.
If they can't measure it, they definitely have this problem.

### 3. Visibility — can't see what routing is doing
Manual, rule-based systems are black boxes. RevOps leaders can't tell
why a lead went where it went.

> "The most power in LeanData — it was 2016, I was the new CMO, I came in and
> in one weekend with no training I did all of our lead routing, contact routing,
> account routing. By Monday we were set up. The power is this no-code visual
> graphing that gives you a ton of power." — Customer, Intellum

> "I struggled with following the process map itself — with RingLead you have to
> make 5 or 6 clicks to actually get to an error log." — Customer, Intellum

**SDR angle:** Lead with the visual graph. Fintech RevOps leaders who have
lived in RingLead or Chili Piper immediately see the value.

### 4. Competing with internal builds
Fintech engineering teams are strong. Some prospects have built internal routing.
This is the objection to get ahead of.

**SDR angle:** Acknowledge it directly — "A lot of fintech RevOps teams we talk
to have explored internal builds. The ones who come to us usually hit one of
two walls: maintenance burden when routing rules change, and no visibility into
why a lead routed the way it did."

---

## Competitive Context

**Most common competitors in fintech deals:**
1. **Chili Piper** — Often already in use for scheduling; they push routing
   as an add-on. Weakness: routing is not their core, no visual graph.
2. **ZoomInfo/RingLead** — Bundled with ZI data contracts. Weakness: clunky
   UI, rule-by-rule setup, no visual workflow, poor error logging.
3. **Internal build** — Common in fintech where engineering is strong.
   Weakness: maintenance cost, no dedicated support, breaks when team changes.

**Win angle against all three:** Visual, no-code routing that any RevOps admin
can own and audit without engineering. LeanData is the system of record for
GTM motion — not a feature bolted onto a data tool or scheduling tool.

---

## Contact Targeting Parameters for ZoomInfo Search

When the researcher agent searches for contacts at fintech prospect accounts,
use these parameters:

```
Title keywords (use OR logic):
  "Revenue Operations" AND (VP OR Director OR "Senior Director" OR Head OR Manager)
  "Sales Operations" AND (VP OR Director OR "Senior Director" OR Head)
  "GTM Operations" AND (Director OR Head OR Manager)
  "GTM Systems" AND (Director OR Head OR Manager)
  "Sales Enablement" AND (Director OR Head)

Seniority: Manager, Director, Vice President, C-Level
Exclude titles containing: "analyst" OR "coordinator" OR "specialist" (unless
  combined with "Senior Manager" or higher)

Department: Sales, Revenue Operations, Marketing Operations

Employee count filter for prospect accounts:
  Fintech Payments: 200–5000 employees
  Fintech Lending: 100–2000 employees
```

---

## Email Personalization Hooks (fintech-specific)

Use one of these opening angles in the writer agent prompt — pick based on
whatever signal the researcher agent surfaces:

**If they use Chili Piper:**
> "Most fintech RevOps teams using Chili Piper for scheduling eventually hit
> the same wall — routing logic needs to live somewhere, and Chili Piper wasn't
> built to own it. Ramp and Brex both ran into this."

**If they've scaled past Series B:**
> "Post-Series B is usually when routing complexity catches up to fintech
> RevOps teams — more reps, more territories, more edge cases than any
> rule-based system handles cleanly."

**If they have multiple GTM tools:**
> "When routing rules live in multiple systems, every change is double work
> and every audit is a nightmare. LeanData becomes the single source of truth
> for who owns what lead, account, or contact — and why."

**If they mention data quality or matching:**
> "Lead-to-account matching is usually where fintech RevOps teams tell us
> the problem starts — a lead comes in, doesn't match to the right account,
> and routes to the wrong rep or goes cold entirely."

---

## Reference Customers to Use in Outreach

Safe to reference in cold emails (widely known logos, publicly announced):
- **Stripe** — large-scale routing and BookIt for forms
- **Ramp** — territory routing, advanced orchestration
- **Brex** — contact routing implementation
- **PayPal** — endpoint routing at scale

Do not reference specific ARR, deal terms, or internal implementation details.

---

## Sample Email Framework (for writer agent)

Writer: you receive `signal_type` (primary) and `signals_used` (all detected). Blend them
naturally like a human SDR who did their homework. Reference `signal_play_catalog.md` for play
framing and blending rules. Never make it feel like a play was selected — make it feel like you
noticed something specific about this company.

```
Subject line options:
- "How [similar fintech] fixed their routing in one sprint"
- "Ramp and Brex both had this routing problem"
- "[Their company] + LeanData — quick question"

Opening (1 sentence, pain-specific):
  Reference one signal from the researcher agent — a tool they use,
  a recent hire, a growth milestone, or a routing-related job posting.

Middle (2–3 sentences):
  Connect their situation to the pattern you see at fintech companies
  at their stage. Reference one relevant customer logo.

CTA (1 sentence):
  Ask for 20 minutes, not a demo. "Would it be worth a 20-minute
  conversation to see if we're seeing the same thing at [company]?"

Signature: Include name, title, LeanData, and a one-line social proof
  ("We work with Stripe, Ramp, and Brex on this exact problem.")
```

---

## Industry Context — Why Fintech RevOps is Under Pressure Right Now
# Source: LeanData Vertical Intelligence Research, April 2026
# Use these stats to add credibility and urgency to email copy.
# Never fabricate stats. Only use what is listed here.

### The macro environment (2025-2026)
- Fintech has moved from growth-at-all-costs to efficiency-first.
  Series A revenue thresholds are up 4x since 2021.
- Over 25,000 active fintech startups compete globally.
  GTM teams must produce more pipeline with fewer resources.
- 75% of VC-backed fintech startups fail within a year.
- Quarterly fintech VC funding stuck at $1B-$1.4B — far below
  the $5.3B peak in Q4 2021.

### Stats the writer agent can reference (with attribution)
- Average CAC for fintech targeting SMBs: $1,450-$1,461 —
  highest of any SaaS vertical. (Source: Data-Mania 2026)
  Email use: "In a $1,400+ CAC environment, every misdirected
  lead has real unit economics impact."

- 46% of RevOps directors say their GTM processes are overly
  manual and lack automation. (Source: Forrester 2024)
  Email use: "Almost half of RevOps teams are still running
  manual triage on inbound — routing hasn't kept up."

- Companies with strong sales/marketing alignment see 38% higher
  win rates — yet only 11% of B2B companies prioritize seamless
  handoffs. (Source: ARISE GTM / Influ2 2025)
  Email use: "The handoff gap between marketing and sales
  is where CAC gets wasted."

- Multi-threaded deals (over $50K) close at 130% higher rates.
  Closed-won deals have 2x as many buyer contacts as lost deals.
  Buying groups now average 6-11 stakeholders, up to 17 in enterprise.
  (Source: Hyperbound 2025 B2B Sales Performance Benchmark)
  Email use: "The deals that close have twice as many buyer
  contacts tracked. LeanData makes multi-threading systematic."

- Reps spend 60-65% of their time on non-selling activities.
  69% of reps missed quota in 2024 even as their companies grew revenue.
  (Source: Hyperbound 2025)
  Email use: "Growing revenue while reps miss quota — that's
  an automation and routing problem, not a talent problem."

- A 5-minute delay in lead response materially reduces conversion.
  (Source: Zams 2025)
  Email use: "Speed to lead isn't a nice-to-have in a $1,400 CAC
  environment — it's the difference between a meeting and a cold lead."

### Key pain points to reference in email copy
(Prioritized by relevance to LeanData's solution)

1. Partner and channel lead chaos
   Fintech growth increasingly depends on partnerships with banks,
   resellers, and embedded finance providers. Partner leads arrive
   through unstructured paths and often miss proper L2A matching,
   routing, and SLA enforcement.
   SDR angle: "How are partner-sourced leads getting to the right rep?"

2. Compliance and audit trail gaps
   GDPR, AML, KYC, CFPB, MiCA — fintech needs to document exactly
   who received a lead, when, and under what criteria.
   Manual routing creates no audit trail.
   SDR angle: "When a regulator asks who got that lead and why —
   can you show them?"

3. Speed-to-lead failure in a high-CAC environment
   Form submission to CRM entry to manual review to rep assignment
   to sequence enrollment — no real-time orchestration.
   SDR angle: "What does your inbound flow look like from form
   submit to rep assignment today?"

4. ABM breaks during M&A activity
   Nearly half of VC-backed fintech acquisitions in 2025 were made
   by other VC-backed companies. When accounts merge, routing breaks.
   SDR angle: "When an account gets acquired, how do you handle
   the re-assignment?"

5. Multi-stakeholder buying committee mismanagement
   Average 6-11 stakeholders per deal. No systematic way to track
   buying committee engagement in CRM.
   SDR angle: "How many of your deals are single-threaded right now?"

### Persona-specific angles (from vertical intelligence research)

VP / Head of RevOps:
- Core concern: Pipeline predictability, CAC efficiency, compliance, consolidation
- Lead with: Audit trail + SLA data + partner lead routing
- Frame LeanData as connective tissue between their existing stack

Head of Partnerships:
- Core concern: Partner pipeline quality, activation speed, attribution
- Lead with: "Your partners send leads — we make sure they reach
  the right rep in under 2 minutes, with a full audit log"

CRO / VP Sales:
- Core concern: Win rate, deal velocity, efficient growth without headcount
- Lead with: Multi-threaded deals close at 130% higher rates.
  LeanData makes multi-threading systematic.

Sales Operations Manager:
- Core concern: CRM hygiene, routing accuracy, manual work reduction
- Lead with: Speed-to-lead ROI. Frame as eliminating manual triage.

Salesforce Admin / Architect:
- Core concern: Native Salesforce tools, no API limitations
- Lead with: Salesforce-native architecture — no middleware, no integration risk
