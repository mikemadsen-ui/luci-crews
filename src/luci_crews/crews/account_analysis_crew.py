"""
Account Analysis Crew - Unified analysis combining sentiment and account health.

This crew consolidates customer sentiment analysis and account health assessment
into a single comprehensive account analysis. It provides:
- Single unified score (1-10)
- Sentiment analysis (from transcripts and support data)
- Health analysis (churn risk, expansion opportunities)
- Actionable recommendations and talking points
"""

import json
import logging
import os
import re
from typing import Any, Callable, Dict, List, Optional

from crewai import Agent, Crew, Task, LLM

from ..ai_settings_helper import create_llm_for_user, DEFAULT_AI_SETTINGS

logger = logging.getLogger(__name__)


class AccountAnalysisCrew:
    """Unified account analysis crew combining sentiment and health assessment."""

    def __init__(self, user_id: Optional[str] = None):
        """Initialize the account analysis crew.

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

    def _create_account_analyst(self) -> Agent:
        """Create the unified account analyst agent."""
        return Agent(
            role="Senior Account Analyst",
            goal="Analyze customer accounts comprehensively by evaluating sentiment from interactions and overall account health metrics",
            backstory="""You are an expert customer success analyst with deep experience in
            both sentiment analysis and account health assessment. You've managed enterprise
            accounts worth millions in ARR and can detect subtle shifts in customer satisfaction.
            You understand that true account health comes from combining what customers say
            (sentiment) with what the data shows (health metrics).""",
            verbose=True,
            allow_delegation=False,
            llm=self.llm,
        )

    def _create_synthesis_coach(self) -> Agent:
        """Create the synthesis and recommendations agent."""
        return Agent(
            role="Account Strategy Coach",
            goal="Synthesize analysis findings into actionable recommendations and a unified score",
            backstory="""You are a strategic advisor who excels at turning complex analyses
            into clear, actionable guidance. You know how to weight different signals -
            understanding that customer sentiment and account health metrics together tell
            a complete story. You provide practical recommendations that account managers
            can act on immediately.""",
            verbose=True,
            allow_delegation=False,
            llm=self.llm,
        )

    def _format_account_context(
        self,
        account_name: str,
        account_tier: Optional[str],
        arr: Optional[float],
    ) -> str:
        """Format account metadata context."""
        arr_str = f"${arr:,.0f}" if arr else "Unknown"
        context = f"""=== ACCOUNT INFORMATION ===
Account Name: {account_name}
Account Tier: {account_tier or 'Unknown'}
ARR: {arr_str}
"""
        return context

    def _format_communications_context(
        self,
        transcription: Optional[str],
    ) -> str:
        """Format communications/transcription context."""
        if not transcription:
            return "=== RECENT COMMUNICATIONS ===\nNo recent call transcriptions available."

        # Truncate if too long
        text = transcription
        if len(text) > 8000:
            text = text[:8000] + "\n... [truncated]"

        return f"""=== RECENT COMMUNICATIONS ===
{text}
"""

    def _format_support_context(
        self,
        support_data: Optional[Dict[str, Any]],
    ) -> str:
        """Format support ticket context."""
        if not support_data:
            return "=== SUPPORT ACTIVITY ===\nNo support data available."

        lines = ["=== SUPPORT ACTIVITY ==="]

        total_cases = support_data.get("total_cases_count", 0)
        recent_tickets = support_data.get("recent_tickets", [])

        # Calculate current status summary
        open_count = sum(1 for t in recent_tickets if t.get("status", "").lower() not in ["closed", "resolved"])
        closed_count = sum(1 for t in recent_tickets if t.get("status", "").lower() in ["closed", "resolved"])

        lines.append(f"Total Support Cases: {total_cases}")

        # Add clear current status summary
        if open_count == 0 and closed_count > 0:
            lines.append(f"⚠️ CURRENT STATUS: All {closed_count} cases are CLOSED/RESOLVED - no open issues")
        elif open_count > 0:
            lines.append(f"⚠️ CURRENT STATUS: {open_count} OPEN case(s), {closed_count} closed")

        if recent_tickets:
            lines.append(f"\nCase History ({len(recent_tickets)} cases):")
            for ticket in recent_tickets[:10]:
                subject = ticket.get("subject", "No subject")
                status = ticket.get("status", "Unknown")
                priority = ticket.get("priority", "Normal")
                lines.append(f"  - [{priority}] {subject} (Status: {status})")

        return "\n".join(lines)

    def _format_engagement_context(
        self,
        engagement_data: Optional[Dict[str, Any]],
    ) -> str:
        """Format engagement metrics context."""
        if not engagement_data:
            return "=== ENGAGEMENT METRICS ===\nNo engagement data available."

        lines = ["=== ENGAGEMENT METRICS ==="]

        if "last_login" in engagement_data:
            lines.append(f"Last Login: {engagement_data['last_login']}")
        if "active_users" in engagement_data:
            lines.append(f"Active Users: {engagement_data['active_users']}")
        if "feature_adoption" in engagement_data:
            lines.append(f"Feature Adoption: {engagement_data['feature_adoption']}%")

        return "\n".join(lines)

    def run(
        self,
        account_name: str,
        account_tier: Optional[str] = None,
        arr: Optional[float] = None,
        transcription: Optional[str] = None,
        support_data: Optional[Dict[str, Any]] = None,
        engagement_data: Optional[Dict[str, Any]] = None,
        send_progress: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """
        Run the unified account analysis.

        Args:
            account_name: Name of the account
            account_tier: Account tier (Enterprise, Mid-market, etc.)
            arr: Annual Recurring Revenue
            transcription: Recent call transcription text
            support_data: Dict with total_cases_count and recent_tickets
            engagement_data: Dict with engagement metrics
            send_progress: Optional callback for streaming progress

        Returns:
            Dict with unified score, sentiment analysis, health analysis, and recommendations
        """
        logger.info(f"Running unified account analysis for: {account_name}")

        def _emit_progress(step: str, message: str):
            if send_progress:
                send_progress(step, message)
            logger.info(f"[{step}] {message}")

        # Format context
        account_context = self._format_account_context(account_name, account_tier, arr)
        communications_context = self._format_communications_context(transcription)
        support_context = self._format_support_context(support_data)
        engagement_context = self._format_engagement_context(engagement_data)

        full_context = f"""{account_context}

{communications_context}

{support_context}

{engagement_context}
"""

        # Create agents
        account_analyst = self._create_account_analyst()
        synthesis_coach = self._create_synthesis_coach()

        # Task 1: Comprehensive Account Analysis
        _emit_progress("Step 1", "Analyzing account sentiment and health...")
        analysis_task = Task(
            description=f"""Analyze this customer account comprehensively.

{full_context}

Evaluate TWO key dimensions:

1. CUSTOMER SENTIMENT (from communications and support):
   - Overall sentiment tone (positive/neutral/negative)
   - Key themes in customer communications
   - Notable quotes or concerns
   - Positive signals and warning signs
   - Support ticket patterns and satisfaction

2. ACCOUNT HEALTH (from metrics and behavior):
   - Engagement level and trends
   - Support health (ticket volume, resolution satisfaction)
   - Relationship strength
   - Churn risk indicators
   - Expansion opportunity signals

IMPORTANT: Pay close attention to the CURRENT STATUS of support cases:
- If all cases are CLOSED/RESOLVED, this is POSITIVE - do NOT describe them as "unresolved" or "open"
- Distinguish between CURRENT state (are there open issues NOW?) and HISTORICAL patterns (past issues)
- If all cases are closed, focus your support assessment on historical patterns and resolution quality

For each dimension, provide:
- A component score from 1-10
- Key findings and evidence
- Specific quotes or data points that support your assessment

Return as JSON:
{{
  "sentiment_component_score": <1-10>,
  "sentiment_summary": "<2-3 sentence summary>",
  "positive_signals": ["<signal1>", "<signal2>"],
  "warning_signs": ["<sign1>", "<sign2>"],
  "key_themes": ["<theme1>", "<theme2>"],
  "key_quotes": [{{"quote": "<quote>", "context": "<context>"}}],
  "health_component_score": <1-10>,
  "health_summary": "<2-3 sentence summary>",
  "strengths": ["<strength1>", "<strength2>"],
  "concerns": ["<concern1>", "<concern2>"],
  "churn_risk": {{
    "level": "low" | "medium" | "high",
    "factors": ["<factor1>"],
    "early_warnings": ["<warning1>"]
  }},
  "expansion_opportunities": [
    {{"opportunity": "<description>", "potential": "low" | "medium" | "high"}}
  ]
}}
""",
            expected_output="JSON analysis with sentiment and health components",
            agent=account_analyst,
        )

        # Task 2: Synthesis and Recommendations
        _emit_progress("Step 2", "Synthesizing findings and generating recommendations...")
        synthesis_task = Task(
            description=f"""Based on the account analysis, synthesize the findings into a unified assessment.

Account: {account_name}

Review the sentiment and health analysis from the previous task. Create a unified assessment that:

1. UNIFIED SCORE (1-10):
   - Weight: 40% sentiment + 60% health (health is more predictive of churn)
   - Calculate the weighted average
   - Round to nearest integer

2. OVERALL STATUS:
   - "thriving" (9-10): Expanding, strong champion, excellent engagement
   - "healthy" (7-8): Stable relationship, good adoption, minor concerns
   - "stable" (5-6): Meeting expectations, some gaps, manageable risk
   - "at_risk" (3-4): Declining engagement, support issues, churn signals
   - "critical" (1-2): Immediate intervention needed

3. TREND:
   - "improving", "stable", or "declining" based on signals

4. EXECUTIVE SUMMARY:
   - 2-3 sentences capturing the essential state of this account

5. RECOMMENDED ACTIONS:
   - 3-5 specific, actionable recommendations
   - Prioritized by urgency

6. TALKING POINTS:
   - Key points for the next customer conversation

Return as JSON:
{{
  "score": <1-10>,
  "score_breakdown": {{
    "sentiment_component": <1-10>,
    "health_component": <1-10>
  }},
  "status": "thriving" | "healthy" | "stable" | "at_risk" | "critical",
  "trend": "improving" | "stable" | "declining",
  "executive_summary": "<2-3 sentence summary>",
  "sentiment_analysis": {{
    "summary": "<summary>",
    "positive_signals": [],
    "warning_signs": [],
    "key_themes": [],
    "key_quotes": []
  }},
  "health_analysis": {{
    "summary": "<summary>",
    "strengths": [],
    "concerns": [],
    "churn_risk": {{}},
    "expansion_opportunities": []
  }},
  "recommended_actions": [
    {{"action": "<action>", "priority": "high" | "medium" | "low", "rationale": "<why>"}}
  ],
  "talking_points": ["<point1>", "<point2>"]
}}
""",
            expected_output="JSON with unified score and synthesized analysis",
            agent=synthesis_coach,
            context=[analysis_task],
        )

        # Create and run crew
        crew = Crew(
            agents=[account_analyst, synthesis_coach],
            tasks=[analysis_task, synthesis_task],
            verbose=True,
        )

        _emit_progress("Step 3", "Running analysis...")
        result = crew.kickoff()

        _emit_progress("Complete", "Analysis complete!")

        # Parse result
        try:
            raw_result = str(result)

            # Try to extract JSON from the result
            json_match = re.search(r'\{[\s\S]*\}', raw_result)
            if json_match:
                parsed = json.loads(json_match.group(0))
                parsed["_provider"] = "crewai"
                parsed["_model"] = os.environ.get("OPENAI_MODEL_NAME", DEFAULT_AI_SETTINGS["model_id"])
                return parsed

            # Fallback: return structured response with raw text
            return {
                "score": 5,
                "status": "stable",
                "trend": "stable",
                "executive_summary": raw_result[:500] if raw_result else "Analysis completed",
                "sentiment_analysis": {"summary": "See executive summary"},
                "health_analysis": {"summary": "See executive summary"},
                "recommended_actions": [],
                "talking_points": [],
                "_raw_result": raw_result,
                "_provider": "crewai",
                "_model": os.environ.get("OPENAI_MODEL_NAME", DEFAULT_AI_SETTINGS["model_id"]),
            }

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON result: {e}")
            return {
                "score": 5,
                "status": "stable",
                "trend": "stable",
                "executive_summary": str(result)[:500] if result else "Analysis completed",
                "sentiment_analysis": {"summary": "See executive summary"},
                "health_analysis": {"summary": "See executive summary"},
                "recommended_actions": [],
                "talking_points": [],
                "_raw_result": str(result),
                "_parse_error": str(e),
                "_provider": "crewai",
                "_model": os.environ.get("OPENAI_MODEL_NAME", DEFAULT_AI_SETTINGS["model_id"]),
            }
