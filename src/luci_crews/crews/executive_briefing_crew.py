"""
Executive Morning Briefing Crew

Generates a cohesive AI narrative for the top of the Executive Dashboard,
synthesizing macro insights, portfolio trends, key risks, wins, and
recommended actions into an executive-ready briefing.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from crewai import Agent, Task, Crew, Process

from .base_crew import BaseCrew

logger = logging.getLogger(__name__)


class ExecutiveMorningBriefingCrew(BaseCrew):
    """Crew for generating executive morning briefings."""

    needs_supabase = True

    # ─── Data fetching ───────────────────────────────────────────────

    def _fetch_macro_insights(self) -> List[Dict[str, Any]]:
        """Fetch active macro insights from macro_insight_history."""
        if not self.supabase:
            return []
        try:
            result = self.supabase.table("macro_insight_history").select(
                "insight_type, severity, title, narrative, affected_arr, generated_at"
            ).eq("is_active", True).order("severity").limit(10).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching macro insights: {e}")
            return []

    def _fetch_portfolio_snapshots(self) -> Dict[str, Any]:
        """Fetch today's snapshot and compare to 7d/30d ago."""
        if not self.supabase:
            return {}

        snapshots = {
            "today": None,
            "week_ago": None,
            "month_ago": None,
        }

        try:
            today = datetime.utcnow().date()
            week_ago = (today - timedelta(days=7)).isoformat()
            month_ago = (today - timedelta(days=30)).isoformat()

            # Today's snapshot (or most recent)
            result = self.supabase.table("executive_portfolio_snapshot").select(
                "*"
            ).order("snapshot_date", desc=True).limit(1).execute()
            if result.data:
                snapshots["today"] = result.data[0]

            # Week ago
            result = self.supabase.table("executive_portfolio_snapshot").select(
                "*"
            ).lte("snapshot_date", week_ago).order("snapshot_date", desc=True).limit(1).execute()
            if result.data:
                snapshots["week_ago"] = result.data[0]

            # Month ago
            result = self.supabase.table("executive_portfolio_snapshot").select(
                "*"
            ).lte("snapshot_date", month_ago).order("snapshot_date", desc=True).limit(1).execute()
            if result.data:
                snapshots["month_ago"] = result.data[0]

        except Exception as e:
            logger.error(f"Error fetching portfolio snapshots: {e}")

        return snapshots

    def _fetch_critical_renewals(self) -> List[Dict[str, Any]]:
        """Fetch accounts with upcoming critical renewals."""
        if not self.supabase:
            return []
        try:
            # Renewals in next 90 days with health < 7
            today = datetime.utcnow().date().isoformat()
            cutoff = (datetime.utcnow() + timedelta(days=90)).date().isoformat()
            result = self.supabase.table("accounts").select(
                "id, name, contract_value_numeric, health_score, contract_end_date, account_tier, updated_at"
            ).gte("contract_end_date", today).lte(
                "contract_end_date", cutoff
            ).lt("health_score", 5).gt(
                "contract_value_numeric", 0
            ).order(
                "contract_value_numeric", desc=True
            ).limit(10).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching critical renewals: {e}")
            return []

    def _fetch_at_risk_accounts(self) -> List[Dict[str, Any]]:
        """Fetch top at-risk accounts by ARR impact."""
        if not self.supabase:
            return []
        try:
            result = self.supabase.table("accounts").select(
                "id, name, contract_value_numeric, health_score, account_tier, updated_at"
            ).lt("health_score", 5).gt(
                "contract_value_numeric", 0
            ).order(
                "contract_value_numeric", desc=True
            ).limit(10).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching at-risk accounts: {e}")
            return []

    def _fetch_recent_wins(self) -> List[Dict[str, Any]]:
        """Fetch recent expansion wins."""
        if not self.supabase:
            return []
        try:
            week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
            result = self.supabase.table("opportunities").select(
                "name, amount, close_date, accounts(name)"
            ).eq("is_won", True).gte("close_date", week_ago).order(
                "amount", desc=True
            ).limit(5).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching recent wins: {e}")
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

    def _format_macro_insights(self, insights: List[Dict[str, Any]]) -> str:
        """Format macro insights for the prompt."""
        if not insights:
            return "No active systemic risks detected."

        formatted = []
        for i in insights:
            severity = i.get("severity", "unknown").upper()
            title = i.get("title", "Unknown insight")
            arr = self._format_currency(i.get("affected_arr", 0))
            narrative = i.get("narrative", "")[:200]
            formatted.append(f"[{severity}] {title} (ARR impact: {arr})\n   {narrative}")

        return "\n".join(formatted)

    def _format_portfolio_trends(self, snapshots: Dict[str, Any]) -> str:
        """Format portfolio trend comparison."""
        today = snapshots.get("today", {})
        week_ago = snapshots.get("week_ago", {})
        month_ago = snapshots.get("month_ago", {})

        if not today:
            return "No portfolio snapshot available."

        lines = [
            f"Total ARR: {self._format_currency(today.get('total_arr', 0))}",
            f"NRR (T12): {float(today.get('nrr_trailing_12', 0) or 0):.1f}%",
            f"GRR (T12): {float(today.get('grr_trailing_12', 0) or 0):.1f}%",
            f"Pipeline Coverage: {float(today.get('pipeline_coverage', 0) or 0):.1f}x",
            f"Top 10 Concentration: {float(today.get('top10_concentration_pct', 0) or 0):.1f}%",
        ]

        # Add trends
        if week_ago:
            arr_7d_change = float(today.get("total_arr", 0) or 0) - float(week_ago.get("total_arr", 0) or 0)
            lines.append(f"7-day ARR change: {self._format_currency(arr_7d_change)}")

        if month_ago:
            arr_30d_change = float(today.get("total_arr", 0) or 0) - float(month_ago.get("total_arr", 0) or 0)
            lines.append(f"30-day ARR change: {self._format_currency(arr_30d_change)}")

        # Health by tier
        health_by_tier = today.get("avg_health_by_tier", {})
        if health_by_tier:
            tier_lines = [f"  {tier}: {float(score):.1f}" for tier, score in health_by_tier.items()]
            lines.append("Health by Tier:")
            lines.extend(tier_lines)

        return "\n".join(lines)

    def _format_critical_renewals(self, renewals: List[Dict[str, Any]]) -> str:
        """Format critical renewals for the prompt."""
        if not renewals:
            return "No critical renewals in the next 90 days."

        formatted = []
        for r in renewals:
            name = r.get("name", "Unknown")
            arr = self._format_currency(r.get("contract_value_numeric", 0))
            health = float(r.get("health_score", 0) or 0)
            end_date = r.get("contract_end_date", "Unknown")
            formatted.append(f"- {name}: {arr} (health: {health:.1f}, expires: {end_date})")

        return "\n".join(formatted)

    def _format_at_risk_accounts(self, accounts: List[Dict[str, Any]]) -> str:
        """Format at-risk accounts for the prompt."""
        if not accounts:
            return "No accounts currently at critical risk."

        formatted = []
        total_at_risk = 0
        for a in accounts:
            name = a.get("name", "Unknown")
            arr = float(a.get("contract_value_numeric", 0) or 0)
            total_at_risk += arr
            health = a.get("health_score", 0)
            formatted.append(
                f"- {name}: {self._format_currency(arr)} "
                f"(health: {health}/10, tier: {a.get('account_tier', 'Unknown')})"
            )

        header = f"Total ARR at risk: {self._format_currency(total_at_risk)}"
        return header + "\n" + "\n".join(formatted)

    def _format_recent_wins(self, wins: List[Dict[str, Any]]) -> str:
        """Format recent wins for the prompt."""
        if not wins:
            return "No closed-won opportunities in the past 7 days."

        formatted = []
        total_won = 0
        for w in wins:
            name = w.get("name", "Unknown")
            amount = float(w.get("amount", 0) or 0)
            total_won += amount
            account = w.get("accounts", {})
            account_name = account.get("name", "Unknown") if account else "Unknown"
            formatted.append(f"- {name} ({account_name}): {self._format_currency(amount)}")

        header = f"Total won this week: {self._format_currency(total_won)}"
        return header + "\n" + "\n".join(formatted)

    # ─── Agents ──────────────────────────────────────────────────────

    def _create_agents(self) -> None:
        """Create the executive briefing agent."""
        self.briefing_writer = self.create_agent_from_config(
            "executive_briefing_writer",
            role_default="Executive Briefing Writer",
            goal_default=(
                "Synthesize portfolio data into a cohesive, executive-ready morning briefing "
                "that highlights key risks, wins, and recommended actions"
            ),
            backstory_default=(
                "You are a seasoned executive communications specialist with 15 years of "
                "experience crafting daily briefings for C-suite leaders at Fortune 500 "
                "companies. You excel at distilling complex data into clear, actionable "
                "narratives. Your briefings are known for being concise yet comprehensive, "
                "always leading with the most critical information and ending with clear "
                "recommended actions. You never bury the lead."
            ),
        )

    # ─── Tasks ───────────────────────────────────────────────────────

    def _build_briefing_task(
        self,
        macro_insights: str,
        portfolio_trends: str,
        critical_renewals: str,
        at_risk_accounts: str,
        recent_wins: str,
    ) -> Task:
        """Build the briefing generation task."""
        task_config = self._get_task_config("generate_executive_briefing")

        description = task_config.get("description", "") or (
            "Generate an executive morning briefing based on the following portfolio data.\n\n"
            "SYSTEMIC RISKS (Macro Insights):\n{macro_insights}\n\n"
            "PORTFOLIO METRICS & TRENDS:\n{portfolio_trends}\n\n"
            "CRITICAL RENEWALS (next 90 days, health < 7):\n{critical_renewals}\n\n"
            "AT-RISK ACCOUNTS (health < 5):\n{at_risk_accounts}\n\n"
            "RECENT WINS (past 7 days):\n{recent_wins}\n\n"
            "IMPORTANT: All currency values are in US Dollars. Always use the $ symbol, never £ or other currency symbols.\n\n"
            "Create a briefing that includes:\n"
            "1. A headline summarizing portfolio health (e.g., 'Portfolio Health: Caution - 2 systemic risks')\n"
            "2. A 2-3 paragraph narrative that:\n"
            "   - Opens with the current state of the portfolio (ARR, NRR, pipeline coverage)\n"
            "   - Highlights the most critical risks requiring attention\n"
            "   - Acknowledges recent wins to maintain morale\n"
            "   - Uses specific numbers and account names\n"
            "   - IMPORTANT: Always use the exact full account name as provided in the data (e.g. 'Cisco Systems' not 'Cisco', 'Veeam Software Group' not 'Veeam'). This enables clickable links in the UI.\n"
            "3. A structured list of key risks with severity, one-liner description, and affected ARR. Use exact full account names in one-liners.\n"
            "4. A list of key wins with description and ARR impact. Use exact full account names in descriptions.\n"
            "5. 3-5 recommended actions with priority levels and a navigation_target from this list:\n"
            "   - strategic-health:high-risk-accounts-list (for churn/retention/whale account risks)\n"
            "   - strategic-health:critical-renewals-section (for upcoming renewal concerns)\n"
            "   - strategic-health:portfolio-kpis (for ARR/NRR/GRR portfolio metrics)\n"
            "   - strategic-health:health-score-trend (for health score trends)\n"
            "   - growth:customer-concentration (for revenue concentration risks)\n"
            "   - growth:expansion-revenue (for expansion/upsell/cross-sell opportunities)\n"
            "   - growth:revenue-cohorts (for cohort analysis)\n"
            "   - growth:industry-breakdown (for industry-specific actions)\n"
            "   - operations:team-performance (for team workload/capacity)\n"
            "   - operations:action-queue (for data health/action items)\n"
            "   - operations:competitive-intelligence (for competitive intelligence)\n"
            "   - operations:customer-insights (for emerging themes/voice of customer)\n"
            "6. A confidence score (0.0-1.0) based on data completeness\n\n"
            "Output as JSON with this structure:\n"
            "{{\n"
            '  "headline": "Portfolio Health: [status] - [summary]",\n'
            '  "narrative": "Good morning. [2-3 paragraphs]...",\n'
            '  "key_risks": [{{"type": "...", "severity": "critical|high|medium", "one_liner": "...", "affected_arr": 0}}],\n'
            '  "key_wins": [{{"description": "...", "arr_impact": 0}}],\n'
            '  "recommended_actions": [{{"action": "...", "priority": "immediate|this_week|this_month", "navigation_target": "strategic-health:high-risk-accounts", "crew_to_trigger": "optional"}}],\n'
            '  "confidence_score": 0.85\n'
            "}}"
        )

        return Task(
            description=description.format(
                macro_insights=macro_insights,
                portfolio_trends=portfolio_trends,
                critical_renewals=critical_renewals,
                at_risk_accounts=at_risk_accounts,
                recent_wins=recent_wins,
            ),
            expected_output=task_config.get(
                "expected_output",
                "A JSON object containing headline, narrative, key_risks, key_wins, "
                "recommended_actions, and confidence_score for the executive morning briefing."
            ),
            agent=self.briefing_writer,
        )

    # ─── Main run method ─────────────────────────────────────────────

    def run(
        self,
        user_id: Optional[str] = None,
        step_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        Run the executive morning briefing crew.

        Args:
            user_id: Optional user ID for AI settings
            step_callback: Optional progress callback

        Returns:
            Dict with briefing result and metadata
        """
        if step_callback:
            step_callback("Gathering portfolio data...")

        # Track data freshness timestamp
        data_fetched_at = datetime.utcnow().isoformat()

        # Fetch all required data
        macro_insights = self._fetch_macro_insights()
        portfolio_snapshots = self._fetch_portfolio_snapshots()
        critical_renewals = self._fetch_critical_renewals()
        at_risk_accounts = self._fetch_at_risk_accounts()
        recent_wins = self._fetch_recent_wins()

        # Calculate data_as_of from MAX(updated_at) across fetched accounts
        all_updated_at = []
        for r in critical_renewals:
            if r.get("updated_at"):
                all_updated_at.append(r.get("updated_at"))
        for a in at_risk_accounts:
            if a.get("updated_at"):
                all_updated_at.append(a.get("updated_at"))
        data_as_of = max(all_updated_at) if all_updated_at else data_fetched_at

        if step_callback:
            step_callback("Formatting data for analysis...")

        # Format data for the prompt
        macro_insights_str = self._format_macro_insights(macro_insights)
        portfolio_trends_str = self._format_portfolio_trends(portfolio_snapshots)
        critical_renewals_str = self._format_critical_renewals(critical_renewals)
        at_risk_accounts_str = self._format_at_risk_accounts(at_risk_accounts)
        recent_wins_str = self._format_recent_wins(recent_wins)

        if step_callback:
            step_callback("Creating briefing writer agent...")

        # Create agents
        self._create_agents()

        # Build task
        task = self._build_briefing_task(
            macro_insights_str,
            portfolio_trends_str,
            critical_renewals_str,
            at_risk_accounts_str,
            recent_wins_str,
        )

        if step_callback:
            step_callback("Generating executive briefing...")

        # Run the crew
        crew = Crew(
            name="Executive Morning Briefing Crew",
            agents=[self.briefing_writer],
            tasks=[task],
            process=Process.sequential,
            verbose=False,
        )

        result = crew.kickoff()
        result_text = str(result)

        if step_callback:
            step_callback("Parsing briefing results...")

        # Parse the JSON result
        parsed_result = self._parse_json_result(
            result_text,
            default={
                "headline": "Portfolio Health: Data Unavailable",
                "narrative": result_text[:500] if result_text else "Unable to generate briefing.",
                "key_risks": [],
                "key_wins": [],
                "recommended_actions": [],
                "confidence_score": 0.0,
            }
        )

        # Get model info
        model_name = getattr(self.llm, "model", "unknown")
        provider = "openai"
        if "claude" in model_name.lower() or "anthropic" in model_name.lower():
            provider = "anthropic"
        elif "gemini" in model_name.lower():
            provider = "google"

        return {
            "success": True,
            "headline": parsed_result.get("headline"),
            "narrative": parsed_result.get("narrative"),
            "key_risks": parsed_result.get("key_risks", []),
            "key_wins": parsed_result.get("key_wins", []),
            "recommended_actions": parsed_result.get("recommended_actions", []),
            "confidence_score": parsed_result.get("confidence_score", 0.0),
            "generated_at": datetime.utcnow().isoformat(),
            "data_as_of": data_as_of,
            "provider": provider,
            "model": model_name,
            "data_summary": {
                "macro_insights_count": len(macro_insights),
                "critical_renewals_count": len(critical_renewals),
                "at_risk_accounts_count": len(at_risk_accounts),
                "recent_wins_count": len(recent_wins),
            },
        }
