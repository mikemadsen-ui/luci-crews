"""
MEDDPICC Gap Actions Crew

Provides targeted recommendations for resolving specific MEDDPICC gaps,
including discovery questions, email templates, and transcript evidence.
"""

import logging
from typing import Optional, List, Dict, Any
from crewai import Agent, Task, Crew, Process

from ..config_store import get_supabase
from .base_crew import BaseCrew
from ..utils import extract_json_from_llm_response

logger = logging.getLogger(__name__)

# Map gap field names to human-readable labels
GAP_FIELD_LABELS = {
    "metrics": "Metrics (Quantified Business Impact)",
    "economic_buyer": "Economic Buyer",
    "decision_criteria": "Decision Criteria",
    "decision_process": "Decision Process",
    "identify_pain": "Identify Pain",
    "champion": "Champion",
    "competition": "Competition",
    # Additional variations that might be used
    "meddpicc_metrics": "Metrics (Quantified Business Impact)",
    "meddpicc_economic_buyer": "Economic Buyer",
    "meddpicc_decision_criteria": "Decision Criteria",
    "meddpicc_decision_process": "Decision Process",
    "meddpicc_identify_pain": "Identify Pain",
    "meddpicc_champion": "Champion",
    "meddpicc_competition": "Competition",
}


class MeddpiccGapActionsCrew(BaseCrew):
    """Crew for generating MEDDPICC gap resolution recommendations."""

    def _fetch_opportunity(self, opportunity_id: str) -> Optional[Dict[str, Any]]:
        """Fetch opportunity details from Supabase."""
        supabase = get_supabase()
        if not supabase:
            logger.error("Supabase not configured")
            return None

        try:
            # Try fetching by UUID first, then by Salesforce ID
            result = supabase.table("opportunities").select(
                "*, accounts(id, name, industry, account_tier, salesforce_id)"
            ).eq("id", opportunity_id).limit(1).execute()

            if not result.data:
                # Try by Salesforce ID
                result = supabase.table("opportunities").select(
                    "*, accounts(id, name, industry, account_tier, salesforce_id)"
                ).eq("salesforce_id", opportunity_id).limit(1).execute()

            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error fetching opportunity: {e}")
            return None

    def _fetch_contacts(self, salesforce_account_id: str) -> List[Dict[str, Any]]:
        """Fetch account contacts for personalization."""
        supabase = get_supabase()
        if not supabase or not salesforce_account_id:
            return []

        try:
            result = supabase.table("contacts").select(
                "name, title, email, department"
            ).eq("salesforce_account_id", salesforce_account_id).limit(20).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching contacts: {e}")
            return []

    def _fetch_account_context(self, salesforce_account_id: str) -> Dict[str, Any]:
        """Fetch additional account context."""
        supabase = get_supabase()
        if not supabase or not salesforce_account_id:
            return {}

        context = {
            "contacts": [],
            "other_opportunities": [],
            "account_details": None,
        }

        try:
            # Fetch account details
            account_result = supabase.table("accounts").select(
                "name, industry, account_tier, arr, employee_count, website"
            ).eq("salesforce_id", salesforce_account_id).limit(1).execute()
            context["account_details"] = account_result.data[0] if account_result.data else None

            # Fetch contacts
            contacts_result = supabase.table("contacts").select(
                "name, title, email, department"
            ).eq("salesforce_account_id", salesforce_account_id).limit(20).execute()
            context["contacts"] = contacts_result.data or []

            # Fetch other opportunities for context
            opps_result = supabase.table("opportunities").select(
                "name, amount, stage_name, probability, close_date, is_won, is_closed"
            ).eq("salesforce_account_id", salesforce_account_id).limit(10).execute()
            context["other_opportunities"] = opps_result.data or []

        except Exception as e:
            logger.error(f"Error fetching account context: {e}")

        return context

    def _fetch_meeting_data(self, salesforce_account_id: str, gap_field: str) -> str:
        """Fetch recent meeting transcripts, prioritizing those mentioning the gap field."""
        supabase = get_supabase()
        if not supabase or not salesforce_account_id:
            return "No meeting data available."

        try:
            from datetime import datetime, timedelta
            cutoff = (datetime.utcnow() - timedelta(days=90)).isoformat()

            result = supabase.table("transcriptions").select(
                "transcription_text, meeting_subject, meeting_date"
            ).eq("salesforce_account_id", salesforce_account_id).gte(
                "meeting_date", cutoff
            ).order("meeting_date", desc=True).limit(10).execute()

            if not result.data:
                return "No recent meetings found for this account."

            # Format transcripts with meeting context
            formatted = []
            gap_label = GAP_FIELD_LABELS.get(gap_field, gap_field)

            for t in result.data:
                subject = t.get("meeting_subject", "Untitled")
                date = t.get("meeting_date", "Unknown date")
                text = t.get("transcription_text", "")[:4000]  # Truncate
                formatted.append(f"=== {subject} ({date}) ===\n{text}\n")

            return "\n".join(formatted)
        except Exception as e:
            logger.error(f"Error fetching meeting data: {e}")
            return "Error fetching meeting data."

    def _format_contacts_data(self, contacts: List[Dict[str, Any]]) -> str:
        """Format contacts for the prompt."""
        if not contacts:
            return "No contacts available."

        formatted = []
        for c in contacts:
            name = c.get("name", "Unknown")
            title = c.get("title", "No title")
            email = c.get("email", "")
            dept = c.get("department", "")
            parts = [f"- {name} ({title})"]
            if dept:
                parts.append(f"  Department: {dept}")
            if email:
                parts.append(f"  Email: {email}")
            formatted.append("\n".join(parts))

        return "\n".join(formatted)

    def _format_account_context(self, context: Dict[str, Any]) -> str:
        """Format account context for the prompt."""
        parts = []

        account = context.get("account_details")
        if account:
            parts.append(f"Industry: {account.get('industry', 'Unknown')}")
            parts.append(f"Tier: {account.get('account_tier', 'Unknown')}")
            if account.get("arr"):
                parts.append(f"ARR: ${account['arr']:,.0f}")
            if account.get("employee_count"):
                parts.append(f"Employees: {account['employee_count']}")

        other_opps = context.get("other_opportunities", [])
        if other_opps:
            parts.append("\nOther Opportunities at Account:")
            for o in other_opps[:5]:
                status = "Won" if o.get("is_won") else "Lost" if o.get("is_closed") else "Open"
                parts.append(
                    f"  - {o.get('name', 'Unknown')}: ${o.get('amount', 0):,.0f} "
                    f"({o.get('stage_name', 'Unknown')}) - {status}"
                )

        return "\n".join(parts) if parts else "No additional account context available."

    def _format_transcription_data(self, transcription_data: List[Dict[str, Any]]) -> str:
        """Format pre-fetched transcription data for the prompt."""
        if not transcription_data:
            return "No meeting transcripts provided."

        formatted = []
        for t in transcription_data:
            subject = t.get("subject", "Untitled Meeting")
            date = t.get("date", "Unknown date")
            text = t.get("text", "")
            if text:
                text = text[:4000] if len(text) > 4000 else text
                formatted.append(f"=== {subject} ({date}) ===\n{text}\n")

        return "\n".join(formatted) if formatted else "No meeting transcripts available."

    def _parse_json_result(self, result_text: str, gap_field: str) -> Dict[str, Any]:
        """Extract JSON from the crew result."""
        default = {
            "gap_field": gap_field,
            "gap_label": GAP_FIELD_LABELS.get(gap_field, gap_field),
            "suggested_questions": [],
            "email_snippet": "",
            "transcript_evidence": [],
            "coaching_tip": "",
            "next_best_action": None,
        }
        return extract_json_from_llm_response(result_text, default=default)

    def _create_agent(self):
        """Create the MEDDPICC gap analyst agent."""
        config = self._get_agent_config("meddpicc_gap_analyst")

        self.analyst = Agent(
            role=config.get("role", "MEDDPICC Gap Resolution Specialist"),
            goal=config.get("goal", "Generate targeted recommendations to resolve MEDDPICC gaps"),
            backstory=config.get("backstory", "Expert in MEDDPICC sales methodology"),
            verbose=config.get("verbose", True),
            allow_delegation=config.get("allow_delegation", False),
            llm=self.llm,
        )

    def _create_task(
        self,
        gap_field: str,
        gap_label: str,
        opportunity_name: str,
        account_name: str,
        amount: float,
        stage_name: str,
        close_date: str,
        owner_name: str,
        contacts_data: str,
        account_context: str,
        meeting_data: str,
    ):
        """Create the gap analysis task with data interpolation."""
        task_config = self._get_task_config("analyze_meddpicc_gap")

        description = task_config.get("description", "").format(
            gap_field=gap_field,
            gap_label=gap_label,
            opportunity_name=opportunity_name,
            account_name=account_name,
            amount=amount or 0,
            stage_name=stage_name or "Unknown",
            close_date=close_date or "Not set",
            owner_name=owner_name or "Unknown",
            contacts_data=contacts_data,
            account_context=account_context,
            meeting_data=meeting_data,
        )

        self.analyze_task = Task(
            description=description,
            expected_output=task_config.get("expected_output", "JSON analysis"),
            agent=self.analyst,
        )

    def run(
        self,
        opportunity_id: str,
        gap_field: str,
        user_id: Optional[str] = None,
        step_callback: Optional[callable] = None,
        opportunity_data: Optional[Dict[str, Any]] = None,
        transcription_data: Optional[List[Dict[str, Any]]] = None,
        salesforce_account_id: Optional[str] = None,
        contacts_data: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Run the MEDDPICC gap actions analysis.

        Args:
            opportunity_id: The opportunity ID (UUID or Salesforce ID)
            gap_field: The MEDDPICC field to analyze (e.g., 'economic_buyer', 'metrics')
            user_id: Optional user ID for context
            step_callback: Optional callback for progress updates
            opportunity_data: Optional pre-fetched opportunity data from Next.js
            transcription_data: Optional pre-fetched transcription data from Next.js
            salesforce_account_id: Optional Salesforce account ID for fetching context
            contacts_data: Optional pre-fetched contacts data

        Returns:
            Dict with gap analysis result and metadata
        """
        # Normalize gap_field
        gap_field = gap_field.lower().replace("-", "_").replace(" ", "_")
        gap_label = GAP_FIELD_LABELS.get(gap_field, gap_field.replace("_", " ").title())

        if step_callback:
            step_callback(f"Analyzing {gap_label} gap...")

        # Use pre-fetched opportunity data if provided, otherwise fetch from Supabase
        opportunity = None
        if opportunity_data and opportunity_data.get("name"):
            logger.info(f"Using pre-fetched opportunity data: {opportunity_data.get('name')}")
            opportunity = {
                "id": opportunity_data.get("id"),
                "salesforce_id": opportunity_data.get("salesforce_id"),
                "name": opportunity_data.get("name"),
                "amount": opportunity_data.get("amount"),
                "stage_name": opportunity_data.get("stage_name"),
                "probability": opportunity_data.get("probability"),
                "close_date": opportunity_data.get("close_date"),
                "owner_name": opportunity_data.get("owner_name"),
                "salesforce_account_id": opportunity_data.get("salesforce_account_id") or salesforce_account_id,
                "accounts": {
                    "name": opportunity_data.get("account_name"),
                    "industry": opportunity_data.get("account_industry"),
                    "account_tier": opportunity_data.get("account_tier"),
                } if opportunity_data.get("account_name") else None,
            }
        else:
            opportunity = self._fetch_opportunity(opportunity_id)

        if not opportunity:
            return {
                "success": False,
                "result": {
                    "gap_field": gap_field,
                    "gap_label": gap_label,
                    "suggested_questions": [],
                    "email_snippet": "",
                    "transcript_evidence": [],
                    "coaching_tip": "Unable to find opportunity data.",
                },
                "error": "Opportunity not found",
            }

        opportunity_name = opportunity.get("name", "Unknown Opportunity")
        account = opportunity.get("accounts") or {}
        account_name = account.get("name", "Unknown Account")
        sf_account_id = opportunity.get("salesforce_account_id") or salesforce_account_id

        if step_callback:
            step_callback("Gathering account context and contacts...")

        # Fetch or use pre-provided contacts
        if contacts_data:
            contacts = contacts_data
        else:
            contacts = self._fetch_contacts(sf_account_id)

        # Fetch account context
        account_context = self._fetch_account_context(sf_account_id)

        # Use pre-fetched transcription data or fetch from Supabase
        if transcription_data and len(transcription_data) > 0:
            logger.info(f"Using {len(transcription_data)} pre-fetched transcriptions")
            meeting_data = self._format_transcription_data(transcription_data)
        else:
            meeting_data = self._fetch_meeting_data(sf_account_id, gap_field)

        # Format data for prompt
        contacts_str = self._format_contacts_data(contacts)
        account_context_str = self._format_account_context(account_context)

        if step_callback:
            step_callback(f"Generating {gap_label} recommendations...")

        # Create agent and task
        self._create_agent()
        self._create_task(
            gap_field=gap_field,
            gap_label=gap_label,
            opportunity_name=opportunity_name,
            account_name=account_name,
            amount=opportunity.get("amount"),
            stage_name=opportunity.get("stage_name"),
            close_date=opportunity.get("close_date"),
            owner_name=opportunity.get("owner_name"),
            contacts_data=contacts_str,
            account_context=account_context_str,
            meeting_data=meeting_data,
        )

        # Run the crew
        crew = Crew(
            name="MEDDPICC Gap Actions Crew",
            agents=[self.analyst],
            tasks=[self.analyze_task],
            process=Process.sequential,
            verbose=False,
        )

        if step_callback:
            step_callback("Running analysis...")

        result = crew.kickoff()
        result_text = str(result)

        if step_callback:
            step_callback("Parsing results...")

        # Parse the JSON result
        parsed_result = self._parse_json_result(result_text, gap_field)

        # Ensure gap_field is set correctly
        parsed_result["gap_field"] = gap_field
        parsed_result["gap_label"] = gap_label

        # Get actual model info from LLM
        model_name = getattr(self.llm, 'model', 'unknown')
        provider = "openai"
        if "claude" in model_name.lower() or "anthropic" in model_name.lower():
            provider = "anthropic"
        elif "gemini" in model_name.lower():
            provider = "google"

        return {
            "success": True,
            "result": parsed_result,
            "opportunity_id": opportunity_id,
            "opportunity_name": opportunity_name,
            "account_name": account_name,
            "provider": provider,
            "model": model_name,
        }
