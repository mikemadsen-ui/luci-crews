"""
QBR Summary Crew

Generates executive-ready quarterly business review summaries with ROI highlights,
risk callouts, and expansion recommendations.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from crewai import Agent, Task, Crew, Process

from ..config_store import get_supabase
from .base_crew import BaseCrew

logger = logging.getLogger(__name__)


class QbrSummaryCrew(BaseCrew):
    """Crew for generating QBR summaries."""

    needs_supabase = True

    def _fetch_health_trend_data(
        self,
        account_id: str,
        quarter_start: str,
        quarter_end: str,
    ) -> List[Dict[str, Any]]:
        """Fetch account health trend data for the quarter."""
        if not self.supabase:
            return []

        try:
            result = self.supabase.table("account_health_snapshots").select(
                "score, status, trend, snapshot_date, key_metrics"
            ).eq("account_id", account_id).gte(
                "snapshot_date", quarter_start
            ).lte(
                "snapshot_date", quarter_end
            ).order("snapshot_date", desc=False).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching health trend data: {e}")
            return []

    def _fetch_usage_data(
        self,
        account_id: str,
        quarter_start: str,
        quarter_end: str,
    ) -> Dict[str, Any]:
        """Fetch product usage metrics for the quarter."""
        if not self.supabase:
            return {}

        try:
            # Fetch usage metrics - adjust table name as needed
            result = self.supabase.table("account_usage_metrics").select(
                "*"
            ).eq("account_id", account_id).gte(
                "metric_date", quarter_start
            ).lte(
                "metric_date", quarter_end
            ).order("metric_date", desc=True).limit(100).execute()

            if not result.data:
                return {"message": "No usage data available for this period."}

            return {
                "metrics": result.data,
                "period": f"{quarter_start} to {quarter_end}",
            }
        except Exception as e:
            logger.error(f"Error fetching usage data: {e}")
            return {"message": f"Error fetching usage data: {str(e)}"}

    def _fetch_support_cases(
        self,
        salesforce_account_id: str,
        quarter_start: str,
        quarter_end: str,
    ) -> List[Dict[str, Any]]:
        """Fetch support cases for the quarter."""
        if not self.supabase or not salesforce_account_id:
            return []

        try:
            result = self.supabase.table("cases").select(
                "case_number, subject, status, priority, type, created_date, closed_date"
            ).eq("salesforce_account_id", salesforce_account_id).gte(
                "created_date", quarter_start
            ).lte(
                "created_date", quarter_end
            ).order("created_date", desc=True).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching support cases: {e}")
            return []

    def _fetch_renewal_data(self, account_id: str) -> Dict[str, Any]:
        """Fetch renewal ARR and contract data."""
        if not self.supabase:
            return {}

        try:
            result = self.supabase.table("accounts").select(
                "arr, contract_end_date, contract_start_date, account_tier"
            ).eq("id", account_id).limit(1).execute()

            if result.data:
                return result.data[0]
            return {}
        except Exception as e:
            logger.error(f"Error fetching renewal data: {e}")
            return {}

    def _fetch_account_salesforce_id(self, account_id: str) -> Optional[str]:
        """Fetch the Salesforce account ID for support case lookup."""
        if not self.supabase:
            return None

        try:
            result = self.supabase.table("accounts").select(
                "salesforce_id"
            ).eq("id", account_id).limit(1).execute()

            if result.data:
                return result.data[0].get("salesforce_id")
            return None
        except Exception as e:
            logger.error(f"Error fetching Salesforce account ID: {e}")
            return None

    def _format_health_trend_data(self, data: List[Dict[str, Any]]) -> str:
        """Format health trend data for the prompt."""
        if not data:
            return "No health trend data available for this period."

        formatted = []
        for snapshot in data:
            date = snapshot.get("snapshot_date", "Unknown")
            score = snapshot.get("score", "N/A")
            status = snapshot.get("status", "Unknown")
            trend = snapshot.get("trend", "Unknown")
            formatted.append(f"- {date}: Score {score}, Status: {status}, Trend: {trend}")

        return "\n".join(formatted)

    def _format_usage_data(self, data: Dict[str, Any]) -> str:
        """Format usage data for the prompt."""
        if not data or data.get("message"):
            return data.get("message", "No usage data available.")

        metrics = data.get("metrics", [])
        if not metrics:
            return "No usage metrics recorded for this period."

        # Summarize usage metrics
        formatted = [f"Period: {data.get('period', 'Unknown')}"]
        formatted.append(f"Total data points: {len(metrics)}")

        # Add sample of recent metrics
        for metric in metrics[:10]:
            formatted.append(f"- {metric}")

        return "\n".join(formatted)

    def _format_support_cases(self, cases: List[Dict[str, Any]]) -> str:
        """Format support cases for the prompt."""
        if not cases:
            return "No support cases during this period."

        formatted = [f"Total cases: {len(cases)}"]

        # Count by status
        status_counts = {}
        priority_counts = {}
        for case in cases:
            status = case.get("status", "Unknown")
            priority = case.get("priority", "Unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
            priority_counts[priority] = priority_counts.get(priority, 0) + 1

        formatted.append(f"By status: {status_counts}")
        formatted.append(f"By priority: {priority_counts}")

        # List recent cases
        formatted.append("\nRecent cases:")
        for case in cases[:10]:
            formatted.append(
                f"- [{case.get('case_number')}] {case.get('subject', 'No subject')} "
                f"({case.get('status')}, {case.get('priority')})"
            )

        return "\n".join(formatted)

    def _format_renewal_data(self, data: Dict[str, Any]) -> str:
        """Format renewal data for the prompt."""
        if not data:
            return "No renewal data available."

        parts = []
        if data.get("arr"):
            parts.append(f"Current ARR: ${data['arr']:,.0f}")
        if data.get("contract_end_date"):
            parts.append(f"Contract End: {data['contract_end_date']}")
        if data.get("account_tier"):
            parts.append(f"Tier: {data['account_tier']}")

        return "\n".join(parts) if parts else "No renewal data available."

    def _create_agents(self) -> None:
        """Create the QBR crew agents."""
        self.data_aggregator = self.create_agent_from_config(
            "qbr_data_aggregator",
            role_default="QBR Data Aggregator",
            goal_default="Aggregate account data for QBR preparation",
        )

        self.narrative_writer = self.create_agent_from_config(
            "qbr_narrative_writer",
            role_default="QBR Narrative Writer",
            goal_default="Generate executive-ready QBR summaries",
        )

    def _create_tasks(
        self,
        account_name: str,
        quarter_start: str,
        quarter_end: str,
        health_trend_data: str,
        usage_data: str,
        support_cases_data: str,
        renewal_data: str,
    ) -> List[Task]:
        """Create the QBR summary tasks."""
        # Task 1: Aggregate data
        aggregate_config = self._get_task_config("aggregate_qbr_data")
        aggregate_task = Task(
            description=aggregate_config.get("description", "").format(
                account_name=account_name,
                quarter_start=quarter_start,
                quarter_end=quarter_end,
                health_trend_data=health_trend_data,
                usage_data=usage_data,
                support_cases_data=support_cases_data,
                renewal_data=renewal_data,
            ),
            expected_output=aggregate_config.get("expected_output", "Data summary"),
            agent=self.data_aggregator,
        )

        # Task 2: Generate narrative
        narrative_config = self._get_task_config("generate_qbr_narrative")
        narrative_task = Task(
            description=narrative_config.get("description", "").format(
                account_name=account_name,
                quarter_start=quarter_start,
                quarter_end=quarter_end,
                aggregated_data="{aggregated_data}",  # Will be filled by context
            ),
            expected_output=narrative_config.get("expected_output", "QBR summary"),
            agent=self.narrative_writer,
            context=[aggregate_task],
        )

        return [aggregate_task, narrative_task]

    def run(
        self,
        account_id: str,
        account_name: str,
        quarter_start: str,
        quarter_end: str,
        user_id: Optional[str] = None,
        step_callback: Optional[callable] = None,
        health_trend_data: Optional[List[Dict[str, Any]]] = None,
        usage_data: Optional[Dict[str, Any]] = None,
        support_cases_data: Optional[List[Dict[str, Any]]] = None,
        renewal_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Run the QBR summary generation.

        Args:
            account_id: The account ID (UUID)
            account_name: Display name of the account
            quarter_start: Start date of quarter (YYYY-MM-DD)
            quarter_end: End date of quarter (YYYY-MM-DD)
            user_id: Optional user ID for context
            step_callback: Optional callback for progress updates
            health_trend_data: Optional pre-fetched health trend data
            usage_data: Optional pre-fetched usage data
            support_cases_data: Optional pre-fetched support cases
            renewal_data: Optional pre-fetched renewal data

        Returns:
            Dict with QBR summary result and metadata
        """
        if step_callback:
            step_callback("Gathering account data...")

        # Use pre-fetched data or fetch from Supabase
        if health_trend_data is None:
            health_trend_data = self._fetch_health_trend_data(
                account_id, quarter_start, quarter_end
            )
        if usage_data is None:
            usage_data = self._fetch_usage_data(account_id, quarter_start, quarter_end)
        if support_cases_data is None:
            sf_account_id = self._fetch_account_salesforce_id(account_id)
            support_cases_data = self._fetch_support_cases(
                sf_account_id, quarter_start, quarter_end
            ) if sf_account_id else []
        if renewal_data is None:
            renewal_data = self._fetch_renewal_data(account_id)

        # Format data for prompts
        health_str = self._format_health_trend_data(health_trend_data)
        usage_str = self._format_usage_data(usage_data)
        support_str = self._format_support_cases(support_cases_data)
        renewal_str = self._format_renewal_data(renewal_data)

        if step_callback:
            step_callback("Creating QBR agents...")

        # Create agents and tasks
        self._create_agents()

        if step_callback:
            step_callback("Aggregating quarterly data...")

        tasks = self._create_tasks(
            account_name=account_name,
            quarter_start=quarter_start,
            quarter_end=quarter_end,
            health_trend_data=health_str,
            usage_data=usage_str,
            support_cases_data=support_str,
            renewal_data=renewal_str,
        )

        # Run the crew
        crew = Crew(
            name="QBR Summary Crew",
            agents=[self.data_aggregator, self.narrative_writer],
            tasks=tasks,
            process=Process.sequential,
            verbose=False,
        )

        if step_callback:
            step_callback("Generating QBR narrative...")

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
            "quarter": f"{quarter_start} to {quarter_end}",
            "provider": provider,
            "model": model_name,
        }
