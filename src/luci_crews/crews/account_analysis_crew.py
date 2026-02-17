"""
Account Analysis Crew - Unified analysis combining sentiment and account health.

This crew consolidates customer sentiment analysis and account health assessment
into a single comprehensive account analysis. It provides:
- Single unified score (1-10)
- Sentiment analysis (from transcripts and support data)
- Health analysis (churn risk, expansion opportunities)
- Actionable recommendations and talking points
"""

import logging
from typing import Any, Callable, Dict, Optional

from crewai import Agent, Crew, Task

from .base_crew import BaseCrew
from ..utils import extract_json_from_llm_response

logger = logging.getLogger(__name__)


class AccountAnalysisCrew(BaseCrew):
    """Unified account analysis crew combining sentiment and health assessment."""

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
            verbose=False,
            allow_delegation=False,
            llm=self.llm,
        )

    def _create_synthesis_coach(self) -> Agent:
        """Create the synthesis and recommendations agent."""
        return Agent(
            role="Account Strategy Coach",
            goal="Synthesize analysis findings into actionable recommendations and a unified score that honestly reflects account reality",
            backstory="""You are a strategic advisor who excels at turning complex analyses
            into clear, actionable guidance. You are deliberately conservative with scores —
            you never let positive sentiment mask hard facts like churn, contract expiration,
            or product disengagement. If an account has churned, that's a 1-2 regardless of
            how much the contacts liked the product. You provide practical recommendations
            that account managers can act on immediately.""",
            verbose=False,
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
        """Format engagement metrics context from Snowflake product usage data."""
        if not engagement_data:
            return "=== PRODUCT USAGE & ENGAGEMENT ===\nNo product usage data available."

        lines = ["=== PRODUCT USAGE & ENGAGEMENT ==="]

        # Utilization metrics
        util_pct = engagement_data.get("utilizationPct")
        contracted = engagement_data.get("contractedSeats")
        active_30d = engagement_data.get("activeUsers30d")
        active_90d = engagement_data.get("activeUsers90d")

        if util_pct is not None or contracted is not None:
            lines.append("\n--- Seat Utilization ---")
            if contracted is not None:
                lines.append(f"Contracted Seats: {contracted}")
            if active_30d is not None:
                lines.append(f"Active Users (30d): {active_30d}")
            if active_90d is not None:
                lines.append(f"Active Users (90d): {active_90d}")
            if util_pct is not None:
                pct_val = round(util_pct) if isinstance(util_pct, (int, float)) else util_pct
                lines.append(f"Utilization: {pct_val}%")
                if isinstance(util_pct, (int, float)):
                    if util_pct < 30:
                        lines.append("⚠️ LOW UTILIZATION - significant underuse of contracted seats")
                    elif util_pct < 60:
                        lines.append("⚠️ MODERATE UTILIZATION - room for adoption improvement")
                    elif util_pct >= 90:
                        lines.append("✅ HIGH UTILIZATION - strong seat adoption")

        # Feature adoption
        features = engagement_data.get("features", [])
        feature_count = engagement_data.get("featureCount", 0)
        total_features = engagement_data.get("totalFeatures", 7)

        if features or feature_count:
            lines.append("\n--- Feature Adoption ---")
            lines.append(f"Features Enabled: {feature_count}/{total_features}")
            if features:
                lines.append(f"Active Features: {', '.join(features)}")
            all_features = {"Lead Routing", "Contact Routing", "Account Routing",
                            "Opportunity Routing", "Matching", "Attribution", "Engagement"}
            missing = all_features - set(features)
            if missing:
                lines.append(f"Not Enabled: {', '.join(sorted(missing))}")

        # Adoption score
        adoption_score = engagement_data.get("adoptionScore")
        health_grade = engagement_data.get("healthGrade")

        if adoption_score is not None or health_grade is not None:
            lines.append("\n--- Adoption Score ---")
            if adoption_score is not None:
                lines.append(f"Adoption Score: {adoption_score}")
            if health_grade is not None:
                lines.append(f"Health Grade: {health_grade}")
            routing_objs = engagement_data.get("routingObjects")
            if routing_objs is not None:
                lines.append(f"Routing Objects: {routing_objs}")
            unique_nodes = engagement_data.get("uniqueNodes")
            if unique_nodes is not None:
                lines.append(f"Unique Nodes: {unique_nodes}")
            total_node = engagement_data.get("totalNodeUsage")
            if total_node is not None:
                lines.append(f"Total Node Usage: {total_node}")
            contractual = engagement_data.get("contractualUsage")
            if contractual is not None:
                lines.append(f"Contractual Usage: {contractual}")
            integrations = engagement_data.get("integrationCount")
            if integrations is not None:
                lines.append(f"Integrations: {integrations}")
            extra = engagement_data.get("extraProducts")
            if extra is not None:
                lines.append(f"Extra Products: {extra}")

        # Help text (detailed improvement recommendations from Snowflake)
        help_text = engagement_data.get("helpText")
        if help_text:
            lines.append("\n--- Improvement Recommendations (from adoption model) ---")
            lines.append(help_text)

        # Renewal context and churn detection
        days_to_renewal = engagement_data.get("daysToRenewal")
        arr = engagement_data.get("arr")
        tier = engagement_data.get("tier")
        health_status = engagement_data.get("healthStatus")
        risk_reason = engagement_data.get("riskReason")
        churn_date = engagement_data.get("churnDate")

        # Detect churn signals and flag prominently
        is_churned = False
        if churn_date:
            is_churned = True
        if isinstance(days_to_renewal, (int, float)) and days_to_renewal < 0:
            is_churned = True
        if health_status and any(
            kw in str(health_status).lower()
            for kw in ("churn", "inactive", "cancelled")
        ):
            is_churned = True

        if is_churned:
            lines.append("\n🚨🚨🚨 CRITICAL: CONFIRMED CHURN / EXPIRED CONTRACT 🚨🚨🚨")
            lines.append("This account has churned or its contract has expired.")
            lines.append("Health score MUST be capped at 2. Overall score MUST be capped at 2.")
            lines.append("Do NOT let positive sentiment override this — churn is a hard fact.")
            if churn_date:
                lines.append(f"Churn Date: {churn_date}")
            if isinstance(days_to_renewal, (int, float)) and days_to_renewal < 0:
                lines.append(f"Contract Expired: {abs(int(days_to_renewal))} days ago")

        if days_to_renewal is not None or health_status is not None:
            lines.append("\n--- Renewal Context ---")
            if days_to_renewal is not None:
                lines.append(f"Days to Renewal: {days_to_renewal}")
                if isinstance(days_to_renewal, (int, float)) and days_to_renewal <= 90 and days_to_renewal >= 0:
                    lines.append("⚠️ RENEWAL APPROACHING - within 90 days")
            if arr is not None:
                lines.append(f"ARR: ${arr:,.0f}" if isinstance(arr, (int, float)) else f"ARR: {arr}")
            if tier:
                lines.append(f"Customer Tier: {tier}")
            if health_status:
                lines.append(f"Account Status: {health_status}")
            if risk_reason:
                lines.append(f"Risk Reason: {risk_reason}")

        # Legacy fields (backwards compatibility)
        if "last_login" in engagement_data:
            lines.append(f"\nLast Login: {engagement_data['last_login']}")
        if "active_users" in engagement_data:
            lines.append(f"Active Users: {engagement_data['active_users']}")
        if "feature_adoption" in engagement_data and not features:
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
   - Churn risk indicators (CRITICAL: if churn date is in the past, contract expired,
     or status is "churned"/"inactive", health MUST be 1-3 max)
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
   - Base calculation: 40% sentiment + 60% health (health is more predictive of churn)
   - Round to nearest integer

   CRITICAL HARD CAPS (these override the weighted average):
   - CONFIRMED CHURN (churn date in the past, contract fully expired, or account status
     contains "churn"/"inactive"/"cancelled"): score MUST be capped at 2, status "critical"
   - CONTRACT EXPIRED (contract end date in the past, or days to renewal is negative):
     score MUST be capped at 3, status "at_risk" or "critical"
   - NEAR-ZERO UTILIZATION (utilization < 5%): apply a penalty of -3 (minimum score 1)
   - Positive sentiment does NOT offset churn. An account with great relationships
     but confirmed churn is still a 1-2, never higher.

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
            name="Account Analysis Crew",
            agents=[account_analyst, synthesis_coach],
            tasks=[analysis_task, synthesis_task],
            verbose=False,
        )

        _emit_progress("Step 3", "Running analysis...")
        result = crew.kickoff()

        _emit_progress("Complete", "Analysis complete!")

        # Parse result
        raw_result = str(result)
        default = {
            "score": 5,
            "status": "stable",
            "trend": "stable",
            "executive_summary": raw_result[:500] if raw_result else "Analysis completed",
            "sentiment_analysis": {"summary": "See executive summary"},
            "health_analysis": {"summary": "See executive summary"},
            "recommended_actions": [],
            "talking_points": [],
            "_raw_result": raw_result,
        }
        parsed = extract_json_from_llm_response(raw_result, default=default)
        parsed["_provider"] = "crewai"
        parsed["_model"] = getattr(self.llm, 'model', 'unknown')
        return parsed
