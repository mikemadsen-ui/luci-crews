"""
Expansion Specialist Crew

Identifies and scores expansion opportunities by analyzing seat utilization,
usage velocity, feature adoption, and ARR growth trends. Deprioritizes support
ticket volume in favor of ROI data and engagement signals.

Branched from RenewalReadinessCrew pattern.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from crewai import Agent, Task, Crew, Process

from ..config_store import get_supabase
from .base_crew import BaseCrew
from ..utils.data_freshness import calculate_data_freshness, extract_sync_timestamps

logger = logging.getLogger(__name__)


class ExpansionSpecialistCrew(BaseCrew):
    """Crew for identifying and scoring expansion opportunities."""

    needs_supabase = True

    def _fetch_account_data(self, account_id: str) -> Dict[str, Any]:
        """Fetch core account data."""
        if not self.supabase:
            return {}

        try:
            result = self.supabase.table("accounts").select(
                "id, name, salesforce_id, industry, account_tier, "
                "contract_value_numeric, annual_revenue, contract_end_date, "
                "customer_start_date, health_score, updated_at, last_synced_at"
            ).eq("id", account_id).limit(1).execute()
            return result.data[0] if result.data else {}
        except Exception as e:
            logger.error(f"Error fetching account data: {e}")
            return {}

    def _fetch_usage_data(self, account_id: str, salesforce_account_id: str) -> Dict[str, Any]:
        """Fetch product usage and seat utilization metrics."""
        if not self.supabase:
            return {}

        try:
            result = None
            if salesforce_account_id:
                result = self.supabase.table("account_product_usage").select(
                    "utilization_pct, adoption_score, health_grade, "
                    "contracted_seats, active_users_90d, active_users_30d, "
                    "routing_objects, unique_nodes, integration_count"
                ).eq("salesforce_account_id", salesforce_account_id).limit(1).execute()

            if not result or not result.data:
                result = self.supabase.table("account_product_usage").select(
                    "utilization_pct, adoption_score, health_grade, "
                    "contracted_seats, active_users_90d, active_users_30d, "
                    "routing_objects, unique_nodes, integration_count"
                ).eq("account_id", account_id).limit(1).execute()

            if result and result.data:
                return {"usage": result.data[0]}
            return {"message": "No usage data available."}
        except Exception as e:
            logger.error(f"Error fetching usage data: {e}")
            return {}

    def _fetch_arr_history(self, salesforce_account_id: str) -> List[Dict[str, Any]]:
        """Fetch renewal ARR history for expansion trend analysis."""
        if not self.supabase or not salesforce_account_id:
            return []

        try:
            result = self.supabase.table("renewal_arr_history").select(
                "arr, previous_arr, arr_change, is_won, close_date, fiscal_year"
            ).eq("salesforce_account_id", salesforce_account_id).order(
                "close_date", desc=True
            ).limit(10).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching ARR history: {e}")
            return []

    def _fetch_health_score_data(self, account_id: str) -> Dict[str, Any]:
        """Fetch health score from latest crew analysis."""
        if not self.supabase:
            return {}

        try:
            result = self.supabase.table("crew_analysis_history").select(
                "result, analyzed_at"
            ).eq("account_id", account_id).eq(
                "crew_type", "sentiment"
            ).order("analyzed_at", desc=True).limit(1).execute()

            if result.data:
                import json
                raw = result.data[0].get("result", "{}")
                parsed = json.loads(raw) if isinstance(raw, str) else raw
                return {
                    "current": {
                        "health_score": parsed.get("score", "N/A"),
                        "trend": parsed.get("trend", "Unknown"),
                        "summary": parsed.get("summary", ""),
                    },
                    "analyzed_at": result.data[0].get("analyzed_at"),
                }
            return {}
        except Exception as e:
            logger.error(f"Error fetching health score data: {e}")
            return {}

    def _fetch_engagement_data(self, salesforce_account_id: str) -> Dict[str, Any]:
        """Fetch engagement gap data."""
        if not self.supabase or not salesforce_account_id:
            return {}

        try:
            cutoff_30 = (datetime.utcnow() - timedelta(days=30)).isoformat()
            cutoff_90 = (datetime.utcnow() - timedelta(days=90)).isoformat()

            recent = self.supabase.table("transcriptions").select(
                "id", count="exact"
            ).eq("salesforce_account_id", salesforce_account_id).gte(
                "meeting_date", cutoff_30
            ).execute()

            older = self.supabase.table("transcriptions").select(
                "id", count="exact"
            ).eq("salesforce_account_id", salesforce_account_id).gte(
                "meeting_date", cutoff_90
            ).lt("meeting_date", cutoff_30).execute()

            return {
                "meetings_last_30_days": recent.count or 0,
                "meetings_30_to_90_days": older.count or 0,
            }
        except Exception as e:
            logger.error(f"Error fetching engagement data: {e}")
            return {}

    def _fetch_stakeholder_map(self, salesforce_account_id: str) -> List[Dict[str, Any]]:
        """Fetch stakeholder/contact information."""
        if not self.supabase or not salesforce_account_id:
            return []

        try:
            result = self.supabase.table("contacts").select(
                "name, title, email"
            ).eq("salesforce_account_id", salesforce_account_id).limit(20).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching stakeholder map: {e}")
            return []

    def _fetch_commercial_insights(self, account_id: str) -> List[Dict[str, Any]]:
        """
        Fetch commercial category insights from insight_history.

        These are expansion-specific signals like:
        - limit_reached: Customer at or exceeding contracted capacity
        - high_usage_velocity: Usage growth signals imminent capacity need
        - seat_expansion_ready: Clear expansion opportunity identified
        - upcoming_renewal_with_growth: Renewal window with expansion potential
        - feature_adoption_spike: New feature adoption unlocking upsell opportunity
        """
        if not self.supabase:
            return []

        try:
            # Fetch commercial insights from last 90 days
            cutoff = (datetime.utcnow() - timedelta(days=90)).isoformat()

            result = self.supabase.table("insight_history").select(
                "insight_type, title, message, severity, created_at, status"
            ).eq("account_id", account_id).eq(
                "category", "commercial"
            ).gte("created_at", cutoff).order(
                "created_at", desc=True
            ).limit(10).execute()

            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching commercial insights: {e}")
            return []

    def _fetch_contract_value(self, account_id: str) -> float:
        """Fetch numeric contract value for ROI calculations."""
        if not self.supabase:
            return 0.0

        try:
            result = self.supabase.table("accounts").select(
                "contract_value_numeric"
            ).eq("id", account_id).limit(1).execute()

            if result.data and result.data[0].get("contract_value_numeric"):
                return float(result.data[0]["contract_value_numeric"])
            return 0.0
        except Exception as e:
            logger.error(f"Error fetching contract value: {e}")
            return 0.0

    # ── Formatters ──────────────────────────────────────────────────────────

    def _format_seat_utilization_context(self, data: Dict[str, Any]) -> str:
        """
        Format seat utilization as a commercial intelligence briefing.
        Maps active_users vs total_seats for the expansion analyst.
        """
        if not data:
            return "No seat utilization data available."

        usage = data.get("usage", {})
        if not usage:
            return "No seat utilization data available."

        contracted = usage.get("contracted_seats") or 0
        active_90 = usage.get("active_users_90d") or 0
        active_30 = usage.get("active_users_30d") or 0

        if contracted == 0:
            return "Contracted seats: Unknown (cannot calculate utilization)"

        # Calculate key metrics
        utilization_pct = round((active_90 / contracted) * 100, 1) if contracted > 0 else 0
        headroom = contracted - active_90
        in_overage = active_90 > contracted
        at_capacity = utilization_pct >= 85

        # Calculate growth velocity (30d vs 90d)
        growth_30d = active_30 - (active_90 - active_30) if active_90 > 0 else 0

        lines = [
            "┌─────────────────────────────────────────────────────────────────┐",
            f"│  CONTRACTED SEATS:    {contracted:>6}                                │",
            f"│  ACTIVE USERS (90d):  {active_90:>6}                                │",
            f"│  ACTIVE USERS (30d):  {active_30:>6}                                │",
            f"│  UTILIZATION:         {utilization_pct:>6.1f}%                              │",
            f"│  HEADROOM:            {headroom:>6} seats                          │",
            "└─────────────────────────────────────────────────────────────────┘",
        ]

        # Add status flags
        if in_overage:
            overage_count = active_90 - contracted
            lines.append(f"🚨 IN OVERAGE: {overage_count} users above contracted limit")
            lines.append("   → Immediate overage cost impact")
            lines.append("   → Expansion conversation is URGENT")
        elif at_capacity:
            lines.append(f"⚠️  AT CAPACITY: Only {headroom} seats remaining")
            lines.append("   → Expansion conversation warranted NOW")
            lines.append("   → Proactive upgrade saves vs. reactive overage")
        elif utilization_pct >= 70:
            lines.append(f"📈 APPROACHING CAPACITY: {headroom} seats remaining")
            lines.append("   → Plan expansion conversation for next QBR")

        # Growth velocity
        if active_30 > 0 and active_90 > active_30:
            monthly_growth_rate = round(((active_30 / (active_90 - active_30 + 0.1)) - 1) * 100, 1)
            if monthly_growth_rate > 10:
                lines.append(f"🚀 HIGH GROWTH: ~{monthly_growth_rate}% monthly user growth")

        return "\n".join(lines)

    def _format_usage_data(self, data: Dict[str, Any]) -> str:
        if not data or data.get("message"):
            return data.get("message", "No usage data available.")

        usage = data.get("usage", {})
        if not usage:
            return "No usage metrics recorded."

        parts = []
        if usage.get("utilization_pct") is not None:
            parts.append(f"Platform Utilization: {usage['utilization_pct']}%")
        if usage.get("adoption_score") is not None:
            parts.append(f"Adoption Score: {usage['adoption_score']}")
        if usage.get("health_grade"):
            parts.append(f"Health Grade: {usage['health_grade']}")
        if usage.get("routing_objects") is not None:
            parts.append(f"Routing Objects: {usage['routing_objects']}")
        if usage.get("unique_nodes") is not None:
            parts.append(f"Unique Nodes: {usage['unique_nodes']}")
        if usage.get("integration_count") is not None:
            parts.append(f"Active Integrations: {usage['integration_count']}")

        return "\n".join(parts) if parts else "No usage data available."

    def _format_arr_history(self, renewals: List[Dict[str, Any]]) -> str:
        if not renewals:
            return "No renewal ARR history available."

        parts = [f"Renewal history ({len(renewals)} records):"]
        total_expansion = 0
        total_contraction = 0

        for r in renewals:
            change = r.get("arr_change") or 0
            arr = r.get("arr") or 0
            close = r.get("close_date", "Unknown")
            won = "Won" if r.get("is_won") else "Lost"
            direction = "expansion" if change > 0 else ("contraction" if change < 0 else "flat")
            parts.append(f"  {close}: ${arr:,.0f} ARR ({direction}: ${change:+,.0f}) [{won}]")

            if change > 0:
                total_expansion += change
            elif change < 0:
                total_contraction += change

        parts.append(f"\nTotal expansion: ${total_expansion:,.0f}")
        parts.append(f"Total contraction: ${total_contraction:,.0f}")
        parts.append(f"Net movement: ${total_expansion + total_contraction:+,.0f}")

        return "\n".join(parts)

    def _format_health_score_data(self, data: Dict[str, Any]) -> str:
        if not data:
            return "No health score data available."

        parts = []
        current = data.get("current", {})
        if current:
            parts.append(f"Current Score: {current.get('health_score', 'N/A')}")
            parts.append(f"Trend: {current.get('trend', 'Unknown')}")
            summary = current.get("summary", "")
            if summary:
                parts.append(f"Summary: {summary[:200]}")

        analyzed_at = data.get("analyzed_at")
        if analyzed_at:
            parts.append(f"Last analyzed: {analyzed_at}")

        return "\n".join(parts) if parts else "No health data available."

    def _format_engagement_data(self, data: Dict[str, Any]) -> str:
        if not data:
            return "No engagement data available."

        recent = data.get("meetings_last_30_days", 0)
        older = data.get("meetings_30_to_90_days", 0)

        parts = [
            f"Meetings in last 30 days: {recent}",
            f"Meetings 30-90 days ago: {older}",
        ]

        if recent > older:
            parts.append("Positive: Engagement is increasing.")
        elif recent < older / 2:
            parts.append("Note: Engagement has declined — may affect expansion timing.")

        return "\n".join(parts)

    def _format_stakeholder_map(self, contacts: List[Dict[str, Any]]) -> str:
        if not contacts:
            return "No stakeholder data available."

        formatted = [f"Total contacts: {len(contacts)}"]
        formatted.append("\nKey Contacts:")
        for contact in contacts[:10]:
            formatted.append(
                f"  - {contact.get('name', 'Unknown')} ({contact.get('title', 'Unknown title')})"
            )

        return "\n".join(formatted)

    def _format_commercial_insights(self, insights: List[Dict[str, Any]]) -> str:
        """Format commercial insights for LLM context."""
        if not insights:
            return "No commercial signals detected in the last 90 days."

        # Group by severity
        critical = [i for i in insights if i.get("severity") == "critical"]
        high = [i for i in insights if i.get("severity") == "high"]
        medium = [i for i in insights if i.get("severity") in ("medium", "low")]

        lines = [f"📊 {len(insights)} Commercial Signals Detected:\n"]

        if critical:
            lines.append("🔴 CRITICAL SIGNALS:")
            for insight in critical:
                lines.append(f"  • [{insight.get('insight_type', 'unknown')}] {insight.get('title', 'No title')}")
                lines.append(f"    → {insight.get('message', '')[:200]}")
            lines.append("")

        if high:
            lines.append("🟠 HIGH PRIORITY SIGNALS:")
            for insight in high:
                lines.append(f"  • [{insight.get('insight_type', 'unknown')}] {insight.get('title', 'No title')}")
                lines.append(f"    → {insight.get('message', '')[:200]}")
            lines.append("")

        if medium:
            lines.append("🟡 MODERATE SIGNALS:")
            for insight in medium[:5]:  # Limit to prevent context bloat
                lines.append(f"  • [{insight.get('insight_type', 'unknown')}] {insight.get('title', 'No title')}")

        return "\n".join(lines)

    def _calculate_roi_context(
        self,
        current_arr: float,
        usage_data: Dict[str, Any],
        insights: List[Dict[str, Any]],
    ) -> str:
        """
        Calculate ROI context for expansion analysis.

        Uses contract_value_numeric and seat utilization to quantify:
        - Overage cost avoidance
        - Expansion lift potential
        - Proactive upgrade savings
        """
        lines = ["┌─────────────────────────────────────────────────────────────────┐"]
        lines.append(f"│  CURRENT CONTRACT VALUE:  ${current_arr:>12,.0f}                  │")

        usage = usage_data.get("usage", {}) if usage_data else {}
        contracted = usage.get("contracted_seats") or 0
        active_90 = usage.get("active_users_90d") or 0

        # Calculate per-seat economics
        if contracted > 0 and current_arr > 0:
            price_per_seat = current_arr / contracted
            lines.append(f"│  PRICE PER SEAT:          ${price_per_seat:>12,.0f}                  │")

            # Overage scenario
            if active_90 > contracted:
                overage_seats = active_90 - contracted
                overage_cost_annual = overage_seats * price_per_seat * 1.25  # 25% overage premium
                lines.append(f"│  OVERAGE SEATS:           {overage_seats:>12}                  │")
                lines.append(f"│  OVERAGE COST (annual):   ${overage_cost_annual:>12,.0f}                  │")
                lines.append("│  ⚠️  IMMEDIATE EXPANSION SAVES OVERAGE FEES                    │")

            # Capacity runway scenario
            elif active_90 > contracted * 0.85:
                headroom = contracted - active_90
                utilization_pct = (active_90 / contracted) * 100
                lines.append(f"│  UTILIZATION:             {utilization_pct:>12.1f}%                 │")
                lines.append(f"│  HEADROOM:                {headroom:>12} seats               │")
                lines.append("│  📈 AT CAPACITY — Expansion conversation is timely            │")

            # Growth projection
            if usage.get("active_users_30d"):
                active_30 = usage.get("active_users_30d") or 0
                if active_30 > 0:
                    monthly_growth = active_90 - active_30
                    if monthly_growth > 0:
                        months_to_capacity = (contracted - active_90) / monthly_growth if monthly_growth > 0 else 99
                        lines.append(f"│  MONTHLY GROWTH RATE:     {monthly_growth:>12} users/month         │")
                        if months_to_capacity < 6:
                            lines.append(f"│  🚀 CAPACITY HIT IN:      {months_to_capacity:>12.1f} months              │")

        lines.append("└─────────────────────────────────────────────────────────────────┘")

        # Add expansion potential calculation
        if current_arr > 0:
            lines.append("")
            lines.append("EXPANSION POTENTIAL:")

            # Standard tier upgrades (20-50% uplift typical)
            low_lift = current_arr * 0.15
            mid_lift = current_arr * 0.30
            high_lift = current_arr * 0.50

            lines.append(f"  • Conservative (15% lift):  +${low_lift:>10,.0f}  → Total ${current_arr + low_lift:,.0f}")
            lines.append(f"  • Moderate (30% lift):      +${mid_lift:>10,.0f}  → Total ${current_arr + mid_lift:,.0f}")
            lines.append(f"  • Aggressive (50% lift):    +${high_lift:>10,.0f}  → Total ${current_arr + high_lift:,.0f}")

        # Add insight-driven signals
        if insights:
            lines.append("")
            lines.append("SIGNAL-DRIVEN OPPORTUNITIES:")
            for insight in insights[:3]:
                insight_type = insight.get("insight_type", "")
                if insight_type == "limit_reached":
                    lines.append("  🔴 LIMIT REACHED: Customer needs immediate seat expansion")
                elif insight_type == "high_usage_velocity":
                    lines.append("  📈 HIGH VELOCITY: Usage growth suggests capacity need soon")
                elif insight_type == "seat_expansion_ready":
                    lines.append("  ✅ EXPANSION READY: Customer has demonstrated expansion readiness")
                elif insight_type == "upcoming_renewal_with_growth":
                    lines.append("  📅 RENEWAL OPPORTUNITY: Bundle expansion with renewal")
                elif insight_type == "feature_adoption_spike":
                    lines.append("  🚀 FEATURE SPIKE: New adoption suggests upsell opportunity")

        return "\n".join(lines)

    # ── Agents & Tasks ──────────────────────────────────────────────────────

    def _create_agents(self) -> None:
        """Create the expansion specialist crew agents."""
        self.analyst = self.create_agent_from_config(
            "expansion_analyst",
            role_default="Revenue Expansion Analyst",
            goal_default="Identify and score expansion opportunities using usage data and ARR trends",
        )

        self.strategist = self.create_agent_from_config(
            "upsell_strategist",
            role_default="Upsell Strategy Advisor",
            goal_default="Develop expansion plays with ROI justification",
        )

    def _create_tasks(
        self,
        account_name: str,
        account_tier: str,
        current_arr: float,
        contract_end_date: str,
        seat_utilization_context: str,
        usage_data: str,
        arr_history: str,
        health_score_data: str,
        engagement_data: str,
        stakeholder_map_data: str,
        commercial_insights: str,
        roi_context: str,
    ) -> List[Task]:
        """Create the expansion specialist tasks."""
        # Task 1: Analyze expansion signals (commercial intelligence)
        analyze_config = self._get_task_config("analyze_expansion_signals")
        analyze_task = Task(
            description=analyze_config.get("description", "").format(
                account_name=account_name,
                account_tier=account_tier,
                current_arr=current_arr,
                contract_end_date=contract_end_date,
                seat_utilization_context=seat_utilization_context,
                usage_data=usage_data,
                arr_history=arr_history,
                health_score_data=health_score_data,
                engagement_data=engagement_data,
                commercial_insights=commercial_insights,
                roi_context=roi_context,
            ),
            expected_output=analyze_config.get("expected_output", "Commercial expansion analysis with seat economics and ROI lift"),
            agent=self.analyst,
        )

        # Task 2: Develop expansion strategy
        strategy_config = self._get_task_config("develop_expansion_strategy_task")
        strategy_task = Task(
            description=strategy_config.get("description", "").format(
                account_name=account_name,
                current_arr=current_arr,
                contract_end_date=contract_end_date,
                stakeholder_map_data=stakeholder_map_data,
            ),
            expected_output=strategy_config.get("expected_output", "Expansion strategy"),
            agent=self.strategist,
            context=[analyze_task],
        )

        return [analyze_task, strategy_task]

    def run(
        self,
        account_id: str,
        current_arr: float = 0,
        user_id: Optional[str] = None,
        step_callback: Optional[callable] = None,
        usage_data: Optional[Dict[str, Any]] = None,
        arr_history_data: Optional[List[Dict[str, Any]]] = None,
        health_score_data: Optional[Dict[str, Any]] = None,
        engagement_data: Optional[Dict[str, Any]] = None,
        stakeholder_data: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Run the expansion specialist assessment.

        Args:
            account_id: The account ID (UUID)
            current_arr: Current ARR value
            user_id: Optional user ID for context
            step_callback: Optional callback for progress updates
            usage_data: Optional pre-fetched usage data
            arr_history_data: Optional pre-fetched renewal ARR history
            health_score_data: Optional pre-fetched health data
            engagement_data: Optional pre-fetched engagement data
            stakeholder_data: Optional pre-fetched stakeholder contacts

        Returns:
            Dict with expansion analysis result and metadata
        """
        if step_callback:
            step_callback("Gathering account data...")

        # Fetch account data
        account_data = self._fetch_account_data(account_id)
        account_name = account_data.get("name", "Unknown Account")
        sf_account_id = account_data.get("salesforce_id")
        account_tier = account_data.get("account_tier", "Unknown")
        contract_end_date = account_data.get("contract_end_date", "Unknown")

        if current_arr == 0:
            try:
                current_arr = float(account_data.get("contract_value_numeric", 0) or 0)
            except (ValueError, TypeError):
                current_arr = 0

        # Track data freshness - use account's updated_at as baseline
        data_as_of = account_data.get("updated_at") or datetime.utcnow().isoformat()

        # Fetch data if not provided
        if usage_data is None:
            usage_data = self._fetch_usage_data(account_id, sf_account_id)
        if arr_history_data is None:
            arr_history_data = self._fetch_arr_history(sf_account_id)
        if health_score_data is None:
            health_score_data = self._fetch_health_score_data(account_id)
        if engagement_data is None:
            engagement_data = self._fetch_engagement_data(sf_account_id)
        if stakeholder_data is None:
            stakeholder_data = self._fetch_stakeholder_map(sf_account_id)

        # Fetch commercial insights (always fetch - critical for ROI)
        commercial_insights = self._fetch_commercial_insights(account_id)

        # Format data for prompts
        seat_context_str = self._format_seat_utilization_context(usage_data)
        usage_str = self._format_usage_data(usage_data)
        arr_str = self._format_arr_history(arr_history_data)
        health_str = self._format_health_score_data(health_score_data)
        engagement_str = self._format_engagement_data(engagement_data)
        stakeholder_str = self._format_stakeholder_map(stakeholder_data)

        # Format commercial insights and ROI context
        commercial_insights_str = self._format_commercial_insights(commercial_insights)
        roi_context_str = self._calculate_roi_context(current_arr, usage_data, commercial_insights)

        if step_callback:
            step_callback("Building commercial intelligence profile...")

        self._create_agents()

        if step_callback:
            step_callback("Analyzing seat economics and growth trajectory...")

        tasks = self._create_tasks(
            account_name=account_name,
            account_tier=account_tier,
            current_arr=current_arr,
            contract_end_date=contract_end_date,
            seat_utilization_context=seat_context_str,
            usage_data=usage_str,
            arr_history=arr_str,
            health_score_data=health_str,
            engagement_data=engagement_str,
            stakeholder_map_data=stakeholder_str,
            commercial_insights=commercial_insights_str,
            roi_context=roi_context_str,
        )

        crew = Crew(
            name="Expansion Specialist Crew",
            agents=[self.analyst, self.strategist],
            tasks=tasks,
            process=Process.sequential,
            verbose=False,
        )

        if step_callback:
            step_callback("Crafting partnership-framed expansion strategy...")

        result = crew.kickoff()
        result_text = str(result)

        if step_callback:
            step_callback("Finalizing commercial briefing...")

        parsed_result = self._parse_json_result(result_text)

        # Get model info
        model_name = getattr(self.llm, "model", "unknown")
        provider = "openai"
        if "claude" in model_name.lower() or "anthropic" in model_name.lower():
            provider = "anthropic"
        elif "gemini" in model_name.lower():
            provider = "google"

        # Calculate basic ROI lift for response metadata
        usage = usage_data.get("usage", {}) if usage_data else {}
        contracted = usage.get("contracted_seats") or 0
        active_90 = usage.get("active_users_90d") or 0
        utilization_pct = round((active_90 / contracted) * 100, 1) if contracted > 0 else 0

        # Calculate data freshness
        sync_timestamps = extract_sync_timestamps({
            "account": account_data,
            "usage": usage_data.get("usage") if usage_data else None,
            "arr_history": arr_history_data,
            "health_score": health_score_data,
        })
        data_freshness = calculate_data_freshness(sync_timestamps)

        return {
            "success": True,
            "result": parsed_result,
            "account_id": account_id,
            "account_name": account_name,
            "account_tier": account_tier,
            "current_arr": current_arr,
            "contract_end_date": contract_end_date,
            "provider": provider,
            "model": model_name,
            "data_as_of": data_as_of,
            # Data freshness metadata
            "data_freshness": data_freshness,
            # Commercial intelligence metadata
            "commercial_signals_count": len(commercial_insights),
            "seat_metrics": {
                "contracted": contracted,
                "active": active_90,
                "utilization_pct": utilization_pct,
                "at_capacity": utilization_pct >= 85,
                "in_overage": active_90 > contracted,
            },
            "roi_lift_potential": {
                "conservative": round(current_arr * 0.15, 2),
                "moderate": round(current_arr * 0.30, 2),
                "aggressive": round(current_arr * 0.50, 2),
            } if current_arr > 0 else None,
        }
