"""
Implementation Consultant (PM) Coaching Crew

Analyzes an Implementation Consultant's project portfolio to provide personalized
coaching on on-time delivery rates, customer sentiment trends, escalation patterns,
and communication effectiveness.
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from crewai import Agent, Task, Crew, Process, LLM
from supabase import create_client, Client

from ..config_loader import load_agents_config, load_tasks_config
from ..ai_settings_helper import create_llm_for_user, DEFAULT_AI_SETTINGS


class PMCoachingCrew:
    """Crew for analyzing Implementation Consultant performance and providing coaching."""

    def __init__(self, user_id: Optional[str] = None):
        """Initialize the crew with optional user-specific AI settings.

        Args:
            user_id: Optional user ID to fetch management-level AI settings.
                    If not provided, uses default settings.
        """
        self.user_id = user_id
        if user_id:
            self.llm = create_llm_for_user(user_id)
        else:
            self.llm = LLM(
                model=os.environ.get("OPENAI_MODEL_NAME", DEFAULT_AI_SETTINGS["model_id"]),
                api_key=os.environ.get("OPENAI_API_KEY"),
            )
        self.agents_config = load_agents_config()
        self.tasks_config = load_tasks_config()
        self.supabase = self._get_supabase_client()

    def _get_supabase_client(self) -> Optional[Client]:
        """Get Supabase client for database access."""
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if url and key:
            return create_client(url, key)
        return None

    def _build_pm_context(
        self,
        projects_data: List[Dict[str, Any]],
        delivery_metrics: Dict[str, Any] = None,
        sentiment_data: List[Dict[str, Any]] = None,
        transcription_samples: List[Dict[str, Any]] = None,
        escalation_data: List[Dict[str, Any]] = None,
        agenda_metrics: Dict[str, Any] = None,
    ) -> str:
        """Build context string from Implementation Consultant portfolio data."""

        context = "=== IMPLEMENTATION CONSULTANT PORTFOLIO OVERVIEW ===\n"

        if delivery_metrics:
            # Calculate on-time rate only from projects with actual go-live dates
            on_time_projects = delivery_metrics.get("on_time_projects", 0)
            delayed_projects = delivery_metrics.get("delayed_projects", 0)
            projects_with_dates = on_time_projects + delayed_projects
            missing_dates = delivery_metrics.get("completed_missing_dates", 0)

            on_time_rate = 0
            if projects_with_dates > 0:
                on_time_rate = (on_time_projects / projects_with_dates) * 100

            active_with_target = delivery_metrics.get("active_with_target_date", 0)
            active_missing_target = delivery_metrics.get("active_missing_target_date", 0)
            active_total = delivery_metrics.get("active_projects", 0)

            context += f"""
Total Projects (Portfolio): {delivery_metrics.get('total_projects', 0)}
Completed: {delivery_metrics.get('completed_projects', 0)}
Active: {active_total}
On Hold: {delivery_metrics.get('on_hold_projects', 0)}

=== ACTIVE PROJECT TARGET DATES ===
Active Projects with PS Forecasted Live Date: {active_with_target}
Active Projects Missing Target Date: {active_missing_target}
NOTE: PS Forecasted Live Date is the target date ICs commit to customers

=== DELIVERY PERFORMANCE (Completed Projects) ===
On-Time Deliveries: {on_time_projects}
Delayed: {delayed_projects}
On-Time Rate: {on_time_rate:.1f}% (based on {projects_with_dates} completed projects with actual go-live dates)
NOTE: {missing_dates} completed projects missing actual go-live date data (cannot calculate on-time rate)
Average Completion Rate: {delivery_metrics.get('avg_completion_rate', 0):.1f}%

=== BUDGET PERFORMANCE ===
Projects Over Budget: {delivery_metrics.get('projects_over_budget', 0)}
Projects Under Budget: {delivery_metrics.get('projects_under_budget', 0)}
"""

        # Project details
        if projects_data:
            context += "\n=== CURRENT PROJECT PORTFOLIO ===\n"

            # Helper to get field from either camelCase or snake_case (frontend sends camelCase)
            def get_field(p, camel_case, snake_case):
                return p.get(camel_case) if p.get(camel_case) is not None else p.get(snake_case)

            # Helper to get target date - PS Forecasted Live Date is the primary field
            def get_target_date(p):
                return get_field(p, "psForecastedLiveDate", "ps_forecasted_live_date") or get_field(p, "targetGoLiveDate", "target_go_live_date")

            # Helper for case-insensitive status matching
            def status_lower(s):
                return (s or "").lower()

            def get_status(p):
                return get_field(p, "projectStatus", "project_status")

            # Active projects (case-insensitive partial match)
            # Match: Active, In Progress, Live, In Development, Confirmed
            def is_active_status(s):
                sl = status_lower(s)
                return any(term in sl for term in ["active", "progress", "live", "development", "confirmed"])

            active = [p for p in projects_data if is_active_status(get_status(p))]
            if active:
                context += "\n-- Active Projects --\n"
                for p in sorted(
                    active, key=lambda x: get_target_date(x) or ""
                )[:10]:
                    completion = get_field(p, "completionPercentage", "completion_percentage") or 0
                    target_date = get_target_date(p)
                    context += f"\n{get_field(p, 'projectName', 'project_name') or 'Unknown'}\n"
                    context += f"  Account: {get_field(p, 'accountName', 'account_name') or 'Unknown'}\n"
                    context += f"  PS Forecasted Live Date: {target_date or 'Not set'}\n"
                    context += f"  Completion: {completion:.0f}%\n"
                    budget = get_field(p, "budget", "budget")
                    budget_used = get_field(p, "budgetUsed", "budget_used")
                    if budget and budget_used:
                        budget_pct = (budget_used / budget) * 100
                        context += f"  Budget Used: {budget_pct:.0f}%\n"

            # On hold projects (case-insensitive partial match)
            on_hold = [p for p in projects_data if "hold" in status_lower(get_status(p))]
            if on_hold:
                context += "\n-- On Hold Projects --\n"
                for p in on_hold[:5]:
                    context += f"  {get_field(p, 'projectName', 'project_name') or 'Unknown'} ({get_field(p, 'accountName', 'account_name') or 'Unknown'})\n"

            # Recently completed (case-insensitive partial match)
            completed = [
                p
                for p in projects_data
                if "complete" in status_lower(get_status(p)) or "closed" in status_lower(get_status(p)) or "done" in status_lower(get_status(p))
            ]
            if completed:
                context += f"\n-- Recently Completed ({len(completed)} total) --\n"
                for p in sorted(
                    completed, key=lambda x: x.get("updated_at") or x.get("lastSyncedAt") or "", reverse=True
                )[:5]:
                    context += f"  {get_field(p, 'projectName', 'project_name') or 'Unknown'}\n"

        # Sentiment data
        context += "\n=== CUSTOMER SENTIMENT SCORES ===\n"
        if sentiment_data and len(sentiment_data) > 0:
            avg_pm_score = (
                sum(s.get("pm_effectiveness_score", 0) or 0 for s in sentiment_data)
                / len(sentiment_data)
            )
            avg_customer_score = (
                sum(s.get("customer_reception_score", 0) or 0 for s in sentiment_data)
                / len(sentiment_data)
            )

            context += f"""
Average IC Effectiveness Score: {avg_pm_score:.1f}/10
Average Customer Reception Score: {avg_customer_score:.1f}/10

Project-Level Sentiment:
"""
            for s in sorted(
                sentiment_data, key=lambda x: x.get("overall_score", 0) or 0
            )[:10]:
                context += f"  {s.get('project_id', 'Unknown')}: IC={s.get('pm_effectiveness_score', 'N/A')}, Customer={s.get('customer_reception_score', 'N/A')}\n"
        else:
            context += """
NO SENTIMENT DATA AVAILABLE
NOTE: Project sentiment analysis has not been run for any of this IC's projects.
Do NOT report sentiment scores as 0 or low - sentiment data simply does not exist yet.
To get sentiment data, run Project Sentiment Analysis on individual projects first.
"""

        # Escalation data
        context += "\n=== ESCALATION PATTERNS ===\n"
        if escalation_data and len(escalation_data) > 0:
            total_cases = sum(e.get("total_cases", 0) for e in escalation_data)
            high_priority = sum(e.get("high_priority", 0) for e in escalation_data)

            context += f"""
Total Support Cases Across Projects: {total_cases}
High Priority Cases: {high_priority}

Projects with Escalations:
"""
            for e in sorted(
                escalation_data, key=lambda x: x.get("high_priority", 0), reverse=True
            )[:10]:
                if e.get("total_cases", 0) > 0:
                    context += f"  {e.get('project_name', 'Unknown')}: {e.get('open_cases', 0)} open, {e.get('high_priority', 0)} high priority\n"
        else:
            context += "No escalation/support case data available for these projects.\n"

        # Transcript samples
        context += "\n=== CUSTOMER COMMUNICATION SAMPLES ===\n"
        if transcription_samples and len(transcription_samples) > 0:
            for sample in transcription_samples[:3]:
                context += f"\n{sample.get('project_name', 'Unknown')} ({sample.get('project_status', 'Unknown')})\n"
                for t in sample.get("transcripts", [])[:1]:
                    context += f"  Meeting: {t.get('subject', 'Unknown')} ({t.get('date', 'Unknown')})\n"
                    text = (t.get("text", "") or "")[:1500]
                    if text:
                        context += f"  Excerpt: {text}...\n"
        else:
            context += "No meeting transcription data available for these projects.\n"
            context += "NOTE: Transcriptions sync when users visit project detail pages in LUCI.\n"

        # Agenda completion metrics
        context += "\n=== CALL AGENDA & FOLLOW-UP PATTERNS ===\n"
        if agenda_metrics and agenda_metrics.get("total_agendas", 0) > 0:
            total_agendas = agenda_metrics.get("total_agendas", 0)
            agendas_with_items = agenda_metrics.get("agendas_with_items", 0)
            total_items = agenda_metrics.get("total_items", 0)
            completed_items = agenda_metrics.get("completed_items", 0)
            incomplete_items = agenda_metrics.get("incomplete_items", 0)
            late_items = agenda_metrics.get("late_items", 0)
            completion_rate = agenda_metrics.get("completion_rate", 0)
            avg_items = agenda_metrics.get("avg_items_per_agenda", 0)
            projects_with_agendas = agenda_metrics.get("projects_with_agendas", 0)

            context += f"""
Call Agendas Created: {total_agendas}
Agendas with Action Items: {agendas_with_items}
Projects Using Call Planner: {projects_with_agendas}

=== AGENDA ITEM COMPLETION ===
Total Action Items Tracked: {total_items}
Completed: {completed_items}
Incomplete/Pending: {incomplete_items}
Late (Carried Forward): {late_items}
Completion Rate: {completion_rate:.1f}%
Average Items per Agenda: {avg_items:.1f}

INTERPRETATION GUIDE:
- Completion Rate above 75%: Good follow-through on commitments
- Completion Rate 50-75%: Room for improvement in closing action items
- Completion Rate below 50%: Significant follow-up gap - needs coaching
- Late Items > 3: Pattern of carrying forward incomplete work
- Avg Items > 8: May be overloading agendas, consider prioritization
"""
            # Add assessment based on metrics
            if completion_rate >= 75:
                context += "\nASSESSMENT: Strong agenda discipline - completing commitments consistently.\n"
            elif completion_rate >= 50:
                context += "\nASSESSMENT: Moderate follow-through - some action items slipping through.\n"
            else:
                context += "\nASSESSMENT: Follow-up patterns need attention - many items not completed.\n"

            if late_items > 3:
                context += f"WARNING: {late_items} late items suggest pattern of deferred commitments.\n"
        else:
            context += """
NO CALL AGENDA DATA AVAILABLE
NOTE: This IC has not used the Call Planner feature yet or has no tracked agendas.
The Call Planner helps track commitments made during customer calls.
Consider recommending adoption of the Call Planner for better follow-up tracking.
"""

        return context

    def run(
        self,
        pm_name: str,
        pm_email: str,
        salesforce_owner_id: Optional[str] = None,
        projects_data: Optional[List[Dict[str, Any]]] = None,
        delivery_metrics: Optional[Dict[str, Any]] = None,
        sentiment_data: Optional[List[Dict[str, Any]]] = None,
        transcription_samples: Optional[List[Dict[str, Any]]] = None,
        escalation_data: Optional[List[Dict[str, Any]]] = None,
        agenda_metrics: Optional[Dict[str, Any]] = None,
        days_back: int = 365,
        step_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        Run the Implementation Consultant coaching crew analysis.

        Args:
            pm_name: Name of the Implementation Consultant
            pm_email: Email of the Implementation Consultant
            salesforce_owner_id: Salesforce Owner ID
            projects_data: Pre-fetched project data
            delivery_metrics: Pre-calculated delivery metrics
            sentiment_data: Pre-fetched sentiment data
            transcription_samples: Pre-fetched transcription samples
            escalation_data: Pre-fetched escalation data
            days_back: Number of days to analyze
            step_callback: Optional callback for progress updates

        Returns:
            Coaching analysis results
        """
        if not projects_data:
            return {
                "success": False,
                "error": "No project data provided for analysis",
                "pm_name": pm_name,
                "pm_email": pm_email,
            }

        # Build context
        pm_context = self._build_pm_context(
            projects_data,
            delivery_metrics,
            sentiment_data,
            transcription_samples,
            escalation_data,
            agenda_metrics,
        )

        full_context = f"""=== IC COACHING ANALYSIS ===
Implementation Consultant: {pm_name}
Email: {pm_email}
Analysis Period: Last {days_back} days

{pm_context}
"""

        # Send progress update if callback provided
        if step_callback:
            step_callback("Analyzing project portfolio...")

        # Create the agents
        delivery_analyst_config = self.agents_config.get("delivery_excellence_analyst", {})
        delivery_analyst = Agent(
            role=delivery_analyst_config.get("role", "Delivery Excellence Analyst"),
            goal=delivery_analyst_config.get(
                "goal",
                "Analyze on-time delivery performance, project velocity, and schedule management",
            ),
            backstory=delivery_analyst_config.get(
                "backstory",
                "You are an expert in project delivery who has managed hundreds of implementations. You identify patterns in delays and techniques for consistent on-time delivery.",
            ),
            verbose=delivery_analyst_config.get("verbose", True),
            allow_delegation=delivery_analyst_config.get("allow_delegation", False),
            llm=self.llm,
        )

        customer_analyst_config = self.agents_config.get("customer_experience_analyst", {})
        customer_analyst = Agent(
            role=customer_analyst_config.get("role", "Customer Experience Analyst"),
            goal=customer_analyst_config.get(
                "goal",
                "Evaluate customer sentiment, communication quality, and relationship health across projects",
            ),
            backstory=customer_analyst_config.get(
                "backstory",
                "You specialize in analyzing customer interactions to identify communication patterns that drive satisfaction or dissatisfaction.",
            ),
            verbose=customer_analyst_config.get("verbose", True),
            allow_delegation=customer_analyst_config.get("allow_delegation", False),
            llm=self.llm,
        )

        risk_analyst_config = self.agents_config.get("risk_escalation_analyst", {})
        risk_analyst = Agent(
            role=risk_analyst_config.get("role", "Risk & Escalation Analyst"),
            goal=risk_analyst_config.get(
                "goal",
                "Assess escalation patterns, proactive risk management, and issue resolution effectiveness",
            ),
            backstory=risk_analyst_config.get(
                "backstory",
                "You are an expert at identifying early warning signs and coaching ICs on proactive risk management and escalation prevention.",
            ),
            verbose=risk_analyst_config.get("verbose", True),
            allow_delegation=risk_analyst_config.get("allow_delegation", False),
            llm=self.llm,
        )

        coach_config = self.agents_config.get("implementation_coach", {})
        coach = Agent(
            role=coach_config.get("role", "Implementation Coach"),
            goal=coach_config.get(
                "goal",
                "Provide actionable coaching to improve delivery rates, customer satisfaction, and IC effectiveness",
            ),
            backstory=coach_config.get(
                "backstory",
                "You are a senior implementation leader who has coached hundreds of ICs. You provide direct, specific, and actionable feedback.",
            ),
            verbose=coach_config.get("verbose", True),
            allow_delegation=coach_config.get("allow_delegation", False),
            llm=self.llm,
        )

        if step_callback:
            step_callback("Running delivery analysis...")

        # Create tasks
        delivery_task = Task(
            description=f"""{full_context}

ANALYZE DELIVERY PERFORMANCE:

1. **On-Time Delivery Rate**
   - What is the IC's on-time delivery rate?
   - How does this compare to benchmark (target: 80%+)?
   - What patterns exist in delayed projects?

2. **Project Velocity**
   - Are projects progressing at appropriate pace?
   - Are there stalled or slow-moving projects?
   - What is causing velocity issues?

3. **Budget Management**
   - Are projects staying within budget?
   - What causes projects to go over budget?
   - Is scope being managed effectively?

4. **Portfolio Balance**
   - Is the IC's portfolio appropriately sized?
   - Are there too many active projects?
   - Which projects need most attention right now?

5. **Completion Quality**
   - Are projects being closed cleanly?
   - Are there lingering tasks or issues?

Provide specific metrics and project examples.""",
            expected_output="Detailed delivery performance analysis with specific projects and improvement areas",
            agent=delivery_analyst,
        )

        if step_callback:
            step_callback("Running customer experience analysis...")

        customer_task = Task(
            description="""ANALYZE CUSTOMER EXPERIENCE:

1. **Sentiment Trends**
   - What are the average IC effectiveness and customer reception scores?
   - Are there projects with declining sentiment?
   - What's driving positive vs negative sentiment?

2. **Communication Quality** (from transcripts if available)
   - Is the IC communicating proactively?
   - Are issues being addressed transparently?
   - Is the IC building trust with customers?

3. **Meeting Effectiveness**
   - Are meetings productive with clear outcomes?
   - Are action items being tracked and completed?
   - Is the IC running effective status calls?

4. **Customer Relationship Health**
   - Are there strained customer relationships?
   - Which accounts need relationship repair?
   - What's working well in healthy relationships?

Identify specific examples and patterns.""",
            expected_output="Customer experience analysis with specific relationship health indicators",
            agent=customer_analyst,
        )

        if step_callback:
            step_callback("Running risk analysis...")

        risk_task = Task(
            description="""ANALYZE RISK & ESCALATION PATTERNS:

1. **Escalation Volume**
   - How many escalations/support cases across the IC's projects?
   - What percentage are high priority?
   - Are there recurring issues?

2. **Proactive vs Reactive**
   - Is the IC identifying risks early?
   - Are escalations being prevented or just managed?
   - What warning signs are being missed?

3. **Resolution Effectiveness**
   - How quickly are issues being resolved?
   - Are the same issues recurring?
   - Is root cause being addressed?

4. **Project-Specific Risks**
   - Which projects have the most risk right now?
   - What immediate actions are needed?
   - Are at-risk projects getting appropriate attention?

Provide specific examples and risk mitigation recommendations.""",
            expected_output="Risk and escalation analysis with specific projects needing attention",
            agent=risk_analyst,
        )

        if step_callback:
            step_callback("Generating coaching recommendations...")

        coaching_task = Task(
            description="""Based on delivery, customer, and risk analysis, provide targeted IC coaching.

PROVIDE COACHING ON:

1. **Top 3 Immediate Priorities** - What should the IC do THIS WEEK?

2. **Project-Specific Actions**
   - At-risk projects: Specific recovery plays
   - Delayed projects: How to get back on track
   - Healthy projects: How to maintain momentum

3. **Delivery Improvement**
   - How to improve on-time delivery rate
   - Better scope and timeline management
   - Proactive customer communication

4. **Customer Relationship Building**
   - How to improve sentiment scores
   - Communication techniques to adopt
   - Rebuilding strained relationships

5. **Risk Management**
   - How to be more proactive on risks
   - Earlier identification techniques
   - Prevention vs reaction strategies

6. **Time Management**
   - How to manage a large portfolio effectively
   - Which projects need more/less attention
   - Prioritization framework

Be SPECIFIC and reference actual projects. Avoid generic advice.

Return your analysis in this JSON format:
{
    "summary": {
        "headline": "One-sentence summary of IC performance",
        "overall_score": 1-10,
        "delivery_performance": "excellent/good/needs improvement",
        "customer_satisfaction": "high/moderate/low"
    },
    "strengths": ["2-3 specific strengths with project examples"],
    "improvement_areas": ["2-3 specific areas with project examples"],
    "immediate_priorities": [
        {"action": "specific action", "project": "project name", "impact": "why this matters"}
    ],
    "at_risk_projects": [
        {"name": "project", "risk": "description", "recommended_action": "specific play"}
    ],
    "delivery_coaching": {
        "timeline_management": "Specific recommendations",
        "scope_management": "Specific recommendations",
        "communication_cadence": "Specific recommendations"
    },
    "customer_coaching": {
        "relationship_building": "Specific techniques",
        "proactive_communication": "What to do differently"
    },
    "risk_coaching": {
        "early_warning_signs": ["What to watch for"],
        "prevention_strategies": ["How to prevent escalations"]
    },
    "skill_development": {
        "priority_skill": "The #1 skill to develop",
        "practice_plan": "How to develop this skill"
    }
}""",
            expected_output="JSON coaching analysis with specific recommendations",
            agent=coach,
            context=[delivery_task, customer_task, risk_task],
        )

        # Create and run the crew
        crew = Crew(
            name="PM Coaching Crew",
            agents=[delivery_analyst, customer_analyst, risk_analyst, coach],
            tasks=[delivery_task, customer_task, risk_task, coaching_task],
            process=Process.sequential,
            verbose=False,
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
                    "pm_name": pm_name,
                    "pm_email": pm_email,
                    "projects_analyzed": len(projects_data) if projects_data else 0,
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
            "pm_name": pm_name,
            "pm_email": pm_email,
            "projects_analyzed": len(projects_data) if projects_data else 0,
            "days_back": days_back,
            "raw_response": True,
            "provider": provider,
            "model": model_name,
        }
