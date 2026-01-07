"""
CSM (Customer Success Manager) Coaching Crew

Analyzes retention patterns, account engagement, and expansion success to provide
personalized coaching for Customer Success Managers.
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from crewai import Agent, Task, Crew, Process

from ..config_loader import load_agents_config, load_tasks_config


class CSMCoachingCrew:
    """Crew for analyzing Customer Success Manager performance and providing coaching."""

    def __init__(self):
        self.agents_config = load_agents_config()
        self.tasks_config = load_tasks_config()

    def _build_csm_context(
        self,
        accounts_data: List[Dict[str, Any]],
        engagement_data: List[Dict[str, Any]] = None,
        transcription_samples: List[Dict[str, Any]] = None,
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

            # Calculate engagement metrics
            low_touch = [e for e in engagement_data if to_number(e.get("meeting_count")) == 0]
            high_case_accounts = [
                e for e in engagement_data if to_number(e.get("high_priority_cases")) > 0
            ]
            expansion_success = [
                e for e in engagement_data if to_number(e.get("expansion_won")) > 0
            ]

            total_expansion_value = sum(
                to_number(e.get("expansion_value")) for e in engagement_data
            )

            context += f"""
Accounts with No Meetings: {len(low_touch)}
Accounts with High Priority Cases: {len(high_case_accounts)}
Accounts with Expansion Wins: {len(expansion_success)}
Total Expansion Revenue: ${total_expansion_value:,.0f}

=== ENGAGEMENT DETAILS BY ACCOUNT ===
"""
            # Show engagement for key accounts
            for e in sorted(
                engagement_data, key=lambda x: to_number(x.get("arr")), reverse=True
            )[:10]:
                context += f"\n{e.get('account_name', 'Unknown')} (Tier: {e.get('account_tier', 'Unknown')})\n"
                context += f"  ARR: ${to_number(e.get('arr')):,.0f} | Health: {to_number(e.get('health_score')):.0f} | NPS: {e.get('nps_score', 'N/A')}\n"
                context += f"  Meetings: {to_number(e.get('meeting_count')):.0f} | Last Meeting: {e.get('last_meeting_date', 'Never')}\n"
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

    def run(
        self,
        csm_name: str,
        csm_email: str,
        accounts_data: Optional[List[Dict[str, Any]]] = None,
        engagement_data: Optional[List[Dict[str, Any]]] = None,
        transcription_samples: Optional[List[Dict[str, Any]]] = None,
        days_back: int = 180,
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
            days_back: Number of days to analyze
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
            accounts_data, engagement_data, transcription_samples
        )

        full_context = f"""=== CSM COACHING ANALYSIS ===
Customer Success Manager: {csm_name}
Email: {csm_email}
Analysis Period: Last {days_back} days

{csm_context}
"""

        if step_callback:
            step_callback("Analyzing retention patterns...")

        # Create the agents
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
        )

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
            verbose=engagement_config.get("verbose", True),
            allow_delegation=engagement_config.get("allow_delegation", False),
        )

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
        )

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
            description="""Based on retention, engagement, and expansion analysis, provide targeted CSM coaching.

PROVIDE COACHING ON:

1. **Top 3 Immediate Priorities** - What should the CSM do THIS WEEK?

2. **Account-Specific Actions**
   - At-risk accounts: Specific save plays
   - Healthy accounts: Expansion plays
   - Neglected accounts: Re-engagement plays

3. **Skill Development**
   - What skills should the CSM focus on developing?
   - Specific behaviors to start/stop/continue

4. **Time Management**
   - How should the CSM reallocate their time?
   - Which accounts need more/less attention?

5. **Metrics to Improve**
   - Which KPIs should the CSM focus on?
   - Realistic targets for the next quarter

Be SPECIFIC and reference actual accounts. Avoid generic advice.

Return your analysis in this JSON format:
{
    "summary": {
        "headline": "One-sentence summary of CSM performance",
        "overall_score": 1-10,
        "retention_health": "strong/moderate/weak",
        "expansion_performance": "exceeding/meeting/below expectations"
    },
    "strengths": ["2-3 specific strengths with evidence"],
    "improvement_areas": ["2-3 specific areas with evidence"],
    "immediate_priorities": [
        {"action": "specific action", "account": "account name", "reason": "why this matters"}
    ],
    "at_risk_accounts": [
        {"name": "account", "arr": 0, "risk_level": "high/medium", "recommended_action": "specific play"}
    ],
    "expansion_opportunities": [
        {"name": "account", "opportunity": "description", "estimated_value": 0}
    ],
    "skill_development": {
        "priority_focus": "The #1 skill to develop",
        "specific_practice": "How to develop this skill"
    },
    "time_reallocation": {
        "increase_focus": ["accounts needing more time"],
        "decrease_focus": ["accounts needing less time"]
    }
}""",
            expected_output="JSON coaching analysis with specific recommendations",
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
                    "provider": "openai",
                    "model": os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini"),
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
            "provider": "openai",
            "model": os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini"),
        }
