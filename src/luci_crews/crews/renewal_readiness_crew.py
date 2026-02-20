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
from ..utils.data_freshness import calculate_data_freshness, extract_sync_timestamps

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
                "id, name, salesforce_id, industry, account_tier, "
                "contract_value_numeric, annual_revenue, contract_end_date, customer_start_date, updated_at, last_synced_at"
            ).eq("id", account_id).limit(1).execute()
            return result.data[0] if result.data else {}
        except Exception as e:
            logger.error(f"Error fetching account data: {e}")
            return {}

    def _fetch_health_score_data(self, account_id: str) -> Dict[str, Any]:
        """Fetch health score from latest crew analysis."""
        if not self.supabase:
            return {}

        try:
            # Get the latest sentiment analysis for this account
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
                        "confidence": parsed.get("confidence", "Unknown"),
                        "summary": parsed.get("summary", ""),
                    },
                    "analyzed_at": result.data[0].get("analyzed_at"),
                }
            return {}
        except Exception as e:
            logger.error(f"Error fetching health score data: {e}")
            return {}

    def _fetch_usage_data(self, account_id: str, salesforce_account_id: str) -> Dict[str, Any]:
        """Fetch product usage metrics from account_product_usage cache."""
        if not self.supabase:
            return {}

        try:
            # Try by salesforce_account_id first, then account_id
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

    def _fetch_support_cases(self, salesforce_account_id: str) -> List[Dict[str, Any]]:
        """Fetch support case history from cases table."""
        if not self.supabase or not salesforce_account_id:
            return []

        try:
            cutoff = (datetime.utcnow() - timedelta(days=180)).isoformat()
            result = self.supabase.table("cases").select(
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
                "name, title, email"
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
            parts.append(f"Trend: {current.get('trend', 'Unknown')}")
            parts.append(f"Confidence: {current.get('confidence', 'Unknown')}")
            summary = current.get('summary', '')
            if summary:
                parts.append(f"Summary: {summary[:200]}")

        analyzed_at = data.get("analyzed_at")
        if analyzed_at:
            parts.append(f"Last analyzed: {analyzed_at}")

        return "\n".join(parts) if parts else "No health data available."

    def _format_usage_data(self, data: Dict[str, Any]) -> str:
        """Format usage data for the prompt."""
        if not data or data.get("message"):
            return data.get("message", "No usage data available.")

        usage = data.get("usage", {})
        if not usage:
            return "No usage metrics recorded."

        parts = []
        if usage.get("utilization_pct") is not None:
            parts.append(f"Utilization: {usage['utilization_pct']}%")
        if usage.get("adoption_score") is not None:
            parts.append(f"Adoption Score: {usage['adoption_score']}")
        if usage.get("health_grade"):
            parts.append(f"Health Grade: {usage['health_grade']}")
        if usage.get("contracted_seats") is not None:
            parts.append(f"Contracted Seats: {usage['contracted_seats']}")
        if usage.get("active_users_90d") is not None:
            parts.append(f"Active Users (90d): {usage['active_users_90d']}")
        if usage.get("active_users_30d") is not None:
            parts.append(f"Active Users (30d): {usage['active_users_30d']}")
        if usage.get("integration_count") is not None:
            parts.append(f"Integrations: {usage['integration_count']}")

        return "\n".join(parts) if parts else "No usage data available."

    def _format_support_cases(self, cases: List[Dict[str, Any]]) -> str:
        """Format support cases for the prompt."""
        if not cases:
            return "No support cases in the last 6 months."

        open_count = sum(1 for c in cases if c.get("status") != "Closed")
        high_priority = sum(
            1 for c in cases if c.get("priority") in ["High", "Critical", "Urgent"]
        )

        formatted = [
            f"Total cases (6 months): {len(cases)}",
            f"Open cases: {open_count}",
            f"High priority cases: {high_priority}",
        ]

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

        formatted = [f"Total contacts: {len(contacts)}"]
        formatted.append("\nKey Contacts:")
        for contact in contacts[:10]:
            formatted.append(
                f"  - {contact.get('name', 'Unknown')} ({contact.get('title', 'Unknown title')})"
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
                nrr_history="NRR history not available.",
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

        # Track data freshness
        data_as_of = account_data.get("updated_at") or datetime.utcnow().isoformat()

        # Fetch data if not provided
        if health_score_data is None:
            health_score_data = self._fetch_health_score_data(account_id)
        if usage_data is None:
            usage_data = self._fetch_usage_data(account_id, sf_account_id)
        if support_cases_data is None:
            support_cases_data = self._fetch_support_cases(sf_account_id)
        if engagement_gap_data is None:
            engagement_gap_data = self._fetch_engagement_data(sf_account_id)
        if stakeholder_map_data is None:
            stakeholder_map_data = self._fetch_stakeholder_map(sf_account_id)

        # Format data for prompts
        health_str = self._format_health_score_data(health_score_data)
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

        # Calculate data freshness
        sync_timestamps = extract_sync_timestamps({
            "account": account_data,
            "usage": usage_data.get("usage") if usage_data and isinstance(usage_data, dict) else None,
            "support_cases": support_cases_data,
            "health_score": health_score_data,
        })
        data_freshness = calculate_data_freshness(sync_timestamps)

        return {
            "success": True,
            "result": parsed_result,
            "account_id": account_id,
            "account_name": account_name,
            "contract_end_date": contract_end_date,
            "current_arr": current_arr,
            "data_as_of": data_as_of,
            "data_freshness": data_freshness,
            "provider": provider,
            "model": model_name,
        }
