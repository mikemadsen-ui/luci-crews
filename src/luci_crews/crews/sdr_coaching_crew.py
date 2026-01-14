"""
SDR (Sales Development Representative) Coaching Crew

Analyzes prospecting activity patterns, lead qualification quality, and pipeline
generation to provide personalized coaching for SDRs.
"""

import os
import json
from typing import Dict, Any, List, Optional
from crewai import Agent, Task, Crew, Process, LLM

from ..config_loader import load_agents_config, load_tasks_config
from ..ai_settings_helper import create_llm_for_user, DEFAULT_AI_SETTINGS


class SDRCoachingCrew:
    """Crew for analyzing SDR performance and providing coaching."""

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
            days_back: Number of days to analyze
            step_callback: Optional callback for progress updates

        Returns:
            Coaching analysis results
        """
        # Build context strings
        activity_context = self._build_activity_context(performance_metrics, sequence_data)
        lead_context = self._build_lead_context(lead_pipeline_analysis)
        opportunity_context = self._build_opportunity_context(opportunity_analysis, performance_metrics)

        full_context = f"""=== SDR COACHING ANALYSIS ===
SDR: {sdr_name}
Email: {sdr_email}
Analysis Period: Last {days_back} days

{activity_context}

{lead_context}

{opportunity_context}
"""

        if step_callback:
            step_callback("Analyzing activity patterns...")

        # Create the agents
        activity_analyst_config = self.agents_config.get("sdr_activity_analyst", {})
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

        lead_analyst_config = self.agents_config.get("sdr_lead_analyst", {})
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

        pipeline_analyst_config = self.agents_config.get("sdr_pipeline_analyst", {})
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

        coach_config = self.agents_config.get("sdr_coach", {})
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

        coaching_task = Task(
            description=f"""Based on all analysis, provide targeted coaching recommendations for {sdr_name}.

PROVIDE COACHING ON:

1. **Performance Score (1-10)** based on:
   - Activity volume and consistency (25%)
   - Activity effectiveness - connect rates, reply rates, show rates (25%)
   - Lead qualification quality (25%)
   - Pipeline generation results (25%)

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

Be SPECIFIC and ACTIONABLE. Reference actual metrics.

Return your analysis in this JSON format:
{{
    "score": 1-10,
    "summary": "Executive summary (150 words max)",
    "comprehensiveAnalysis": "Detailed analysis (500-800 words)"
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
                    "sdr_name": sdr_name,
                    "sdr_email": sdr_email,
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
            "sdr_name": sdr_name,
            "sdr_email": sdr_email,
            "days_back": days_back,
            "raw_response": True,
            "provider": provider,
            "model": model_name,
        }
