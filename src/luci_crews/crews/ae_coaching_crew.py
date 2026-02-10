"""
AE (Account Executive) Sales Coaching Crew

Analyzes win/loss patterns, deal velocity, and discovery quality to provide
personalized coaching for Account Executives.
"""

import os
import json
from typing import Dict, Any, List, Optional
from crewai import Agent, Task, Crew, Process, LLM

from ..config_loader import load_agents_config, load_tasks_config
from ..ai_settings_helper import create_llm_for_user, DEFAULT_AI_SETTINGS


class AECoachingCrew:
    """Crew for analyzing Account Executive performance and providing coaching."""

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

    def _build_opportunity_context(
        self,
        opportunities_data: List[Dict[str, Any]],
        transcription_samples: List[Dict[str, Any]] = None,
    ) -> str:
        """Build context string from opportunity data."""
        if not opportunities_data:
            return "No opportunity data available for analysis."

        # Calculate metrics
        total_opps = len(opportunities_data)
        closed_opps = [o for o in opportunities_data if o.get("is_closed")]
        won_opps = [o for o in opportunities_data if o.get("is_won")]
        lost_opps = [
            o for o in opportunities_data if o.get("is_closed") and not o.get("is_won")
        ]
        open_opps = [o for o in opportunities_data if not o.get("is_closed")]

        win_rate = (len(won_opps) / len(closed_opps) * 100) if closed_opps else 0
        total_value = sum(o.get("amount", 0) or 0 for o in opportunities_data)
        won_value = sum(o.get("amount", 0) or 0 for o in won_opps)
        avg_deal_size = total_value / total_opps if total_opps else 0

        # Analyze by stage
        stages = {}
        for opp in open_opps:
            stage = opp.get("stage_name", "Unknown")
            stages[stage] = stages.get(stage, 0) + 1

        # Analyze by lead source
        sources = {}
        for opp in won_opps:
            source = opp.get("lead_source", "Unknown") or "Unknown"
            sources[source] = sources.get(source, 0) + 1

        context = f"""=== AE PERFORMANCE METRICS ===
Total Opportunities (Last 180 Days): {total_opps}
Closed-Won: {len(won_opps)} (${won_value:,.0f})
Closed-Lost: {len(lost_opps)}
Open Pipeline: {len(open_opps)}
Win Rate: {win_rate:.1f}%
Average Deal Size: ${avg_deal_size:,.0f}

=== PIPELINE BY STAGE ===
"""
        for stage, count in sorted(stages.items(), key=lambda x: x[1], reverse=True):
            context += f"  {stage}: {count} deals\n"

        context += "\n=== TOP PERFORMING LEAD SOURCES ===\n"
        for source, count in sorted(sources.items(), key=lambda x: x[1], reverse=True)[
            :5
        ]:
            context += f"  {source}: {count} wins\n"

        # Add recent closed deals for pattern analysis
        context += "\n=== RECENT CLOSED DEALS (For Pattern Analysis) ===\n"
        recent_closed = sorted(
            closed_opps, key=lambda x: x.get("close_date", ""), reverse=True
        )[:10]
        for opp in recent_closed:
            outcome = "WON" if opp.get("is_won") else "LOST"
            amount = opp.get("amount", 0) or 0
            context += f"\n[{outcome}] {opp.get('name', 'Unknown')} - ${amount:,.0f}\n"
            context += f"  Account: {opp.get('account_name', 'Unknown')} ({opp.get('account_industry', 'Unknown')})\n"
            context += f"  Stage: {opp.get('stage_name', 'Unknown')} | Source: {opp.get('lead_source', 'Unknown')}\n"

        # Add transcript insights if available
        if transcription_samples:
            context += "\n=== CALL/MEETING TRANSCRIPT SAMPLES ===\n"
            for sample in transcription_samples[:3]:
                opp_name = sample.get("opportunity_name", "Unknown")
                outcome = "WON" if sample.get("is_won") else "LOST"
                context += f"\n[{outcome}] {opp_name}\n"
                for t in sample.get("transcripts", [])[:1]:
                    context += (
                        f"  Meeting: {t.get('subject', 'Unknown')} ({t.get('date', 'Unknown')})\n"
                    )
                    text = t.get("text", "")[:2000]
                    if text:
                        context += f"  Excerpt: {text}...\n"

        return context

    def run(
        self,
        ae_name: str,
        ae_email: str,
        opportunities_data: Optional[List[Dict[str, Any]]] = None,
        transcription_samples: Optional[List[Dict[str, Any]]] = None,
        days_back: int = 180,
        step_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        Run the AE coaching crew analysis.

        Args:
            ae_name: Name of the Account Executive
            ae_email: Email of the Account Executive
            opportunities_data: Pre-fetched opportunity data
            transcription_samples: Pre-fetched transcription samples
            days_back: Number of days to analyze
            step_callback: Optional callback for progress updates

        Returns:
            Coaching analysis results
        """
        if not opportunities_data:
            return {
                "success": False,
                "error": "No opportunity data provided for analysis",
                "ae_name": ae_name,
                "ae_email": ae_email,
            }

        # Build context
        ae_context = self._build_opportunity_context(
            opportunities_data, transcription_samples
        )

        full_context = f"""=== AE COACHING ANALYSIS ===
Account Executive: {ae_name}
Email: {ae_email}
Analysis Period: Last {days_back} days

{ae_context}
"""

        if step_callback:
            step_callback("Analyzing sales performance...")

        # Create the agents
        perf_analyst_config = self.agents_config.get("sales_performance_analyst", {})
        perf_analyst = Agent(
            role=perf_analyst_config.get("role", "Sales Performance Analyst"),
            goal=perf_analyst_config.get(
                "goal",
                "Analyze win/loss patterns, deal velocity, and pipeline health to identify strengths and improvement areas",
            ),
            backstory=perf_analyst_config.get(
                "backstory",
                "You are an expert sales analyst who has reviewed thousands of deals. You identify patterns in successful deals and diagnose why deals are lost.",
            ),
            verbose=perf_analyst_config.get("verbose", True),
            allow_delegation=perf_analyst_config.get("allow_delegation", False),
            llm=self.llm,
        )

        discovery_analyst_config = self.agents_config.get("discovery_quality_analyst", {})
        discovery_analyst = Agent(
            role=discovery_analyst_config.get("role", "Discovery Quality Analyst"),
            goal=discovery_analyst_config.get(
                "goal",
                "Evaluate discovery call quality, stakeholder engagement, and qualification effectiveness from meeting transcripts",
            ),
            backstory=discovery_analyst_config.get(
                "backstory",
                "You are a MEDDIC/MEDDPICC expert who evaluates sales conversations for proper discovery, champion building, and deal qualification.",
            ),
            verbose=discovery_analyst_config.get("verbose", True),
            allow_delegation=discovery_analyst_config.get("allow_delegation", False),
            llm=self.llm,
        )

        coach_config = self.agents_config.get("sales_coach", {})
        coach = Agent(
            role=coach_config.get("role", "Sales Coach"),
            goal=coach_config.get(
                "goal",
                "Provide specific, actionable coaching recommendations to improve win rates and deal velocity",
            ),
            backstory=coach_config.get(
                "backstory",
                "You are an elite sales coach who has helped hundreds of AEs improve their performance. You provide direct, specific, and actionable feedback.",
            ),
            verbose=coach_config.get("verbose", True),
            allow_delegation=coach_config.get("allow_delegation", False),
            llm=self.llm,
        )

        if step_callback:
            step_callback("Analyzing win/loss patterns...")

        # Create tasks
        performance_task = Task(
            description=f"""{full_context}

ANALYZE THE AE'S SALES PERFORMANCE:

1. **Win/Loss Pattern Analysis**
   - What patterns exist in won deals? (deal size, industry, lead source, sales cycle)
   - What patterns exist in lost deals? Where in the funnel are deals dying?
   - Are there specific deal types or industries where the AE excels or struggles?

2. **Pipeline Health Assessment**
   - Is the pipeline balanced across stages?
   - Are deals progressing or stalling?
   - What is the average deal velocity?

3. **Deal Quality Indicators**
   - Are deals properly qualified before advancing?
   - Is there evidence of multi-threading (multiple stakeholders)?
   - Are deal amounts realistic based on outcomes?

4. **Competitive Performance**
   - How does win rate compare to team average (assume 25-30% benchmark)?
   - Are there patterns in competitive losses?

Provide specific metrics and examples from the data.""",
            expected_output="Detailed sales performance analysis with specific patterns, metrics, and examples",
            agent=perf_analyst,
        )

        if step_callback:
            step_callback("Analyzing discovery quality...")

        discovery_task = Task(
            description="""Based on the available meeting transcripts, evaluate the AE's discovery and engagement quality.

ASSESS:
1. **Discovery Depth** - Are they uncovering business pain, impact, and urgency?
2. **Stakeholder Engagement** - Evidence of multi-threading and champion building?
3. **Qualification Rigor** - MEDDIC/BANT criteria being validated?
4. **Next Steps** - Are meetings ending with clear, committed next steps?
5. **Talk/Listen Ratio** - Is the AE asking questions or just pitching?

NOTE: If no transcript data is available, skip this analysis and note that discovery quality cannot be assessed without call recordings.""",
            expected_output="Discovery and engagement quality assessment with specific examples from transcripts",
            agent=discovery_analyst,
        )

        if step_callback:
            step_callback("Generating coaching recommendations...")

        coaching_task = Task(
            description="""Based on the sales performance and discovery analysis, provide targeted coaching recommendations.

PROVIDE COACHING ON:

1. **Top 3 Immediate Actions** - What should the AE do this week to improve?

2. **Deal Strategy Improvements**
   - Which open deals need attention and what specifically should change?
   - How to improve qualification to avoid wasting time on bad deals?

3. **Discovery Improvements** (if transcript data available)
   - Specific questions to ask
   - How to better uncover pain and build urgency

4. **Pipeline Management**
   - How to improve deal velocity
   - Stage-specific actions to move deals forward

5. **Win Rate Improvement Plan**
   - Based on patterns in won vs lost deals, what should the AE do more/less of?

Be SPECIFIC and ACTIONABLE. Reference actual data. Avoid generic advice.

Return your analysis in this JSON format:
{
    "summary": {
        "headline": "One-sentence summary of AE's current state",
        "overall_score": 1-10,
        "win_rate_vs_benchmark": "above/at/below"
    },
    "strengths": ["List of 2-3 specific strengths with evidence"],
    "improvement_areas": ["List of 2-3 specific areas with evidence"],
    "immediate_actions": ["3 specific actions for this week"],
    "deal_coaching": {
        "at_risk_deals": ["Deal names that need attention"],
        "recommended_actions": ["Specific actions for each"]
    },
    "skill_development": {
        "priority_focus": "The #1 thing to work on",
        "resources": ["Suggested training or practice activities"]
    }
}""",
            expected_output="JSON coaching analysis with specific recommendations",
            agent=coach,
            context=[performance_task, discovery_task],
        )

        # Create and run the crew
        crew = Crew(
            agents=[perf_analyst, discovery_analyst, coach],
            tasks=[performance_task, discovery_task, coaching_task],
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
                    "ae_name": ae_name,
                    "ae_email": ae_email,
                    "opportunities_analyzed": len(opportunities_data) if opportunities_data else 0,
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
            "ae_name": ae_name,
            "ae_email": ae_email,
            "opportunities_analyzed": len(opportunities_data) if opportunities_data else 0,
            "days_back": days_back,
            "raw_response": True,
            "provider": provider,
            "model": model_name,
        }
