"""
Renewal Readiness Crew

Assesses account renewal readiness with risk scoring, strategic recommendations,
and negotiation guidance across expansion, flat, and contraction scenarios.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from crewai import Agent, Task, Crew, Process

from ..config_store import get_supabase
from .base_crew import BaseCrew

logger = logging.getLogger(__name__)


class RenewalReadinessCrew(BaseCrew):
    """Crew for assessing renewal readiness."""

    needs_supabase = True

    def _fetch_account_data(self, account_id: str) -> Dict[str, Any]:
        """Fetch core account data."""
        if not self.supabase:
            return {}

        try:
            result = self.supabase.table("accounts").select(
                "id, name, salesforce_id, industry, account_tier, arr, health_score, "
                "contract_end_date, contract_start_date, customer_since"
            ).eq("id", account_id).limit(1).execute()
            return result.data[0] if result.data else {}
        except Exception as e:
            logger.error(f"Error fetching account data: {e}")
            return {}

    def _fetch_health_score_data(self, account_id: str) -> Dict[str, Any]:
        """Fetch current and historical health score data."""
        if not self.supabase:
            return {}

        try:
            # Get current health
            current = self.supabase.table("accounts").select(
                "health_score, health_status, health_trend"
            ).eq("id", account_id).limit(1).execute()

            # Get historical snapshots (last 6 months)
            cutoff = (datetime.utcnow() - timedelta(days=180)).isoformat()
            history = self.supabase.table("account_health_snapshots").select(
                "score, status, trend, snapshot_date"
            ).eq("account_id", account_id).gte(
                "snapshot_date", cutoff
            ).order("snapshot_date", desc=True).limit(20).execute()

            return {
                "current": current.data[0] if current.data else {},
                "history": history.data or [],
            }
        except Exception as e:
            logger.error(f"Error fetching health score data: {e}")
            return {}

    def _fetch_nrr_history(self, salesforce_account_id: str) -> List[Dict[str, Any]]:
        """Fetch NRR (Net Revenue Retention) history."""
        if not self.supabase or not salesforce_account_id:
            return []

        try:
            result = self.supabase.table("account_nrr_history").select(
                "period, arr_start, arr_end, expansion, contraction, churn, nrr_pct"
            ).eq("salesforce_account_id", salesforce_account_id).order(
                "period", desc=True
            ).limit(8).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching NRR history: {e}")
            return []

    def _fetch_usage_data(self, account_id: str) -> Dict[str, Any]:
        """Fetch product usage metrics."""
        if not self.supabase:
            return {}

        try:
            # Get recent usage metrics
            cutoff = (datetime.utcnow() - timedelta(days=90)).isoformat()
            result = self.supabase.table("account_usage_metrics").select(
                "*"
            ).eq("account_id", account_id).gte(
                "metric_date", cutoff
            ).order("metric_date", desc=True).limit(50).execute()

            if not result.data:
                return {"message": "No usage data available."}

            return {"metrics": result.data}
        except Exception as e:
            logger.error(f"Error fetching usage data: {e}")
            return {}

    def _fetch_support_cases(self, salesforce_account_id: str) -> List[Dict[str, Any]]:
        """Fetch support case history."""
        if not self.supabase or not salesforce_account_id:
            return []

        try:
            cutoff = (datetime.utcnow() - timedelta(days=180)).isoformat()
            result = self.supabase.table("support_cases").select(
                "case_number, subject, status, priority, type, created_date, closed_date"
            ).eq("salesforce_account_id", salesforce_account_id).gte(
                "created_date", cutoff
            ).order("created_date", desc=True).limit(50).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching support cases: {e}")
            return []

    def _fetch_engagement_data(self, salesforce_account_id: str) -> Dict[str, Any]:
        """Fetch engagement gap data."""
        if not self.supabase or not salesforce_account_id:
            return {}

        try:
            # Get recent meeting count
            cutoff_30 = (datetime.utcnow() - timedelta(days=30)).isoformat()
            cutoff_90 = (datetime.utcnow() - timedelta(days=90)).isoformat()

            recent_meetings = self.supabase.table("transcriptions").select(
                "id", count="exact"
            ).eq("salesforce_account_id", salesforce_account_id).gte(
                "meeting_date", cutoff_30
            ).execute()

            older_meetings = self.supabase.table("transcriptions").select(
                "id", count="exact"
            ).eq("salesforce_account_id", salesforce_account_id).gte(
                "meeting_date", cutoff_90
            ).lt("meeting_date", cutoff_30).execute()

            return {
                "meetings_last_30_days": recent_meetings.count or 0,
                "meetings_30_to_90_days": older_meetings.count or 0,
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
                "name, title, email, department, is_champion, is_decision_maker, "
                "engagement_level, last_interaction_date"
            ).eq("salesforce_account_id", salesforce_account_id).limit(20).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching stakeholder map: {e}")
            return []

    def _format_health_score_data(self, data: Dict[str, Any]) -> str:
        """Format health score data for the prompt."""
        if not data:
            return "No health score data available."

        parts = []
        current = data.get("current", {})
        if current:
            parts.append(f"Current Score: {current.get('health_score', 'N/A')}")
            parts.append(f"Status: {current.get('health_status', 'Unknown')}")
            parts.append(f"Trend: {current.get('health_trend', 'Unknown')}")

        history = data.get("history", [])
        if history:
            parts.append("\nHistorical Snapshots:")
            for snapshot in history[:5]:
                parts.append(
                    f"  - {snapshot.get('snapshot_date')}: "
                    f"Score {snapshot.get('score')}, {snapshot.get('trend')}"
                )

        return "\n".join(parts) if parts else "No health data available."

    def _format_nrr_history(self, data: List[Dict[str, Any]]) -> str:
        """Format NRR history for the prompt."""
        if not data:
            return "No NRR history available."

        formatted = []
        for period in data:
            formatted.append(
                f"- {period.get('period')}: NRR {period.get('nrr_pct', 'N/A')}% "
                f"(Start: ${period.get('arr_start', 0):,.0f}, End: ${period.get('arr_end', 0):,.0f})"
            )

        return "\n".join(formatted)

    def _format_usage_data(self, data: Dict[str, Any]) -> str:
        """Format usage data for the prompt."""
        if not data or data.get("message"):
            return data.get("message", "No usage data available.")

        metrics = data.get("metrics", [])
        if not metrics:
            return "No usage metrics recorded."

        return f"Usage data points: {len(metrics)} records in last 90 days."

    def _format_support_cases(self, cases: List[Dict[str, Any]]) -> str:
        """Format support cases for the prompt."""
        if not cases:
            return "No support cases in the last 6 months."

        # Analyze cases
        open_count = sum(1 for c in cases if c.get("status") != "Closed")
        high_priority = sum(
            1 for c in cases if c.get("priority") in ["High", "Critical", "Urgent"]
        )

        formatted = [
            f"Total cases (6 months): {len(cases)}",
            f"Open cases: {open_count}",
            f"High priority cases: {high_priority}",
        ]

        # List recent cases
        formatted.append("\nRecent cases:")
        for case in cases[:5]:
            formatted.append(
                f"- [{case.get('case_number')}] {case.get('subject', 'No subject')[:50]} "
                f"({case.get('status')}, {case.get('priority')})"
            )

        return "\n".join(formatted)

    def _format_engagement_data(self, data: Dict[str, Any]) -> str:
        """Format engagement gap data for the prompt."""
        if not data:
            return "No engagement data available."

        recent = data.get("meetings_last_30_days", 0)
        older = data.get("meetings_30_to_90_days", 0)

        parts = [
            f"Meetings in last 30 days: {recent}",
            f"Meetings 30-90 days ago: {older}",
        ]

        if recent < older / 2:
            parts.append("WARNING: Engagement appears to be declining.")
        elif recent > older:
            parts.append("Positive: Engagement is increasing.")

        return "\n".join(parts)

    def _format_stakeholder_map(self, contacts: List[Dict[str, Any]]) -> str:
        """Format stakeholder map for the prompt."""
        if not contacts:
            return "No stakeholder data available."

        champions = [c for c in contacts if c.get("is_champion")]
        decision_makers = [c for c in contacts if c.get("is_decision_maker")]

        formatted = [f"Total contacts: {len(contacts)}"]

        if champions:
            formatted.append(f"\nChampions ({len(champions)}):")
            for c in champions:
                formatted.append(f"  - {c.get('name')} ({c.get('title', 'Unknown title')})")

        if decision_makers:
            formatted.append(f"\nDecision Makers ({len(decision_makers)}):")
            for dm in decision_makers:
                formatted.append(f"  - {dm.get('name')} ({dm.get('title', 'Unknown title')})")

        # List other key contacts
        formatted.append("\nOther Key Contacts:")
        for contact in contacts[:10]:
            if contact not in champions and contact not in decision_makers:
                formatted.append(
                    f"  - {contact.get('name')} ({contact.get('title', 'Unknown')})"
                )

        return "\n".join(formatted)

    def _create_agents(self) -> None:
        """Create the renewal readiness crew agents."""
        self.data_analyst = self.create_agent_from_config(
            "renewal_data_analyst",
            role_default="Renewal Data Analyst",
            goal_default="Analyze renewal risk factors",
        )

        self.strategist = self.create_agent_from_config(
            "renewal_strategist",
            role_default="Renewal Strategist",
            goal_default="Develop renewal strategies",
        )

    def _create_tasks(
        self,
        account_name: str,
        contract_end_date: str,
        current_arr: float,
        health_score_data: str,
        nrr_history: str,
        usage_data: str,
        support_cases_data: str,
        engagement_gap_data: str,
        stakeholder_map_data: str,
    ) -> List[Task]:
        """Create the renewal readiness tasks."""
        # Task 1: Analyze data
        analyze_config = self._get_task_config("analyze_renewal_data")
        analyze_task = Task(
            description=analyze_config.get("description", "").format(
                account_name=account_name,
                contract_end_date=contract_end_date,
                current_arr=current_arr,
                health_score_data=health_score_data,
                nrr_history=nrr_history,
                usage_data=usage_data,
                support_cases_data=support_cases_data,
                engagement_gap_data=engagement_gap_data,
                stakeholder_map_data=stakeholder_map_data,
            ),
            expected_output=analyze_config.get("expected_output", "Risk analysis"),
            agent=self.data_analyst,
        )

        # Task 2: Develop strategy
        strategy_config = self._get_task_config("develop_renewal_strategy")
        strategy_task = Task(
            description=strategy_config.get("description", "").format(
                account_name=account_name,
                contract_end_date=contract_end_date,
                current_arr=current_arr,
                risk_analysis="{risk_analysis}",  # Filled by context
            ),
            expected_output=strategy_config.get("expected_output", "Renewal strategy"),
            agent=self.strategist,
            context=[analyze_task],
        )

        return [analyze_task, strategy_task]

    def run(
        self,
        account_id: str,
        contract_end_date: str,
        current_arr: float,
        user_id: Optional[str] = None,
        step_callback: Optional[callable] = None,
        health_score_data: Optional[Dict[str, Any]] = None,
        nrr_history: Optional[List[Dict[str, Any]]] = None,
        usage_data: Optional[Dict[str, Any]] = None,
        support_cases_data: Optional[List[Dict[str, Any]]] = None,
        engagement_gap_data: Optional[Dict[str, Any]] = None,
        stakeholder_map_data: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Run the renewal readiness assessment.

        Args:
            account_id: The account ID (UUID)
            contract_end_date: Contract end date (YYYY-MM-DD)
            current_arr: Current ARR value
            user_id: Optional user ID for context
            step_callback: Optional callback for progress updates
            health_score_data: Optional pre-fetched health data
            nrr_history: Optional pre-fetched NRR history
            usage_data: Optional pre-fetched usage data
            support_cases_data: Optional pre-fetched support cases
            engagement_gap_data: Optional pre-fetched engagement data
            stakeholder_map_data: Optional pre-fetched stakeholder data

        Returns:
            Dict with renewal readiness result and metadata
        """
        if step_callback:
            step_callback("Gathering account data...")

        # Fetch account data
        account_data = self._fetch_account_data(account_id)
        account_name = account_data.get("name", "Unknown Account")
        sf_account_id = account_data.get("salesforce_id")

        # Fetch data if not provided
        if health_score_data is None:
            health_score_data = self._fetch_health_score_data(account_id)
        if nrr_history is None:
            nrr_history = self._fetch_nrr_history(sf_account_id)
        if usage_data is None:
            usage_data = self._fetch_usage_data(account_id)
        if support_cases_data is None:
            support_cases_data = self._fetch_support_cases(sf_account_id)
        if engagement_gap_data is None:
            engagement_gap_data = self._fetch_engagement_data(sf_account_id)
        if stakeholder_map_data is None:
            stakeholder_map_data = self._fetch_stakeholder_map(sf_account_id)

        # Format data for prompts
        health_str = self._format_health_score_data(health_score_data)
        nrr_str = self._format_nrr_history(nrr_history)
        usage_str = self._format_usage_data(usage_data)
        support_str = self._format_support_cases(support_cases_data)
        engagement_str = self._format_engagement_data(engagement_gap_data)
        stakeholder_str = self._format_stakeholder_map(stakeholder_map_data)

        if step_callback:
            step_callback("Creating renewal analysts...")

        # Create agents and tasks
        self._create_agents()

        if step_callback:
            step_callback("Analyzing renewal risk factors...")

        tasks = self._create_tasks(
            account_name=account_name,
            contract_end_date=contract_end_date,
            current_arr=current_arr,
            health_score_data=health_str,
            nrr_history=nrr_str,
            usage_data=usage_str,
            support_cases_data=support_str,
            engagement_gap_data=engagement_str,
            stakeholder_map_data=stakeholder_str,
        )

        # Run the crew
        crew = Crew(
            name="Renewal Readiness Crew",
            agents=[self.data_analyst, self.strategist],
            tasks=tasks,
            process=Process.sequential,
            verbose=False,
        )

        if step_callback:
            step_callback("Developing renewal strategy...")

        result = crew.kickoff()
        result_text = str(result)

        if step_callback:
            step_callback("Parsing results...")

        # Parse the JSON result
        parsed_result = self._parse_json_result(result_text)

        # Get model info
        model_name = getattr(self.llm, 'model', 'unknown')
        provider = "openai"
        if "claude" in model_name.lower() or "anthropic" in model_name.lower():
            provider = "anthropic"
        elif "gemini" in model_name.lower():
            provider = "google"

        return {
            "success": True,
            "result": parsed_result,
            "account_id": account_id,
            "account_name": account_name,
            "contract_end_date": contract_end_date,
            "current_arr": current_arr,
            "provider": provider,
            "model": model_name,
        }
