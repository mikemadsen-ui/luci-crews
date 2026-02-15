"""
SDR (Sales Development Representative) Coaching Crew

Analyzes prospecting activity patterns, lead qualification quality, and pipeline
generation to provide personalized coaching for SDRs.
"""

from typing import Dict, Any, List, Optional
from crewai import Agent, Task, Crew, Process

from .base_crew import BaseCrew
from ..utils import extract_json_from_llm_response


class SDRCoachingCrew(BaseCrew):
    """Crew for analyzing SDR performance and providing coaching."""

    def _build_activity_context(
        self,
        performance_metrics: Dict[str, Any],
        sequence_data: List[Dict[str, Any]] = None,
    ) -> str:
        """Build context string from activity metrics."""
        context = """=== ACTIVITY METRICS ===
"""
        # Call metrics
        total_calls = performance_metrics.get("total_calls", 0)
        calls_connected = performance_metrics.get("calls_connected", 0)
        connect_rate = performance_metrics.get("connect_rate", 0)
        voicemails = performance_metrics.get("voicemails_left", 0)

        context += f"""
CALLS:
  Total Calls: {total_calls}
  Calls Connected: {calls_connected}
  Connect Rate: {connect_rate}% (Benchmark: 3-5%)
  Voicemails Left: {voicemails}
"""

        # Email metrics
        total_emails = performance_metrics.get("total_emails", 0)
        emails_replied = performance_metrics.get("emails_replied", 0)
        reply_rate = performance_metrics.get("reply_rate", 0)

        context += f"""
EMAILS:
  Total Emails Sent: {total_emails}
  Emails Replied: {emails_replied}
  Reply Rate: {reply_rate}% (Benchmark: 1-3%)
"""

        # Meeting metrics
        meetings_booked = performance_metrics.get("meetings_booked", 0)
        meetings_held = performance_metrics.get("meetings_held", 0)
        show_rate = performance_metrics.get("meeting_show_rate", 0)

        context += f"""
MEETINGS:
  Meetings Booked: {meetings_booked}
  Meetings Held: {meetings_held}
  Show Rate: {show_rate}% (Target: 80%+)
"""

        # Sequence data if available
        if sequence_data:
            context += "\n=== SEQUENCE/CADENCE PERFORMANCE ===\n"
            for seq in sequence_data[:5]:
                context += f"  {seq.get('sequence_name', 'Unknown')}: "
                context += f"{seq.get('enrolled', 0)} enrolled, "
                context += f"{seq.get('replies', 0)} replies, "
                context += f"{seq.get('meetings', 0)} meetings\n"

        return context

    def _build_lead_context(
        self,
        lead_pipeline_analysis: Dict[str, Any],
    ) -> str:
        """Build context string from lead pipeline data."""
        context = """=== LEAD PIPELINE HEALTH ===
"""
        total_leads = lead_pipeline_analysis.get("total_leads", 0)
        stale_leads = lead_pipeline_analysis.get("stale_leads", 0)
        working_leads = lead_pipeline_analysis.get("working_leads", 0)
        qualified_leads = lead_pipeline_analysis.get("qualified_leads", 0)
        converted_leads = lead_pipeline_analysis.get("converted_leads", 0)
        avg_days = lead_pipeline_analysis.get("avg_days_since_activity", 0)

        context += f"""
Total Leads: {total_leads}
Working Leads: {working_leads}
Qualified Leads: {qualified_leads}
Converted to Opportunity: {converted_leads}
Stale Leads (7+ days): {stale_leads} {'(CONCERN - review follow-up cadence)' if stale_leads > total_leads * 0.3 else ''}
Average Days Since Activity: {avg_days}
"""

        # Status breakdown
        leads_by_status = lead_pipeline_analysis.get("leads_by_status", {})
        if leads_by_status:
            context += "\nLEADS BY STATUS:\n"
            for status, count in sorted(leads_by_status.items(), key=lambda x: x[1], reverse=True):
                context += f"  {status}: {count}\n"

        # Source breakdown
        leads_by_source = lead_pipeline_analysis.get("leads_by_source", {})
        if leads_by_source:
            context += "\nLEADS BY SOURCE:\n"
            for source, count in sorted(leads_by_source.items(), key=lambda x: x[1], reverse=True)[:5]:
                context += f"  {source}: {count}\n"

        return context

    def _build_intent_context(
        self,
        intent_metrics: Dict[str, Any],
    ) -> str:
        """Build context string from 6Sense, UserGems, and campaign data."""
        if not intent_metrics:
            return ""

        hot_accounts = intent_metrics.get("hotAccounts", 0)
        decision_stage = intent_metrics.get("decisionStage", 0)
        purchase_stage = intent_metrics.get("purchaseStage", 0)
        high_intent = intent_metrics.get("highIntent", 0)
        user_gems = intent_metrics.get("userGems", 0)
        user_gems_from_customer = intent_metrics.get("userGemsFromCustomer", 0)
        champions = intent_metrics.get("champions", 0)
        campaign_responders = intent_metrics.get("campaignResponders", 0)

        # Only build context if there's data
        if not any([hot_accounts, user_gems, champions, campaign_responders]):
            return ""

        context = """=== INTENT & ENGAGEMENT SIGNALS ===

HOT ACCOUNTS (6Sense Decision/Purchase Stage):
"""
        if hot_accounts > 0 or decision_stage > 0 or purchase_stage > 0:
            context += f"""  Accounts in Decision Stage: {decision_stage}
  Accounts in Purchase Stage: {purchase_stage}
  High Intent Score (70+): {high_intent}
  Total Hot Accounts: {hot_accounts}

  NOTE: These accounts are showing strong buying signals. They should be TOP PRIORITY.
"""
        else:
            context += "  No accounts currently in Decision/Purchase stage.\n"

        context += "\nJOB CHANGE SIGNALS (UserGems):\n"
        if user_gems > 0:
            context += f"""  Total Job Changers: {user_gems}
  From Previous Customers: {user_gems_from_customer} (warm referral opportunity)
  Champions Moving Companies: {champions}

  NOTE: Job changers who came from customer companies are HIGH VALUE targets.
"""
        else:
            context += "  No recent job changers detected.\n"

        context += "\nCAMPAIGN ENGAGEMENT:\n"
        if campaign_responders > 0:
            context += f"""  Campaign Responders: {campaign_responders}

  NOTE: Contacts who responded to campaigns have shown interest. Follow up promptly.
"""
        else:
            context += "  No campaign responses tracked.\n"

        return context

    def _build_opportunity_context(
        self,
        opportunity_analysis: Dict[str, Any],
        performance_metrics: Dict[str, Any],
    ) -> str:
        """Build context string from opportunity data."""
        context = """=== PIPELINE GENERATION ===
"""
        total_opps = opportunity_analysis.get("total_opportunities", 0)
        total_pipeline = opportunity_analysis.get("total_pipeline", 0)
        avg_deal_size = opportunity_analysis.get("avg_deal_size", 0)

        opps_created = performance_metrics.get("opportunities_created", 0)
        pipeline_generated = performance_metrics.get("pipeline_generated", 0)

        context += f"""
Opportunities Created: {opps_created or total_opps}
Total Pipeline Generated: ${pipeline_generated or total_pipeline:,.0f}
Average Deal Size: ${float(avg_deal_size):,.0f}
"""

        # Stage breakdown
        opps_by_stage = opportunity_analysis.get("opportunities_by_stage", {})
        if opps_by_stage:
            context += "\nOPPORTUNITIES BY STAGE:\n"
            for stage, count in sorted(opps_by_stage.items(), key=lambda x: x[1], reverse=True):
                context += f"  {stage}: {count}\n"

        # Source breakdown
        opps_by_source = opportunity_analysis.get("opportunities_by_source", {})
        if opps_by_source:
            context += "\nOPPORTUNITIES BY SOURCE:\n"
            for source, count in sorted(opps_by_source.items(), key=lambda x: x[1], reverse=True)[:5]:
                context += f"  {source}: {count}\n"

        return context

    def run(
        self,
        sdr_name: str,
        sdr_email: str,
        performance_metrics: Dict[str, Any],
        lead_pipeline_analysis: Dict[str, Any],
        opportunity_analysis: Dict[str, Any],
        sequence_data: Optional[List[Dict[str, Any]]] = None,
        intent_metrics: Optional[Dict[str, Any]] = None,
        days_back: int = 30,
        step_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        Run the SDR coaching crew analysis.

        Args:
            sdr_name: Name of the SDR
            sdr_email: Email of the SDR
            performance_metrics: Aggregated activity metrics
            lead_pipeline_analysis: Lead pipeline health analysis
            opportunity_analysis: Opportunity creation analysis
            sequence_data: Optional sequence/cadence performance data
            intent_metrics: Optional 6Sense, UserGems, campaign engagement metrics
            days_back: Number of days to analyze
            step_callback: Optional callback for progress updates

        Returns:
            Coaching analysis results
        """
        # Build context strings
        activity_context = self._build_activity_context(performance_metrics, sequence_data)
        lead_context = self._build_lead_context(lead_pipeline_analysis)
        opportunity_context = self._build_opportunity_context(opportunity_analysis, performance_metrics)
        intent_context = self._build_intent_context(intent_metrics or {})

        full_context = f"""=== SDR COACHING ANALYSIS ===
SDR: {sdr_name}
Email: {sdr_email}
Analysis Period: Last {days_back} days

{activity_context}

{lead_context}

{opportunity_context}

{intent_context}
"""

        if step_callback:
            step_callback("Analyzing activity patterns...")

        # Create the agents
        activity_analyst_config = self._get_agent_config("sdr_activity_analyst")
        activity_analyst = Agent(
            role=activity_analyst_config.get("role", "SDR Activity Pattern Analyst"),
            goal=activity_analyst_config.get(
                "goal",
                "Analyze call, email, and meeting activity patterns to identify areas for improvement in prospecting behavior",
            ),
            backstory=activity_analyst_config.get(
                "backstory",
                "You are an expert in analyzing SDR activity data. You understand connect rates, reply rates, and meeting conversion patterns.",
            ),
            verbose=activity_analyst_config.get("verbose", True),
            allow_delegation=activity_analyst_config.get("allow_delegation", False),
            llm=self.llm,
        )

        lead_analyst_config = self._get_agent_config("sdr_lead_analyst")
        lead_analyst = Agent(
            role=lead_analyst_config.get("role", "Lead Qualification Analyst"),
            goal=lead_analyst_config.get(
                "goal",
                "Analyze lead qualification patterns and pipeline health to improve lead scoring and follow-up prioritization",
            ),
            backstory=lead_analyst_config.get(
                "backstory",
                "You specialize in understanding how SDRs qualify and prioritize leads. You identify stale leads and optimize follow-up strategies.",
            ),
            verbose=lead_analyst_config.get("verbose", True),
            allow_delegation=lead_analyst_config.get("allow_delegation", False),
            llm=self.llm,
        )

        pipeline_analyst_config = self._get_agent_config("sdr_pipeline_analyst")
        pipeline_analyst = Agent(
            role=pipeline_analyst_config.get("role", "Pipeline Generation Analyst"),
            goal=pipeline_analyst_config.get(
                "goal",
                "Analyze opportunity creation patterns and pipeline contribution to identify conversion strengths",
            ),
            backstory=pipeline_analyst_config.get(
                "backstory",
                "You are an expert at evaluating SDR contribution to pipeline generation. Pipeline value is the ultimate measure of SDR success.",
            ),
            verbose=pipeline_analyst_config.get("verbose", True),
            allow_delegation=pipeline_analyst_config.get("allow_delegation", False),
            llm=self.llm,
        )

        coach_config = self._get_agent_config("sdr_coach")
        coach = Agent(
            role=coach_config.get("role", "SDR Performance Coach"),
            goal=coach_config.get(
                "goal",
                "Synthesize all analysis into actionable coaching recommendations with a performance score",
            ),
            backstory=coach_config.get(
                "backstory",
                "You are a seasoned SDR coach who provides specific, actionable recommendations to help SDRs improve their pipeline generation.",
            ),
            verbose=coach_config.get("verbose", True),
            allow_delegation=coach_config.get("allow_delegation", False),
            llm=self.llm,
        )

        if step_callback:
            step_callback("Analyzing call, email, and meeting patterns...")

        # Create tasks
        activity_task = Task(
            description=f"""{full_context}

ANALYZE THE SDR'S ACTIVITY PATTERNS:

1. **Call Effectiveness**
   - How does the connect rate compare to benchmark (3-5%)?
   - Is call volume sufficient for pipeline targets?
   - What can be inferred about calling strategy?

2. **Email Performance**
   - How does the reply rate compare to benchmark (1-3%)?
   - Is email volume balanced with calls?
   - What does the data suggest about email quality?

3. **Meeting Conversion**
   - Is the show rate healthy (target 80%+)?
   - Are enough meetings being booked relative to activity?

4. **Multi-Channel Coordination**
   - Is the SDR using a balanced approach?
   - Any signs of over-reliance on one channel?

Provide specific observations with metrics.""",
            expected_output="Detailed analysis of activity patterns with specific metrics and improvement opportunities",
            agent=activity_analyst,
        )

        if step_callback:
            step_callback("Analyzing lead qualification...")

        lead_task = Task(
            description=f"""Based on the lead pipeline data, evaluate lead qualification and follow-up patterns.

ASSESS:
1. **Pipeline Health** - Is the lead distribution healthy across statuses?
2. **Stale Leads** - Are there too many leads without recent activity?
3. **Qualification Rate** - What percentage of contacted leads get qualified?
4. **Source Performance** - Which lead sources are most productive?
5. **Conversion Efficiency** - Lead-to-opportunity conversion rate

Identify specific risks and opportunities in the lead pipeline.""",
            expected_output="Lead qualification assessment with specific pipeline health metrics",
            agent=lead_analyst,
        )

        if step_callback:
            step_callback("Analyzing pipeline generation...")

        pipeline_task = Task(
            description=f"""Based on the opportunity data, evaluate pipeline generation performance.

ASSESS:
1. **Opportunity Volume** - Is the SDR creating enough opportunities?
2. **Pipeline Value** - Total dollar value generated
3. **Deal Quality** - Average deal size and stage distribution
4. **Source Effectiveness** - Which sources yield best opportunities?
5. **Activity-to-Opportunity Ratio** - How efficient is the SDR at converting activity to pipeline?

Provide specific observations about pipeline contribution.""",
            expected_output="Pipeline generation analysis with specific metrics and efficiency assessment",
            agent=pipeline_analyst,
        )

        if step_callback:
            step_callback("Generating coaching recommendations...")

        # Check if intent data is available
        has_intent_data = intent_metrics and any([
            intent_metrics.get("hotAccounts", 0),
            intent_metrics.get("userGems", 0),
            intent_metrics.get("champions", 0),
            intent_metrics.get("campaignResponders", 0),
        ])

        intent_coaching_section = ""
        if has_intent_data:
            intent_coaching_section = """
5. **Intent Signal Utilization** (CRITICAL):
   - Are hot accounts (Decision/Purchase stage) being prioritized?
   - Are UserGems (job changers) being contacted quickly?
   - Is the SDR following up with champions from customer companies?
   - Are campaign responders getting timely outreach?
   - Specific recommendations for leveraging intent signals

"""

        coaching_task = Task(
            description=f"""Based on all analysis, provide targeted coaching recommendations for {sdr_name}.

PROVIDE COACHING ON:

1. **Performance Score (1-10)** based on:
   - Activity volume and consistency (20%)
   - Activity effectiveness - connect rates, reply rates, show rates (20%)
   - Lead qualification quality (20%)
   - Pipeline generation results (20%)
   - Intent signal utilization - prioritizing hot accounts, job changers (20%)

2. **Executive Summary** (150 words max):
   - Overall score and key takeaway
   - Top 2-3 strengths
   - Top 2-3 improvement areas
   - Single most impactful recommendation

3. **Comprehensive Analysis** (500-800 words):
   - Activity pattern insights
   - Lead qualification assessment
   - Pipeline generation analysis
   - Prioritized coaching recommendations
   - Specific tactics to try
   - Recognition of wins

4. **Priority Actions** (if hot accounts or job changers exist):
   - Specific accounts/contacts to prioritize TODAY
   - Why these are high-value targets
   - Suggested outreach approach
{intent_coaching_section}
Be SPECIFIC and ACTIONABLE. Reference actual metrics.

IMPORTANT: If there are accounts in Decision or Purchase stage, or contacts who recently changed jobs from customer companies, these should be the TOP PRIORITY and must be called out prominently.

Return your analysis in this JSON format:
{{
    "score": 1-10,
    "summary": "Executive summary (150 words max)",
    "comprehensiveAnalysis": "Detailed analysis (500-800 words)",
    "priorityActions": ["Action 1", "Action 2", "Action 3"]
}}""",
            expected_output="JSON coaching analysis with score, summary, and comprehensive analysis",
            agent=coach,
            context=[activity_task, lead_task, pipeline_task],
        )

        # Create and run the crew
        crew = Crew(
            agents=[activity_analyst, lead_analyst, pipeline_analyst, coach],
            tasks=[activity_task, lead_task, pipeline_task, coaching_task],
            process=Process.sequential,
            verbose=False,
        )

        result = crew.kickoff()
        result_text = str(result)

        # Get actual model info from LLM
        model_name = getattr(self.llm, 'model', 'unknown')
        provider = "openai"
        if "claude" in model_name.lower() or "anthropic" in model_name.lower():
            provider = "anthropic"
        elif "gemini" in model_name.lower():
            provider = "google"

        # Extract JSON from the result
        parsed_result = extract_json_from_llm_response(result_text)
        is_raw = "text" in parsed_result and len(parsed_result) == 1

        return {
            "success": True,
            "result": result_text if is_raw else parsed_result,
            "sdr_name": sdr_name,
            "sdr_email": sdr_email,
            "days_back": days_back,
            "raw_response": is_raw,
            "provider": provider,
            "model": model_name,
        }
