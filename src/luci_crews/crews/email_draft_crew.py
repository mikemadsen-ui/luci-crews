"""
Email Draft Crew

Drafts professional, personalized customer emails matching various template types
while incorporating account-specific context.
"""

import logging
from typing import Optional, List, Dict, Any

from crewai import Agent, Task, Crew, Process

from ..config_store import get_supabase
from .base_crew import BaseCrew

logger = logging.getLogger(__name__)

# Valid template types
TEMPLATE_TYPES = [
    "executive_checkin",
    "renewal_kickoff",
    "risk_mitigation",
    "qbr_followup",
    "expansion_proposal",
]


class EmailDraftCrew(BaseCrew):
    """Crew for drafting customer emails."""

    needs_supabase = True

    def _fetch_account_data(self, account_id: str) -> Dict[str, Any]:
        """Fetch account details."""
        if not self.supabase:
            return {}

        try:
            result = self.supabase.table("accounts").select(
                "name, industry, account_tier, arr, health_score, contract_end_date, "
                "salesforce_id, customer_since"
            ).eq("id", account_id).limit(1).execute()
            return result.data[0] if result.data else {}
        except Exception as e:
            logger.error(f"Error fetching account data: {e}")
            return {}

    def _fetch_recent_interactions(
        self,
        salesforce_account_id: str,
        days: int = 30,
    ) -> List[Dict[str, Any]]:
        """Fetch recent meeting transcriptions."""
        if not self.supabase or not salesforce_account_id:
            return []

        try:
            from datetime import datetime, timedelta
            cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

            result = self.supabase.table("transcriptions").select(
                "meeting_subject, meeting_date, meeting_summary"
            ).eq("salesforce_account_id", salesforce_account_id).gte(
                "meeting_date", cutoff
            ).order("meeting_date", desc=True).limit(10).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching recent interactions: {e}")
            return []

    def _fetch_open_cases(self, salesforce_account_id: str) -> List[Dict[str, Any]]:
        """Fetch open support cases."""
        if not self.supabase or not salesforce_account_id:
            return []

        try:
            result = self.supabase.table("support_cases").select(
                "case_number, subject, status, priority, type, created_date"
            ).eq("salesforce_account_id", salesforce_account_id).neq(
                "status", "Closed"
            ).order("created_date", desc=True).limit(10).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching open cases: {e}")
            return []

    def _fetch_renewal_status(self, account_id: str) -> Dict[str, Any]:
        """Fetch renewal status information."""
        if not self.supabase:
            return {}

        try:
            result = self.supabase.table("accounts").select(
                "arr, contract_end_date, renewal_probability, renewal_status"
            ).eq("id", account_id).limit(1).execute()
            return result.data[0] if result.data else {}
        except Exception as e:
            logger.error(f"Error fetching renewal status: {e}")
            return {}

    def _format_account_data(self, data: Dict[str, Any]) -> str:
        """Format account data for the prompt."""
        if not data:
            return "No account data available."

        parts = []
        if data.get("name"):
            parts.append(f"Account: {data['name']}")
        if data.get("industry"):
            parts.append(f"Industry: {data['industry']}")
        if data.get("account_tier"):
            parts.append(f"Tier: {data['account_tier']}")
        if data.get("arr"):
            parts.append(f"ARR: ${data['arr']:,.0f}")
        if data.get("health_score"):
            parts.append(f"Health Score: {data['health_score']}")
        if data.get("contract_end_date"):
            parts.append(f"Contract End: {data['contract_end_date']}")
        if data.get("customer_since"):
            parts.append(f"Customer Since: {data['customer_since']}")

        return "\n".join(parts) if parts else "No account data available."

    def _format_recent_interactions(self, interactions: List[Dict[str, Any]]) -> str:
        """Format recent interactions for the prompt."""
        if not interactions:
            return "No recent interactions recorded."

        formatted = []
        for interaction in interactions:
            date = interaction.get("meeting_date", "Unknown date")
            subject = interaction.get("meeting_subject", "No subject")
            summary = interaction.get("meeting_summary", "No summary")
            formatted.append(f"- {date}: {subject}")
            if summary and summary != "No summary":
                formatted.append(f"  Summary: {summary[:200]}...")

        return "\n".join(formatted)

    def _format_open_cases(self, cases: List[Dict[str, Any]]) -> str:
        """Format open cases for the prompt."""
        if not cases:
            return "No open support cases."

        formatted = [f"Open cases: {len(cases)}"]
        for case in cases[:5]:
            formatted.append(
                f"- [{case.get('case_number')}] {case.get('subject', 'No subject')} "
                f"({case.get('priority', 'Unknown')} priority)"
            )

        return "\n".join(formatted)

    def _format_renewal_status(self, data: Dict[str, Any]) -> str:
        """Format renewal status for the prompt."""
        if not data:
            return "No renewal data available."

        parts = []
        if data.get("arr"):
            parts.append(f"ARR: ${data['arr']:,.0f}")
        if data.get("contract_end_date"):
            parts.append(f"Contract End: {data['contract_end_date']}")
        if data.get("renewal_probability"):
            parts.append(f"Renewal Probability: {data['renewal_probability']}%")
        if data.get("renewal_status"):
            parts.append(f"Status: {data['renewal_status']}")

        return "\n".join(parts) if parts else "No renewal data available."

    def _create_agents(self) -> None:
        """Create the email draft crew agents."""
        self.context_gatherer = self.create_agent_from_config(
            "email_context_gatherer",
            role_default="Email Context Gatherer",
            goal_default="Assemble context for email drafting",
        )

        self.email_composer = self.create_agent_from_config(
            "email_composer",
            role_default="Email Composer",
            goal_default="Draft professional customer emails",
        )

    def _create_tasks(
        self,
        account_name: str,
        template_type: str,
        recipient_role: str,
        account_data: str,
        recent_interactions: str,
        open_cases: str,
        renewal_status: str,
        additional_context: str,
    ) -> List[Task]:
        """Create the email draft tasks."""
        # Task 1: Gather context
        gather_config = self._get_task_config("gather_email_context")
        gather_task = Task(
            description=gather_config.get("description", "").format(
                template_type=template_type,
                account_name=account_name,
                recipient_role=recipient_role or "Unknown",
                account_data=account_data,
                recent_interactions=recent_interactions,
                open_cases=open_cases,
                renewal_status=renewal_status,
                additional_context=additional_context or "None provided.",
            ),
            expected_output=gather_config.get("expected_output", "Context summary"),
            agent=self.context_gatherer,
        )

        # Task 2: Compose email
        compose_config = self._get_task_config("compose_email")
        compose_task = Task(
            description=compose_config.get("description", "").format(
                template_type=template_type,
                account_name=account_name,
                recipient_role=recipient_role or "customer stakeholder",
                context_summary="{context_summary}",  # Filled by context
            ),
            expected_output=compose_config.get("expected_output", "Email draft"),
            agent=self.email_composer,
            context=[gather_task],
        )

        return [gather_task, compose_task]

    def run(
        self,
        account_id: str,
        template_type: str,
        recipient_role: Optional[str] = None,
        additional_context: Optional[str] = None,
        user_id: Optional[str] = None,
        step_callback: Optional[callable] = None,
        account_data: Optional[Dict[str, Any]] = None,
        recent_interactions: Optional[List[Dict[str, Any]]] = None,
        open_cases: Optional[List[Dict[str, Any]]] = None,
        renewal_status: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Run the email draft generation.

        Args:
            account_id: The account ID (UUID)
            template_type: Type of email (executive_checkin, renewal_kickoff, etc.)
            recipient_role: Role of the recipient (e.g., "VP of Operations")
            additional_context: Any additional context for the email
            user_id: Optional user ID for context
            step_callback: Optional callback for progress updates
            account_data: Optional pre-fetched account data
            recent_interactions: Optional pre-fetched interactions
            open_cases: Optional pre-fetched open cases
            renewal_status: Optional pre-fetched renewal status

        Returns:
            Dict with email draft result and metadata
        """
        # Validate template type
        if template_type not in TEMPLATE_TYPES:
            return {
                "success": False,
                "error": f"Invalid template type. Must be one of: {TEMPLATE_TYPES}",
            }

        if step_callback:
            step_callback("Gathering account context...")

        # Fetch account data if not provided
        if account_data is None:
            account_data = self._fetch_account_data(account_id)

        account_name = account_data.get("name", "Unknown Account")
        sf_account_id = account_data.get("salesforce_id")

        # Fetch other data if not provided
        if recent_interactions is None:
            recent_interactions = self._fetch_recent_interactions(sf_account_id)
        if open_cases is None:
            open_cases = self._fetch_open_cases(sf_account_id)
        if renewal_status is None:
            renewal_status = self._fetch_renewal_status(account_id)

        # Format data for prompts
        account_str = self._format_account_data(account_data)
        interactions_str = self._format_recent_interactions(recent_interactions)
        cases_str = self._format_open_cases(open_cases)
        renewal_str = self._format_renewal_status(renewal_status)

        if step_callback:
            step_callback("Creating email agents...")

        # Create agents and tasks
        self._create_agents()

        if step_callback:
            step_callback("Analyzing context...")

        tasks = self._create_tasks(
            account_name=account_name,
            template_type=template_type,
            recipient_role=recipient_role,
            account_data=account_str,
            recent_interactions=interactions_str,
            open_cases=cases_str,
            renewal_status=renewal_str,
            additional_context=additional_context,
        )

        # Run the crew
        crew = Crew(
            name="Email Draft Crew",
            agents=[self.context_gatherer, self.email_composer],
            tasks=tasks,
            process=Process.sequential,
            verbose=False,
        )

        if step_callback:
            step_callback(f"Composing {template_type} email...")

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
            "template_type": template_type,
            "provider": provider,
            "model": model_name,
        }
