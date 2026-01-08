"""
CSM (Customer Success Manager) Coaching Crew

Analyzes retention patterns, account engagement, and expansion success to provide
personalized coaching for Customer Success Managers.
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from crewai import Agent, Task, Crew, Process, LLM

from ..config_loader import load_agents_config, load_tasks_config
from ..ai_settings_helper import create_llm_for_user, DEFAULT_AI_SETTINGS


class CSMCoachingCrew:
    """Crew for analyzing Customer Success Manager performance and providing coaching.

    Uses tiered model strategy for optimal cost/speed/quality:
    - Fast model (GPT-4o-mini): Data analysis agents (retention, engagement, expansion)
    - Quality model (GPT-4o or user-configured): Coach agent (final synthesis)
    """

    def __init__(self, user_id: Optional[str] = None):
        """Initialize the crew with tiered model strategy.

        Args:
            user_id: Optional user ID to fetch management-level AI settings.
                    If not provided, uses default settings.
        """
        self.user_id = user_id

        # Fast model for analysis agents (data crunching, pattern matching)
        # GPT-4o-mini is fast, cheap, and great for structured analysis
        self.fast_llm = LLM(
            model="gpt-4o-mini",
            api_key=os.environ.get("OPENAI_API_KEY"),
        )

        # Quality model for coach agent (synthesis, strategic recommendations)
        # Uses user-configured model or defaults to GPT-4o for best reasoning
        if user_id:
            self.quality_llm = create_llm_for_user(user_id)
        else:
            self.quality_llm = LLM(
                model=os.environ.get("OPENAI_MODEL_NAME", "gpt-4o"),
                api_key=os.environ.get("OPENAI_API_KEY"),
            )

        # Keep self.llm for backward compatibility
        self.llm = self.quality_llm

        self.agents_config = load_agents_config()
        self.tasks_config = load_tasks_config()

        # Log the tiered model strategy
        print(f"[CSM Coaching] Using tiered models: fast={self.fast_llm.model}, quality={self.quality_llm.model}")

    def _build_csm_context(
        self,
        accounts_data: List[Dict[str, Any]],
        engagement_data: List[Dict[str, Any]] = None,
        transcription_samples: List[Dict[str, Any]] = None,
        calendar_connected: bool = False,
    ) -> str:
        """Build context string from CSM account data."""
        if not accounts_data:
            return "No account data available for analysis."

        def to_number(val, default=0):
            """Safely convert a value to a number."""
            if val is None:
                return default
            try:
                return float(val)
            except (TypeError, ValueError):
                return default

        # Portfolio metrics
        total_accounts = len(accounts_data)
        total_arr = sum(to_number(a.get("arr")) for a in accounts_data)
        avg_health = (
            sum(to_number(a.get("health_score")) for a in accounts_data) / total_accounts
            if total_accounts
            else 0
        )

        # Health distribution
        healthy = [a for a in accounts_data if to_number(a.get("health_score")) >= 70]
        at_risk = [
            a for a in accounts_data if 40 <= to_number(a.get("health_score")) < 70
        ]
        critical = [a for a in accounts_data if to_number(a.get("health_score")) < 40]

        # Upcoming renewals (next 90 days)
        now = datetime.now()
        ninety_days = now + timedelta(days=90)
        upcoming_renewals = [
            a
            for a in accounts_data
            if a.get("renewal_date")
            and now.isoformat()[:10]
            <= a.get("renewal_date", "")
            <= ninety_days.isoformat()[:10]
        ]

        context = f"""=== CSM PORTFOLIO METRICS ===
Total Accounts: {total_accounts}
Total ARR Under Management: ${total_arr:,.0f}
Average Health Score: {avg_health:.1f}/100

=== HEALTH DISTRIBUTION ===
Healthy (70+): {len(healthy)} accounts
At Risk (40-69): {len(at_risk)} accounts
Critical (<40): {len(critical)} accounts

=== UPCOMING RENEWALS (Next 90 Days) ===
{len(upcoming_renewals)} renewals upcoming
"""
        for a in sorted(upcoming_renewals, key=lambda x: x.get("renewal_date", ""))[:5]:
            arr = to_number(a.get("arr"))
            health = to_number(a.get("health_score"))
            context += f"  {a.get('name', 'Unknown')}: ${arr:,.0f} ARR, Health: {health:.0f}\n"

        # Add engagement data if available
        if engagement_data:
            context += "\n=== ACCOUNT ENGAGEMENT ANALYSIS ===\n"

            # Calendar connection warning
            if not calendar_connected:
                context += """
⚠️ CALENDAR NOT CONNECTED
The CSM has not connected their Google Calendar. Upcoming meeting data is NOT available.
- Only PAST meetings from Avoma call recordings are included
- Do NOT flag "no upcoming calls" as a risk - we simply don't have visibility
- Recommend connecting Google Calendar as an action item for better engagement tracking

"""

            # Calculate engagement metrics
            low_touch = [e for e in engagement_data if to_number(e.get("meeting_count")) == 0]
            high_case_accounts = [
                e for e in engagement_data if to_number(e.get("high_priority_cases")) > 0
            ]
            expansion_success = [
                e for e in engagement_data if to_number(e.get("expansion_won")) > 0
            ]
            accounts_with_upcoming = [e for e in engagement_data if to_number(e.get("upcoming_calls_count")) > 0]

            total_expansion_value = sum(
                to_number(e.get("expansion_value")) for e in engagement_data
            )

            context += f"""
Accounts with No Past Meetings (Avoma): {len(low_touch)}
Accounts with High Priority Cases: {len(high_case_accounts)}
Accounts with Expansion Wins: {len(expansion_success)}
Total Expansion Revenue: ${total_expansion_value:,.0f}
"""
            if calendar_connected:
                context += f"Accounts with Upcoming Calls Scheduled: {len(accounts_with_upcoming)}\n"

            context += "\n=== ENGAGEMENT DETAILS BY ACCOUNT ===\n"

            # Show engagement for key accounts
            for e in sorted(
                engagement_data, key=lambda x: to_number(x.get("arr")), reverse=True
            )[:10]:
                context += f"\n{e.get('account_name', 'Unknown')} (Tier: {e.get('account_tier', 'Unknown')})\n"
                context += f"  ARR: ${to_number(e.get('arr')):,.0f} | Health: {to_number(e.get('health_score')):.0f} | NPS: {e.get('nps_score', 'N/A')}\n"

                # Past meetings from Avoma
                days_since = e.get('days_since_last_meeting')
                days_str = f" ({days_since} days ago)" if days_since is not None else ""
                context += f"  Past Meetings (Avoma): {to_number(e.get('meeting_count')):.0f} | Last Meeting: {e.get('last_meeting_date', 'Never')}{days_str}\n"

                # Upcoming calls (only if calendar connected)
                if calendar_connected:
                    upcoming_count = to_number(e.get('upcoming_calls_count'))
                    next_call = e.get('next_call_date', 'None scheduled')
                    context += f"  Upcoming Calls: {upcoming_count:.0f} | Next Call: {next_call}\n"

                context += f"  Open Cases: {to_number(e.get('open_cases')):.0f} | High Priority: {to_number(e.get('high_priority_cases')):.0f}\n"
                context += f"  Expansion Opps: {to_number(e.get('expansion_opportunities')):.0f} | Won: ${to_number(e.get('expansion_value')):,.0f}\n"

        # Add transcript samples if available
        if transcription_samples:
            context += "\n=== RECENT CALL SAMPLES (For Communication Analysis) ===\n"
            for sample in transcription_samples[:3]:
                context += f"\n{sample.get('account_name', 'Unknown')} (Health: {sample.get('health_score', 'Unknown')})\n"
                transcript = sample.get("transcript", {})
                context += f"  Meeting: {transcript.get('subject', 'Unknown')} ({transcript.get('date', 'Unknown')})\n"
                text = transcript.get("text", "")[:1500]
                if text:
                    context += f"  Excerpt: {text}...\n"

        return context

    def _format_semantic_insights(self, semantic_insights: Dict[str, List[Dict[str, Any]]]) -> str:
        """Format semantic insights from vector search into coaching context."""
        if not semantic_insights:
            return ""

        sections = []

        # Map signal types to human-readable descriptions
        signal_descriptions = {
            "churn_signals": ("🚨 CHURN RISK SIGNALS", "Concerns, frustrations, or dissatisfaction detected in conversations"),
            "expansion_signals": ("📈 EXPANSION OPPORTUNITIES", "Growth interest or additional use cases mentioned"),
            "product_feedback": ("💡 PRODUCT FEEDBACK", "Feature requests and improvement suggestions"),
            "competitive_mentions": ("⚔️ COMPETITIVE INTELLIGENCE", "Alternative solutions or vendor comparisons discussed"),
            "success_indicators": ("✅ SUCCESS SIGNALS", "Positive outcomes and satisfaction expressed"),
            "stakeholder_changes": ("👥 STAKEHOLDER CHANGES", "Organizational changes or key decision makers mentioned"),
        }

        for signal_type, insights in semantic_insights.items():
            if not insights:
                continue

            title, description = signal_descriptions.get(
                signal_type, (signal_type.upper(), "Relevant conversation snippets")
            )

            section_parts = [f"\n{title}", f"({description})"]

            # Group by account
            by_account = {}
            for insight in insights:
                account = insight.get("account_name", "Unknown")
                if account not in by_account:
                    by_account[account] = []
                by_account[account].append(insight)

            for account, account_insights in by_account.items():
                section_parts.append(f"\n  {account}:")
                for i, insight in enumerate(account_insights[:3], 1):  # Max 3 per account
                    content = insight.get("content", "")[:800]  # Limit snippet size
                    similarity = insight.get("similarity", 0)
                    section_parts.append(f"    [{i}] (relevance: {similarity:.0%}) {content}")

            sections.append("\n".join(section_parts))

        if not sections:
            return ""

        return "\n\n=== SEMANTIC INSIGHTS FROM CONVERSATION ANALYSIS ===\n" + "\n".join(sections)

    def run(
        self,
        csm_name: str,
        csm_email: str,
        accounts_data: Optional[List[Dict[str, Any]]] = None,
        engagement_data: Optional[List[Dict[str, Any]]] = None,
        transcription_samples: Optional[List[Dict[str, Any]]] = None,
        semantic_insights: Optional[Dict[str, List[Dict[str, Any]]]] = None,  # NEW
        days_back: int = 180,
        calendar_connected: bool = False,
        step_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        Run the CSM coaching crew analysis.

        Args:
            csm_name: Name of the Customer Success Manager
            csm_email: Email of the Customer Success Manager
            accounts_data: Pre-fetched account data
            engagement_data: Pre-fetched engagement data
            transcription_samples: Pre-fetched transcription samples
            semantic_insights: Structured signals from vector search (churn, expansion, etc.)
            days_back: Number of days to analyze
            calendar_connected: Whether the CSM has connected their calendar
            step_callback: Optional callback for progress updates

        Returns:
            Coaching analysis results
        """
        if not accounts_data:
            return {
                "success": False,
                "error": "No account data provided for analysis",
                "result": "Unable to provide coaching analysis: No accounts found for this CSM. Please ensure the CSM has accounts assigned in Salesforce.",
                "csm_name": csm_name,
                "csm_email": csm_email,
                "accounts_analyzed": 0,
            }

        # Build context
        csm_context = self._build_csm_context(
            accounts_data, engagement_data, transcription_samples, calendar_connected
        )

        # Add semantic insights if available
        semantic_context = self._format_semantic_insights(semantic_insights) if semantic_insights else ""

        # Log what we received
        if semantic_insights:
            total_insights = sum(len(v) for v in semantic_insights.values())
            print(f"[CSM Coaching] Received {total_insights} semantic insights across {len([k for k, v in semantic_insights.items() if v])} categories")
        else:
            print("[CSM Coaching] No semantic insights provided, using transcription samples if available")

        full_context = f"""=== CSM COACHING ANALYSIS ===
Customer Success Manager: {csm_name}
Email: {csm_email}
Analysis Period: Last {days_back} days

{csm_context}
{semantic_context}
"""

        if step_callback:
            step_callback("Analyzing retention patterns...")

        # Create the agents with tiered model strategy:
        # - Analysis agents use fast_llm (GPT-4o-mini) for speed and cost efficiency
        # - Coach agent uses quality_llm (GPT-4o) for best reasoning and output quality

        # ANALYSIS AGENT 1: Retention Analyst (uses fast model)
        retention_config = self.agents_config.get("retention_analyst", {})
        retention_analyst = Agent(
            role=retention_config.get("role", "Retention Analyst"),
            goal=retention_config.get(
                "goal",
                "Analyze account health patterns, identify churn risks, and assess retention effectiveness",
            ),
            backstory=retention_config.get(
                "backstory",
                "You are an expert in customer retention who can identify early warning signs and patterns that predict churn or renewal success.",
            ),
            verbose=retention_config.get("verbose", True),
            allow_delegation=retention_config.get("allow_delegation", False),
            llm=self.fast_llm,  # Fast model for data analysis
        )

        # ANALYSIS AGENT 2: Engagement Specialist (uses fast model)
        engagement_config = self.agents_config.get("engagement_specialist", {})
        engagement_specialist = Agent(
            role=engagement_config.get("role", "Engagement Specialist"),
            goal=engagement_config.get(
                "goal",
                "Evaluate customer engagement quality, meeting cadence, and communication effectiveness",
            ),
            backstory=engagement_config.get(
                "backstory",
                "You analyze customer touchpoints and engagement patterns to identify accounts that need more attention and those being over-serviced.",
            ),
            verbose=retention_config.get("verbose", True),
            allow_delegation=retention_config.get("allow_delegation", False),
            llm=self.fast_llm,  # Fast model for data analysis
        )

        # ANALYSIS AGENT 3: Expansion Strategist (uses fast model)
        expansion_config = self.agents_config.get("expansion_strategist", {})
        expansion_strategist = Agent(
            role=expansion_config.get("role", "Expansion Strategist"),
            goal=expansion_config.get(
                "goal",
                "Identify expansion opportunities and assess the CSM's ability to drive growth within accounts",
            ),
            backstory=expansion_config.get(
                "backstory",
                "You specialize in identifying upsell and cross-sell opportunities and coaching CSMs on how to position expansion conversations.",
            ),
            verbose=expansion_config.get("verbose", True),
            allow_delegation=expansion_config.get("allow_delegation", False),
            llm=self.fast_llm,  # Fast model for opportunity identification
        )

        # SYNTHESIS AGENT: CSM Coach (uses quality model for best output)
        coach_config = self.agents_config.get("csm_coach", {})
        coach = Agent(
            role=coach_config.get("role", "CSM Coach"),
            goal=coach_config.get(
                "goal",
                "Provide actionable coaching recommendations to improve retention, engagement, and expansion outcomes",
            ),
            backstory=coach_config.get(
                "backstory",
                "You are an experienced CS leader who has coached hundreds of CSMs. You provide direct, specific, and actionable feedback.",
            ),
            verbose=coach_config.get("verbose", True),
            allow_delegation=coach_config.get("allow_delegation", False),
            llm=self.quality_llm,  # Quality model for strategic synthesis
        )

        # Create tasks
        retention_task = Task(
            description=f"""{full_context}

ANALYZE RETENTION PATTERNS:

1. **Health Score Distribution**
   - What percentage of accounts are healthy vs at-risk?
   - Are there patterns in what causes low health scores?
   - How does this compare to typical benchmarks (aim for 70%+ healthy)?

2. **Churn Risk Assessment**
   - Which specific accounts are at highest churn risk and why?
   - Are there early warning signs being missed?
   - What is the ARR at risk?

3. **Renewal Pipeline**
   - Are upcoming renewals well-positioned?
   - Which renewals need immediate attention?
   - Is the CSM proactively preparing for renewals?

4. **Historical Patterns**
   - Any patterns in accounts that have churned or downgraded?
   - What behaviors correlate with successful renewals?

Provide specific account examples and ARR impact for each finding.""",
            expected_output="Detailed retention analysis with specific accounts, ARR at risk, and pattern identification",
            agent=retention_analyst,
        )

        if step_callback:
            step_callback("Analyzing engagement patterns...")

        engagement_task = Task(
            description="""ANALYZE ENGAGEMENT PATTERNS:

1. **Meeting Cadence**
   - Are high-value/at-risk accounts getting appropriate touch frequency?
   - Which accounts are being under-touched? Over-touched?
   - Is there a correlation between engagement and health scores?

2. **Support Case Patterns**
   - Are there accounts with recurring issues that need CSM intervention?
   - Is the CSM aware of high-priority cases in their accounts?
   - Are cases being resolved or escalating?

3. **Communication Quality** (from transcripts if available)
   - Is the CSM driving value-focused conversations?
   - Are QBRs/EBRs happening for strategic accounts?
   - Is there evidence of business outcome discussions?

4. **Time Allocation**
   - Is time being spent on the right accounts (tier-appropriate)?
   - Are there accounts that need more/less attention?

Provide specific recommendations for engagement changes.""",
            expected_output="Engagement analysis with specific account recommendations for improved touch patterns",
            agent=engagement_specialist,
        )

        if step_callback:
            step_callback("Analyzing expansion opportunities...")

        expansion_task = Task(
            description="""ANALYZE EXPANSION PERFORMANCE:

1. **Expansion Success Rate**
   - What percentage of expansion opportunities are converting?
   - What is the total expansion revenue generated?
   - Are there patterns in successful vs unsuccessful expansions?

2. **Untapped Opportunities**
   - Which healthy accounts have expansion potential?
   - Are there usage patterns suggesting need for upgrades?
   - What expansion conversations should the CSM be having?

3. **Expansion Readiness**
   - Are accounts being properly positioned for expansion?
   - Is value being demonstrated before asking for more?
   - Is the CSM comfortable with commercial conversations?

4. **NPS/Advocacy**
   - Are high NPS accounts being leveraged for referrals/case studies?
   - What is the relationship between NPS and expansion success?

Identify specific expansion opportunities with estimated potential value.""",
            expected_output="Expansion opportunity analysis with specific account recommendations and estimated value",
            agent=expansion_strategist,
        )

        if step_callback:
            step_callback("Generating coaching recommendations...")

        coaching_task = Task(
            description="""Based on retention, engagement, and expansion analysis, provide DETAILED, ACTIONABLE CSM coaching.

You are a McKinsey-level CS strategist. Your recommendations must be:
- SPECIFIC (name accounts, people, dates, dollar amounts)
- ACTIONABLE (clear next steps, not vague advice)
- EVIDENCE-BASED (reference actual data from the analysis)
- PRIORITIZED (what to do first, second, third)
- QUANTIFIED (ARR at risk, potential expansion value, etc.)

REQUIRED SECTIONS:

1. **EXECUTIVE SUMMARY**
   - One-paragraph diagnosis of portfolio health
   - Total ARR at risk with specific accounts
   - Total expansion opportunity with specific accounts
   - The single most important thing to fix

2. **THIS WEEK'S PRIORITIES** (Max 5, ranked by ARR impact)
   For each priority:
   - Specific account and contact to reach
   - Exact action to take (call, email, meeting request)
   - What to say/discuss (specific talking points from transcript insights)
   - Expected outcome
   - ARR at stake

3. **ACCOUNT-BY-ACCOUNT PLAYBOOKS** (Top 10 accounts by ARR)
   For each account provide:
   - Current status (health score, days since contact, open issues)
   - Primary risk or opportunity
   - Recommended play (save play, expansion play, maintain play)
   - Specific next step with timeline
   - Key stakeholder to engage
   - Talking points based on recent conversations

4. **CHURN PREVENTION PLAYS**
   For each at-risk account:
   - Warning signs detected (from transcript analysis)
   - Specific quote or signal that triggered concern
   - Recommended save play with step-by-step actions
   - Escalation recommendation (when to involve leadership)
   - Win-back probability estimate

5. **EXPANSION OPPORTUNITIES**
   For each expansion candidate:
   - Current ARR and expansion potential
   - Signals detected (usage, sentiment, stated needs)
   - Recommended expansion motion
   - Pricing/packaging suggestion
   - Best time to approach and why

6. **SKILL DEVELOPMENT**
   - Top 3 skill gaps identified with evidence
   - Specific behaviors to START (with examples)
   - Specific behaviors to STOP (with examples)
   - Recommended training or coaching focus

7. **TIME ALLOCATION RECOMMENDATION**
   - Accounts getting too much attention (reduce)
   - Accounts getting too little attention (increase)
   - Suggested weekly cadence by account tier
   - Time savings opportunities

8. **30-60-90 DAY ROADMAP**
   - Week 1-2: Critical saves and quick wins
   - Week 3-4: Expansion conversations to initiate
   - Month 2: Relationship deepening plays
   - Month 3: Strategic reviews and renewals prep

Return your analysis in this JSON format:
{
    "executive_summary": {
        "headline": "One-sentence performance summary",
        "overall_score": 1-10,
        "portfolio_health": "critical/concerning/stable/healthy/thriving",
        "total_arr_at_risk": 0,
        "total_expansion_potential": 0,
        "most_critical_issue": "The #1 thing to address immediately"
    },
    "this_week_priorities": [
        {
            "priority": 1,
            "account": "account name",
            "contact": "person to reach",
            "action": "specific action",
            "talking_points": ["point 1", "point 2"],
            "arr_at_stake": 0,
            "deadline": "by when"
        }
    ],
    "account_playbooks": [
        {
            "account": "name",
            "arr": 0,
            "health_score": 0,
            "days_since_contact": 0,
            "status": "at-risk/stable/growth-ready",
            "primary_issue_or_opportunity": "description",
            "recommended_play": "save/expand/maintain/re-engage",
            "next_step": "specific action",
            "timeline": "by when",
            "key_stakeholder": "name and role",
            "talking_points": ["point 1", "point 2"]
        }
    ],
    "churn_prevention": [
        {
            "account": "name",
            "arr": 0,
            "warning_signs": ["sign 1", "sign 2"],
            "customer_quote": "actual quote or paraphrase from transcripts",
            "save_play": ["step 1", "step 2", "step 3"],
            "escalation_needed": true/false,
            "escalation_reason": "why leadership should be involved",
            "save_probability": "high/medium/low"
        }
    ],
    "expansion_opportunities": [
        {
            "account": "name",
            "current_arr": 0,
            "expansion_potential": 0,
            "signals": ["signal 1", "signal 2"],
            "recommended_motion": "upsell/cross-sell/land-expand",
            "approach": "how to position",
            "timing": "when to approach",
            "success_probability": "high/medium/low"
        }
    ],
    "skill_development": {
        "gaps_identified": [
            {"skill": "skill name", "evidence": "what shows this gap", "impact": "how it hurts performance"}
        ],
        "start_doing": [
            {"behavior": "what to start", "example": "specific example", "expected_impact": "what improves"}
        ],
        "stop_doing": [
            {"behavior": "what to stop", "example": "specific example", "expected_impact": "what improves"}
        ],
        "training_recommendation": "specific training or coaching focus"
    },
    "time_allocation": {
        "reduce_attention": [{"account": "name", "current_state": "why over-served", "recommendation": "new cadence"}],
        "increase_attention": [{"account": "name", "current_state": "why under-served", "recommendation": "new cadence"}],
        "tier_cadence": {
            "enterprise": "recommended touch frequency",
            "mid_market": "recommended touch frequency",
            "smb": "recommended touch frequency"
        }
    },
    "roadmap": {
        "week_1_2": [{"action": "what to do", "accounts": ["account1", "account2"], "expected_outcome": "result"}],
        "week_3_4": [{"action": "what to do", "accounts": ["account1", "account2"], "expected_outcome": "result"}],
        "month_2": [{"action": "what to do", "accounts": ["account1", "account2"], "expected_outcome": "result"}],
        "month_3": [{"action": "what to do", "accounts": ["account1", "account2"], "expected_outcome": "result"}]
    },
    "key_metrics_to_track": [
        {"metric": "metric name", "current": "current value", "target": "target value", "timeline": "achieve by when"}
    ]
}""",
            expected_output="Comprehensive JSON coaching analysis with specific, actionable recommendations for each account",
            agent=coach,
            context=[retention_task, engagement_task, expansion_task],
        )

        # Create and run the crew
        crew = Crew(
            agents=[retention_analyst, engagement_specialist, expansion_strategist, coach],
            tasks=[retention_task, engagement_task, expansion_task, coaching_task],
            process=Process.sequential,
            verbose=True,
        )

        result = crew.kickoff()
        result_text = str(result)

        # Get actual model info from LLM
        model_name = getattr(self.llm, 'model', os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini"))
        provider = "openai"
        if "claude" in model_name.lower() or "anthropic" in model_name.lower():
            provider = "anthropic"
        elif "gemini" in model_name.lower():
            provider = "google"

        # Try to extract JSON from the result
        try:
            import re

            json_match = re.search(r"\{[\s\S]*\}", result_text)
            if json_match:
                parsed_result = json.loads(json_match.group())
                return {
                    "success": True,
                    "result": parsed_result,
                    "csm_name": csm_name,
                    "csm_email": csm_email,
                    "accounts_analyzed": len(accounts_data) if accounts_data else 0,
                    "days_back": days_back,
                    "provider": provider,
                    "model": model_name,
                }
        except json.JSONDecodeError:
            pass

        # Return raw result if JSON parsing fails
        return {
            "success": True,
            "result": result_text,
            "csm_name": csm_name,
            "csm_email": csm_email,
            "accounts_analyzed": len(accounts_data) if accounts_data else 0,
            "days_back": days_back,
            "raw_response": True,
            "provider": provider,
            "model": model_name,
        }
