"""
SC (Solutions Consultant) Coaching Crew

Analyzes demo effectiveness, discovery synthesis, and deal support to provide
personalized coaching for Solutions Consultants.
"""

import os
import json
from typing import Dict, Any, List, Optional
from crewai import Agent, Task, Crew, Process, LLM

from ..config_loader import load_agents_config, load_tasks_config
from ..ai_settings_helper import create_llm_for_user, DEFAULT_AI_SETTINGS


class SCCoachingCrew:
    """Crew for analyzing Solutions Consultant performance and providing coaching."""

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

    def _build_sc_context(
        self,
        opportunities_data: List[Dict[str, Any]],
        demo_transcripts: List[Dict[str, Any]] = None,
        discovery_transcripts: List[Dict[str, Any]] = None,
        deal_outcomes: Dict[str, Any] = None,
    ) -> str:
        """Build context string from SC activity data."""
        context = "=== SC PERFORMANCE METRICS ===\n"

        if deal_outcomes:
            context += f"""
Deals Supported: {deal_outcomes.get('total_deals', 0)}
Won Deals: {deal_outcomes.get('won_deals', 0)}
Lost Deals: {deal_outcomes.get('lost_deals', 0)}
Open Deals: {deal_outcomes.get('open_deals', 0)}
Total Value Supported: ${deal_outcomes.get('total_value', 0):,.0f}
Won Value: ${deal_outcomes.get('won_value', 0):,.0f}
Win Rate on Supported Deals: {deal_outcomes.get('win_rate', 0):.1f}%
"""

        # Opportunity details
        if opportunities_data:
            context += "\n=== DEALS SUPPORTED (Recent) ===\n"
            for opp in sorted(
                opportunities_data, key=lambda x: x.get("close_date", ""), reverse=True
            )[:10]:
                status = (
                    "WON"
                    if opp.get("is_won")
                    else ("LOST" if opp.get("is_closed") else "OPEN")
                )
                amount = opp.get("amount", 0) or 0
                context += f"\n[{status}] {opp.get('name', 'Unknown')} - ${amount:,.0f}\n"
                context += f"  Account: {opp.get('account_name', 'Unknown')} | Industry: {opp.get('account_industry', 'Unknown')}\n"
                context += f"  Stage: {opp.get('stage_name', 'Unknown')}\n"

        # Demo transcript analysis
        if demo_transcripts:
            context += "\n=== DEMO CALL TRANSCRIPTS ===\n"
            context += f"(Analyzing {len(demo_transcripts)} demo calls for effectiveness)\n"
            for t in demo_transcripts[:3]:
                context += f"\nDemo: {t.get('subject', 'Unknown')} ({t.get('date', 'Unknown')})\n"
                text = t.get("text", "")[:3000]
                if text:
                    context += f"Transcript excerpt:\n{text}\n...\n"

        # Discovery transcript analysis
        if discovery_transcripts:
            context += "\n=== DISCOVERY CALL TRANSCRIPTS ===\n"
            context += f"(Analyzing {len(discovery_transcripts)} discovery calls)\n"
            for t in discovery_transcripts[:3]:
                context += f"\nDiscovery: {t.get('subject', 'Unknown')} ({t.get('date', 'Unknown')})\n"
                text = t.get("text", "")[:3000]
                if text:
                    context += f"Transcript excerpt:\n{text}\n...\n"

        if not demo_transcripts and not discovery_transcripts:
            context += "\n[No transcript data available - analysis will be limited to deal outcomes only]\n"

        return context

    def run(
        self,
        sc_name: str,
        sc_email: str,
        opportunities_data: Optional[List[Dict[str, Any]]] = None,
        demo_transcripts: Optional[List[Dict[str, Any]]] = None,
        discovery_transcripts: Optional[List[Dict[str, Any]]] = None,
        deal_outcomes: Optional[Dict[str, Any]] = None,
        days_back: int = 180,
        step_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        Run the SC coaching crew analysis.

        Args:
            sc_name: Name of the Solutions Consultant
            sc_email: Email of the Solutions Consultant
            opportunities_data: Pre-fetched opportunity data
            demo_transcripts: Pre-fetched demo call transcripts
            discovery_transcripts: Pre-fetched discovery call transcripts
            deal_outcomes: Pre-calculated deal outcome metrics
            days_back: Number of days to analyze
            step_callback: Optional callback for progress updates

        Returns:
            Coaching analysis results
        """
        if not opportunities_data and not demo_transcripts and not discovery_transcripts:
            return {
                "success": False,
                "error": "No activity data provided for analysis",
                "sc_name": sc_name,
                "sc_email": sc_email,
            }

        # Build context
        sc_context = self._build_sc_context(
            opportunities_data or [],
            demo_transcripts,
            discovery_transcripts,
            deal_outcomes,
        )

        full_context = f"""=== SC COACHING ANALYSIS ===
Solutions Consultant: {sc_name}
Email: {sc_email}
Analysis Period: Last {days_back} days

{sc_context}
"""

        if step_callback:
            step_callback("Analyzing demo effectiveness...")

        # Create the agents
        demo_config = self.agents_config.get("demo_effectiveness_analyst", {})
        demo_analyst = Agent(
            role=demo_config.get("role", "Demo Effectiveness Analyst"),
            goal=demo_config.get(
                "goal",
                "Evaluate demo quality, technical credibility, and ability to connect features to business value",
            ),
            backstory=demo_config.get(
                "backstory",
                "You are a demo excellence expert who has trained hundreds of SCs. You can identify what makes demos compelling vs forgettable.",
            ),
            verbose=demo_config.get("verbose", True),
            allow_delegation=demo_config.get("allow_delegation", False),
            llm=self.llm,
        )

        discovery_config = self.agents_config.get("discovery_synthesis_expert", {})
        discovery_expert = Agent(
            role=discovery_config.get("role", "Discovery Synthesis Expert"),
            goal=discovery_config.get(
                "goal",
                "Assess how well the SC captures, synthesizes, and applies discovery insights to solutions",
            ),
            backstory=discovery_config.get(
                "backstory",
                "You specialize in evaluating how SCs translate customer discovery into tailored solutions and compelling business cases.",
            ),
            verbose=discovery_config.get("verbose", True),
            allow_delegation=discovery_config.get("allow_delegation", False),
            llm=self.llm,
        )

        coach_config = self.agents_config.get("technical_win_coach", {})
        coach = Agent(
            role=coach_config.get("role", "Technical Win Coach"),
            goal=coach_config.get(
                "goal",
                "Provide actionable coaching to improve technical win rates and deal velocity",
            ),
            backstory=coach_config.get(
                "backstory",
                "You are a veteran SC leader who has helped SCs improve their technical win rates from 50% to 80%+. You provide direct, specific feedback.",
            ),
            verbose=coach_config.get("verbose", True),
            allow_delegation=coach_config.get("allow_delegation", False),
            llm=self.llm,
        )

        # Create tasks
        demo_task = Task(
            description=f"""{full_context}

ANALYZE DEMO EFFECTIVENESS:

1. **Demo Structure & Flow**
   - Does the demo have a clear narrative arc (problem -> solution -> value)?
   - Is the demo customized to the audience or generic?
   - Is time spent appropriately on high-impact features?

2. **Technical Credibility**
   - Does the SC demonstrate deep product knowledge?
   - Are technical questions handled confidently?
   - Are integrations and technical requirements addressed?

3. **Value Articulation**
   - Are features connected to business outcomes?
   - Is the "so what?" clearly communicated?
   - Are competitive differentiators highlighted?

4. **Audience Engagement**
   - Is the SC reading the room and adjusting?
   - Are stakeholders participating or passive?
   - Are objections being surfaced and addressed?

5. **Demo Outcomes**
   - What percentage of demos result in advancement?
   - Are there patterns in demos that win vs lose?

If no demo transcripts available, note this limitation.""",
            expected_output="Demo effectiveness analysis with specific examples and improvement areas",
            agent=demo_analyst,
        )

        if step_callback:
            step_callback("Analyzing discovery synthesis...")

        discovery_task = Task(
            description="""ANALYZE DISCOVERY SYNTHESIS:

1. **Discovery Capture**
   - Is the SC documenting key discovery findings?
   - Are pain points, metrics, and decision criteria captured?
   - Is the technical environment understood?

2. **Discovery Application**
   - Are demo and solution presentations tailored to discovery?
   - Are customer-specific use cases incorporated?
   - Is business value quantified based on discovery?

3. **Stakeholder Understanding**
   - Are different stakeholder perspectives captured?
   - Is the technical vs business buyer balance understood?
   - Are evaluation criteria known for each stakeholder?

4. **Gap Analysis**
   - What discovery information is typically missing?
   - Are there blind spots the SC should probe?
   - Is competitive intelligence being gathered?

If no discovery transcripts available, note this limitation.""",
            expected_output="Discovery synthesis analysis with specific gaps and recommendations",
            agent=discovery_expert,
        )

        if step_callback:
            step_callback("Generating coaching recommendations...")

        coaching_task = Task(
            description="""Based on demo and discovery analysis, provide targeted SC coaching.

PROVIDE COACHING ON:

1. **Technical Win Rate Improvement**
   - What specific changes would increase win rate?
   - Which deals in the pipeline need different approach?

2. **Demo Excellence**
   - What should the SC do more/less of in demos?
   - Specific techniques to improve engagement
   - How to better handle tough technical questions

3. **Discovery-to-Demo Connection**
   - How to better translate discovery to demos
   - Creating more compelling value propositions
   - Building stronger business cases

4. **Deal Velocity**
   - How to reduce technical evaluation time
   - Getting to technical wins faster
   - Handling competitive situations

5. **Skill Development**
   - Top 2-3 skills to develop
   - Specific practice recommendations

Be SPECIFIC. Reference actual examples from the data.

Return your analysis in this JSON format:
{
    "summary": {
        "headline": "One-sentence summary of SC performance",
        "overall_score": 1-10,
        "technical_win_rate_assessment": "strong/average/needs improvement",
        "demo_effectiveness": "excellent/good/developing"
    },
    "strengths": ["2-3 specific strengths with examples"],
    "improvement_areas": ["2-3 specific areas with examples"],
    "demo_coaching": {
        "keep_doing": ["What's working well"],
        "start_doing": ["New techniques to adopt"],
        "stop_doing": ["Habits to break"]
    },
    "discovery_coaching": {
        "key_questions_to_add": ["Questions they should ask"],
        "synthesis_improvements": ["How to better use discovery"]
    },
    "deal_specific_advice": [
        {"deal": "name", "recommendation": "specific action"}
    ],
    "skill_development": {
        "priority_skills": ["Top 2 skills to develop"],
        "practice_plan": "Specific activities to improve"
    },
    "quick_wins": ["3 things they can do this week"]
}""",
            expected_output="JSON coaching analysis with specific recommendations",
            agent=coach,
            context=[demo_task, discovery_task],
        )

        # Create and run the crew
        crew = Crew(
            agents=[demo_analyst, discovery_expert, coach],
            tasks=[demo_task, discovery_task, coaching_task],
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
                    "sc_name": sc_name,
                    "sc_email": sc_email,
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
            "sc_name": sc_name,
            "sc_email": sc_email,
            "opportunities_analyzed": len(opportunities_data) if opportunities_data else 0,
            "days_back": days_back,
            "raw_response": True,
            "provider": provider,
            "model": model_name,
        }
