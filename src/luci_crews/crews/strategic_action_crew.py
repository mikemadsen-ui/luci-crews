"""
Strategic Action Crew

Generates executive-ready strategic documents on demand:
- Board-ready quarterly summaries
- Pipeline gap directives to VP Sales
- Segment deep dives with win/loss patterns
- Whale account churn prevention plans
- Competitive response syntheses
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from crewai import Agent, Task, Crew, Process

from .base_crew import BaseCrew

logger = logging.getLogger(__name__)

# Supported action types
ACTION_TYPES = {
    "board_summary",
    "pipeline_directive",
    "segment_deep_dive",
    "churn_prevention_plan",
    "competitive_response",
}


class StrategicActionCrew(BaseCrew):
    """Crew for generating executive strategic documents."""

    needs_supabase = True

    # ─── Data fetching ───────────────────────────────────────────────

    def _fetch_portfolio_snapshot(self, days_back: int = 90) -> List[Dict[str, Any]]:
        """Fetch recent portfolio snapshots for trend data."""
        if not self.supabase:
            return []
        try:
            cutoff = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
            result = self.supabase.table("executive_portfolio_snapshot").select(
                "*"
            ).gte("snapshot_date", cutoff).order("snapshot_date", desc=True).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching portfolio snapshots: {e}")
            return []

    def _fetch_macro_insights(self) -> List[Dict[str, Any]]:
        """Fetch active macro insights."""
        if not self.supabase:
            return []
        try:
            result = self.supabase.table("macro_insight_history").select(
                "*"
            ).eq("is_active", True).order("severity").execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching macro insights: {e}")
            return []

    def _fetch_accounts_summary(self) -> List[Dict[str, Any]]:
        """Fetch top accounts with health and contract data."""
        if not self.supabase:
            return []
        try:
            result = self.supabase.table("accounts").select(
                "id, name, account_tier, contract_value, health_score, "
                "contract_end_date, industry, owner_name, utilization_pct, "
                "days_since_last_touch"
            ).order("contract_value", desc=True).limit(50).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching accounts summary: {e}")
            return []

    def _fetch_opportunities(self, segment: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch pipeline opportunities, optionally filtered by segment."""
        if not self.supabase:
            return []
        try:
            query = self.supabase.table("opportunities").select(
                "id, name, amount, stage_name, close_date, probability, "
                "is_closed, is_won, account_tier, meddpic_score"
            ).eq("is_closed", False)
            if segment:
                query = query.eq("account_tier", segment)
            result = query.order("amount", desc=True).limit(100).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching opportunities: {e}")
            return []

    def _fetch_renewal_arr_history(self, months_back: int = 12) -> List[Dict[str, Any]]:
        """Fetch renewal ARR history for NRR/GRR calculation."""
        if not self.supabase:
            return []
        try:
            cutoff = (datetime.utcnow() - timedelta(days=months_back * 30)).strftime("%Y-%m-%d")
            result = self.supabase.table("renewal_arr_history").select(
                "account_name, arr, previous_arr, arr_change, renewal_date, is_won"
            ).gte("renewal_date", cutoff).order("renewal_date", desc=True).limit(200).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching renewal ARR history: {e}")
            return []

    def _fetch_competitive_intel(self) -> List[Dict[str, Any]]:
        """Fetch competitive intelligence summary."""
        if not self.supabase:
            return []
        try:
            result = self.supabase.table("competitive_intelligence_summary").select(
                "*"
            ).order("mention_count", desc=True).limit(20).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching competitive intel: {e}")
            return []

    def _fetch_account_detail(self, account_id: str) -> Dict[str, Any]:
        """Fetch detailed data for a specific account (churn prevention)."""
        if not self.supabase:
            return {}
        try:
            result = self.supabase.table("accounts").select("*").eq(
                "id", account_id
            ).limit(1).execute()
            if result.data:
                return result.data[0]
            return {}
        except Exception as e:
            logger.error(f"Error fetching account detail: {e}")
            return {}

    def _fetch_account_cases(self, salesforce_account_id: str) -> List[Dict[str, Any]]:
        """Fetch recent support cases for an account."""
        if not self.supabase or not salesforce_account_id:
            return []
        try:
            result = self.supabase.table("cases").select(
                "case_number, subject, status, priority, created_date"
            ).eq("salesforce_account_id", salesforce_account_id).order(
                "created_date", desc=True
            ).limit(20).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching account cases: {e}")
            return []

    def _fetch_account_health_history(self, account_id: str) -> List[Dict[str, Any]]:
        """Fetch health analysis history for an account."""
        if not self.supabase:
            return []
        try:
            result = self.supabase.table("crew_analysis_history").select(
                "crew_type, analysis_data, created_at"
            ).eq("account_id", account_id).order(
                "created_at", desc=True
            ).limit(10).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching health history: {e}")
            return []

    # ─── Data formatting ─────────────────────────────────────────────

    def _format_currency(self, value: Any) -> str:
        """Format a numeric value as currency."""
        try:
            v = float(value) if value else 0
        except (TypeError, ValueError):
            return "$0"
        if v >= 1_000_000:
            return f"${v / 1_000_000:.1f}M"
        if v >= 1_000:
            return f"${v / 1_000:.0f}K"
        return f"${v:.0f}"

    def _format_context(self, data: Any) -> str:
        """Format arbitrary data into a prompt-friendly string."""
        if not data:
            return "No data available."
        if isinstance(data, list):
            if not data:
                return "No data available."
            import json
            return json.dumps(data[:30], indent=2, default=str)
        if isinstance(data, dict):
            import json
            return json.dumps(data, indent=2, default=str)
        return str(data)

    # ─── Agents ──────────────────────────────────────────────────────

    def _create_agents(self) -> None:
        """Create the strategic action agents."""
        self.strategist = self.create_agent_from_config(
            "strategic_action_strategist",
            role_default="Chief Strategy Analyst",
            goal_default=(
                "Synthesize portfolio data into executive-ready strategic documents "
                "with clear recommendations and actionable next steps"
            ),
            backstory_default=(
                "You are a seasoned B2B SaaS strategy consultant with 20 years of experience "
                "advising C-suite executives. You excel at distilling complex data into "
                "compelling narratives with precise recommendations. You think in terms of "
                "ARR impact, retention levers, and competitive positioning. Your documents "
                "are known for being concise, data-backed, and immediately actionable."
            ),
        )

    # ─── Task builders (one per action type) ─────────────────────────

    def _build_board_summary_task(
        self,
        snapshots: str,
        macro_insights: str,
        accounts: str,
        renewals: str,
        competitive: str,
        quarter: str,
    ) -> Task:
        """Build the board summary generation task."""
        task_config = self._get_task_config("strategic_board_summary")
        description = task_config.get("description", "") or (
            f"Generate a board-ready quarterly summary for {quarter}.\n\n"
            "PORTFOLIO SNAPSHOTS (trend data):\n{snapshots}\n\n"
            "ACTIVE SYSTEMIC RISKS:\n{macro_insights}\n\n"
            "TOP ACCOUNTS:\n{accounts}\n\n"
            "RENEWAL HISTORY (12 months):\n{renewals}\n\n"
            "COMPETITIVE INTELLIGENCE:\n{competitive}\n\n"
            "Generate a structured executive document with:\n"
            "1. Executive Summary (3-4 sentences)\n"
            "2. ARR & Revenue Performance (with NRR/GRR trends)\n"
            "3. Portfolio Health Assessment (by tier)\n"
            "4. Key Risks & Mitigations\n"
            "5. Competitive Landscape\n"
            "6. Strategic Recommendations (3-5 actionable items)\n"
            "7. Outlook for next quarter\n\n"
            "Use specific numbers and percentages. This goes to the board."
        )

        return Task(
            description=description.format(
                quarter=quarter,
                snapshots=snapshots,
                macro_insights=macro_insights,
                accounts=accounts,
                renewals=renewals,
                competitive=competitive,
            ),
            expected_output=task_config.get(
                "expected_output",
                "A structured board-ready quarterly summary in markdown with sections "
                "for executive summary, revenue performance, health assessment, risks, "
                "competitive landscape, recommendations, and outlook."
            ),
            agent=self.strategist,
        )

    def _build_pipeline_directive_task(
        self,
        snapshots: str,
        opportunities: str,
        macro_insights: str,
        quarter: str,
    ) -> Task:
        """Build the pipeline directive task."""
        task_config = self._get_task_config("strategic_pipeline_directive")
        description = task_config.get("description", "") or (
            f"Draft a directive from the CRO/CEO to the VP of Sales regarding "
            f"pipeline gaps for {quarter}.\n\n"
            "PORTFOLIO TRENDS:\n{snapshots}\n\n"
            "CURRENT PIPELINE:\n{opportunities}\n\n"
            "SYSTEMIC RISKS:\n{macro_insights}\n\n"
            "The directive should:\n"
            "1. State the problem clearly (pipeline coverage, gap to target)\n"
            "2. Quantify the gap in dollars and coverage ratio\n"
            "3. Identify root causes (conversion rates, deal velocity, sourcing)\n"
            "4. Provide 3-5 specific directives with owners and deadlines\n"
            "5. Set clear expectations for weekly reporting\n\n"
            "Tone: Direct, urgent but professional. This is an internal memo."
        )

        return Task(
            description=description.format(
                quarter=quarter,
                snapshots=snapshots,
                opportunities=opportunities,
                macro_insights=macro_insights,
            ),
            expected_output=task_config.get(
                "expected_output",
                "An executive directive memo in markdown format addressed to VP Sales "
                "with quantified pipeline gaps, root causes, and numbered directives."
            ),
            agent=self.strategist,
        )

    def _build_segment_deep_dive_task(
        self,
        segment: str,
        accounts: str,
        opportunities: str,
        renewals: str,
    ) -> Task:
        """Build the segment deep dive task."""
        task_config = self._get_task_config("strategic_segment_deep_dive")
        description = task_config.get("description", "") or (
            f"Perform a deep-dive analysis of the {segment} segment.\n\n"
            "ACCOUNTS IN SEGMENT:\n{accounts}\n\n"
            "PIPELINE IN SEGMENT:\n{opportunities}\n\n"
            "RENEWAL HISTORY:\n{renewals}\n\n"
            "Analyze:\n"
            "1. Segment Overview (account count, total ARR, avg health)\n"
            "2. Win/Loss Patterns (win rate, avg deal size, sales cycle)\n"
            "3. Retention Performance (NRR, GRR, churn rate)\n"
            "4. Health Distribution (healthy vs at-risk vs critical)\n"
            "5. Top Risks in This Segment\n"
            "6. Expansion Opportunities\n"
            "7. Recommendations for Segment Strategy\n\n"
            "Include specific account names where relevant."
        )

        return Task(
            description=description.format(
                segment=segment,
                accounts=accounts,
                opportunities=opportunities,
                renewals=renewals,
            ),
            expected_output=task_config.get(
                "expected_output",
                "A comprehensive segment analysis in markdown with performance metrics, "
                "win/loss patterns, risk assessment, and strategic recommendations."
            ),
            agent=self.strategist,
        )

    def _build_churn_prevention_task(
        self,
        account_detail: str,
        health_history: str,
        cases: str,
        macro_insights: str,
    ) -> Task:
        """Build the churn prevention plan task."""
        task_config = self._get_task_config("strategic_churn_prevention")
        description = task_config.get("description", "") or (
            "Create an executive-level churn prevention plan for this account.\n\n"
            "ACCOUNT DETAILS:\n{account_detail}\n\n"
            "HEALTH ANALYSIS HISTORY:\n{health_history}\n\n"
            "SUPPORT CASES:\n{cases}\n\n"
            "RELATED MACRO RISKS:\n{macro_insights}\n\n"
            "The save plan should include:\n"
            "1. Situation Assessment (why is this account at risk)\n"
            "2. Revenue Impact (ARR at risk, downstream effects)\n"
            "3. Root Cause Analysis (product, service, relationship, competitive)\n"
            "4. Recommended Interventions (immediate, 30-day, 60-day)\n"
            "5. Executive Engagement Plan (who should contact whom)\n"
            "6. Success Criteria (how we know the save is working)\n"
            "7. Escalation Path if interventions fail\n\n"
            "Be specific. Name the people, the actions, the timeline."
        )

        return Task(
            description=description.format(
                account_detail=account_detail,
                health_history=health_history,
                cases=cases,
                macro_insights=macro_insights,
            ),
            expected_output=task_config.get(
                "expected_output",
                "A detailed churn prevention plan in markdown with situation assessment, "
                "revenue impact, root causes, phased interventions, and escalation path."
            ),
            agent=self.strategist,
        )

    def _build_competitive_response_task(
        self,
        competitive: str,
        accounts: str,
        macro_insights: str,
    ) -> Task:
        """Build the competitive response task."""
        task_config = self._get_task_config("strategic_competitive_response")
        description = task_config.get("description", "") or (
            "Synthesize competitive intelligence and create a strategic response plan.\n\n"
            "COMPETITIVE INTELLIGENCE:\n{competitive}\n\n"
            "PORTFOLIO OVERVIEW:\n{accounts}\n\n"
            "SYSTEMIC RISKS:\n{macro_insights}\n\n"
            "The response should include:\n"
            "1. Competitive Landscape Summary (who's mentioned, frequency, threat level)\n"
            "2. Accounts at Competitive Risk (where competitors are actively engaged)\n"
            "3. Competitive Differentiators (our strengths to emphasize)\n"
            "4. Vulnerability Assessment (where we're weakest)\n"
            "5. Strategic Response Playbook (defensive + offensive moves)\n"
            "6. Resource Recommendations (where to invest)\n\n"
            "Focus on actionable intelligence, not generic advice."
        )

        return Task(
            description=description.format(
                competitive=competitive,
                accounts=accounts,
                macro_insights=macro_insights,
            ),
            expected_output=task_config.get(
                "expected_output",
                "A competitive response strategy in markdown with landscape analysis, "
                "at-risk accounts, differentiators, vulnerabilities, and playbook."
            ),
            agent=self.strategist,
        )

    # ─── Main run method ─────────────────────────────────────────────

    def run(
        self,
        action_type: str,
        user_id: Optional[str] = None,
        segment: Optional[str] = None,
        account_id: Optional[str] = None,
        quarter: Optional[str] = None,
        step_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        Run the strategic action crew to generate an executive document.

        Args:
            action_type: One of: board_summary, pipeline_directive,
                segment_deep_dive, churn_prevention_plan, competitive_response
            user_id: Optional user ID for AI settings
            segment: Segment name for segment_deep_dive (e.g., "Enterprise")
            account_id: Account UUID for churn_prevention_plan
            quarter: Quarter label (e.g., "Q1 2026") for board_summary/pipeline_directive
            step_callback: Optional progress callback

        Returns:
            Dict with generated document and metadata
        """
        if action_type not in ACTION_TYPES:
            return {
                "success": False,
                "error": f"Invalid action_type: {action_type}. Must be one of: {ACTION_TYPES}",
            }

        if not quarter:
            now = datetime.utcnow()
            q = (now.month - 1) // 3 + 1
            quarter = f"Q{q} {now.year}"

        if step_callback:
            step_callback(f"Preparing {action_type.replace('_', ' ')}...")

        # Create agents
        self._create_agents()

        # Fetch data based on action type
        if step_callback:
            step_callback("Gathering portfolio data...")

        task = self._build_task_for_action(action_type, segment, account_id, quarter, step_callback)

        if step_callback:
            step_callback("Generating strategic document...")

        # Run the crew
        crew = Crew(
            name="Strategic Action Crew",
            agents=[self.strategist],
            tasks=[task],
            process=Process.sequential,
            verbose=False,
        )

        result = crew.kickoff()
        result_text = str(result)

        if step_callback:
            step_callback("Document complete.")

        # Get model info
        model_name = getattr(self.llm, "model", "unknown")
        provider = "openai"
        if "claude" in model_name.lower() or "anthropic" in model_name.lower():
            provider = "anthropic"
        elif "gemini" in model_name.lower():
            provider = "google"

        return {
            "success": True,
            "document": result_text,
            "action_type": action_type,
            "quarter": quarter,
            "segment": segment,
            "account_id": account_id,
            "provider": provider,
            "model": model_name,
            "generated_at": datetime.utcnow().isoformat(),
        }

    def _build_task_for_action(
        self,
        action_type: str,
        segment: Optional[str],
        account_id: Optional[str],
        quarter: str,
        step_callback: Optional[callable],
    ) -> Task:
        """Build the appropriate task based on action type."""

        if action_type == "board_summary":
            snapshots = self._format_context(self._fetch_portfolio_snapshot())
            macro_insights = self._format_context(self._fetch_macro_insights())
            accounts = self._format_context(self._fetch_accounts_summary())
            renewals = self._format_context(self._fetch_renewal_arr_history())
            competitive = self._format_context(self._fetch_competitive_intel())

            if step_callback:
                step_callback("Building board summary...")

            return self._build_board_summary_task(
                snapshots, macro_insights, accounts, renewals, competitive, quarter
            )

        elif action_type == "pipeline_directive":
            snapshots = self._format_context(self._fetch_portfolio_snapshot(days_back=30))
            opportunities = self._format_context(self._fetch_opportunities())
            macro_insights = self._format_context(self._fetch_macro_insights())

            if step_callback:
                step_callback("Analyzing pipeline gaps...")

            return self._build_pipeline_directive_task(
                snapshots, opportunities, macro_insights, quarter
            )

        elif action_type == "segment_deep_dive":
            seg = segment or "Enterprise"
            accounts = self._format_context(self._fetch_accounts_summary())
            opportunities = self._format_context(self._fetch_opportunities(segment=seg))
            renewals = self._format_context(self._fetch_renewal_arr_history())

            if step_callback:
                step_callback(f"Deep diving into {seg} segment...")

            return self._build_segment_deep_dive_task(
                seg, accounts, opportunities, renewals
            )

        elif action_type == "churn_prevention_plan":
            if not account_id:
                raise ValueError("account_id is required for churn_prevention_plan")

            account_detail = self._format_context(self._fetch_account_detail(account_id))
            health_history = self._format_context(self._fetch_account_health_history(account_id))

            # Get salesforce ID for case lookup
            acct = self._fetch_account_detail(account_id)
            sf_id = acct.get("salesforce_id", "")
            cases = self._format_context(self._fetch_account_cases(sf_id))
            macro_insights = self._format_context(self._fetch_macro_insights())

            if step_callback:
                step_callback(f"Building save plan for {acct.get('name', 'account')}...")

            return self._build_churn_prevention_task(
                account_detail, health_history, cases, macro_insights
            )

        elif action_type == "competitive_response":
            competitive = self._format_context(self._fetch_competitive_intel())
            accounts = self._format_context(self._fetch_accounts_summary())
            macro_insights = self._format_context(self._fetch_macro_insights())

            if step_callback:
                step_callback("Synthesizing competitive intelligence...")

            return self._build_competitive_response_task(
                competitive, accounts, macro_insights
            )

        else:
            raise ValueError(f"Unsupported action_type: {action_type}")
