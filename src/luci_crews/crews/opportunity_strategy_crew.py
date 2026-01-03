"""
Opportunity Strategy Crew

McKinsey-style analysis of enterprise opportunities, providing comprehensive
deal qualification, stakeholder mapping, competitive positioning, and winning strategy.
"""

import os
import re
import json
import yaml
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from crewai import Agent, Task, Crew, Process
from crewai import LLM

from ..config_store import get_supabase

logger = logging.getLogger(__name__)


class OpportunityStrategyCrew:
    """Crew for strategic analysis of sales opportunities."""

    def __init__(self):
        self.llm = LLM(
            model=os.environ.get("OPENAI_MODEL_NAME", "gpt-4o"),
            api_key=os.environ.get("OPENAI_API_KEY"),
        )
        self._load_configs()

    def _load_configs(self):
        """Load agent and task configurations from YAML files."""
        config_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")

        with open(os.path.join(config_dir, "agents.yaml"), 'r') as f:
            self.agents_config = yaml.safe_load(f)

        with open(os.path.join(config_dir, "tasks.yaml"), 'r') as f:
            self.tasks_config = yaml.safe_load(f)

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
            ).eq("id", opportunity_id).maybeSingle().execute()

            if not result.data:
                # Try by Salesforce ID
                result = supabase.table("opportunities").select(
                    "*, accounts(id, name, industry, account_tier, salesforce_id)"
                ).eq("salesforce_id", opportunity_id).maybeSingle().execute()

            return result.data
        except Exception as e:
            logger.error(f"Error fetching opportunity: {e}")
            return None

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
            ).eq("salesforce_id", salesforce_account_id).maybeSingle().execute()
            context["account_details"] = account_result.data

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

    def _fetch_meeting_data(self, salesforce_account_id: str) -> str:
        """Fetch recent meeting transcripts for the account."""
        supabase = get_supabase()
        if not supabase or not salesforce_account_id:
            return "No meeting data available."

        try:
            cutoff = (datetime.utcnow() - timedelta(days=90)).isoformat()
            result = supabase.table("transcriptions").select(
                "transcription_text, meeting_subject, meeting_date"
            ).eq("salesforce_account_id", salesforce_account_id).gte(
                "meeting_date", cutoff
            ).order("meeting_date", desc=True).limit(5).execute()

            if not result.data:
                return "No recent meetings found."

            formatted = []
            for t in result.data:
                subject = t.get("meeting_subject", "Untitled")
                date = t.get("meeting_date", "Unknown date")
                text = t.get("transcription_text", "")[:3000]  # Truncate
                formatted.append(f"=== {subject} ({date}) ===\n{text}\n")

            return "\n".join(formatted)
        except Exception as e:
            logger.error(f"Error fetching meeting data: {e}")
            return "Error fetching meeting data."

    def _fetch_support_data(self, salesforce_account_id: str) -> str:
        """Fetch recent support cases for the account."""
        supabase = get_supabase()
        if not supabase or not salesforce_account_id:
            return "No support data available."

        try:
            result = supabase.table("cases").select(
                "subject, status, priority, created_date, description"
            ).eq("salesforce_account_id", salesforce_account_id).order(
                "created_date", desc=True
            ).limit(10).execute()

            if not result.data:
                return "No support cases found."

            formatted = []
            for c in result.data:
                formatted.append(
                    f"- [{c.get('priority', 'N/A')}] {c.get('subject', 'No subject')} "
                    f"({c.get('status', 'Unknown')}): {(c.get('description') or '')[:200]}"
                )

            return "\n".join(formatted)
        except Exception as e:
            logger.error(f"Error fetching support data: {e}")
            return "Error fetching support data."

    def _format_opportunity_details(self, opp: Dict[str, Any]) -> str:
        """Format opportunity details for the prompt."""
        details = []
        if opp.get("type"):
            details.append(f"Type: {opp['type']}")
        if opp.get("lead_source"):
            details.append(f"Lead Source: {opp['lead_source']}")
        if opp.get("next_step"):
            details.append(f"Next Step: {opp['next_step']}")
        if opp.get("description"):
            details.append(f"Description: {opp['description'][:1000]}")
        if opp.get("fiscal_quarter") and opp.get("fiscal_year"):
            details.append(f"Fiscal Period: Q{opp['fiscal_quarter']} FY{opp['fiscal_year']}")

        return "\n".join(details) if details else "No additional details available."

    def _format_account_context(self, context: Dict[str, Any]) -> str:
        """Format account context for the prompt."""
        parts = []

        # Account details
        account = context.get("account_details")
        if account:
            parts.append(f"Industry: {account.get('industry', 'Unknown')}")
            parts.append(f"Tier: {account.get('account_tier', 'Unknown')}")
            if account.get("arr"):
                parts.append(f"ARR: ${account['arr']:,.0f}")
            if account.get("employee_count"):
                parts.append(f"Employees: {account['employee_count']}")

        # Contacts
        contacts = context.get("contacts", [])
        if contacts:
            parts.append("\nKey Contacts:")
            for c in contacts[:10]:
                parts.append(f"  - {c.get('name', 'Unknown')} ({c.get('title', 'No title')})")

        # Other opportunities
        other_opps = context.get("other_opportunities", [])
        if other_opps:
            parts.append("\nOther Opportunities at Account:")
            for o in other_opps:
                status = "Won" if o.get("is_won") else "Lost" if o.get("is_closed") else "Open"
                parts.append(
                    f"  - {o.get('name', 'Unknown')}: ${o.get('amount', 0):,.0f} "
                    f"({o.get('stage_name', 'Unknown')}) - {status}"
                )

        return "\n".join(parts) if parts else "No additional account context available."

    def _compute_input_hash(self, opportunity_id: str, data_length: int) -> str:
        """Compute a hash for caching."""
        content = f"{opportunity_id}:{data_length}:{datetime.utcnow().strftime('%Y-%m-%d')}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _parse_json_result(self, result_text: str) -> Dict[str, Any]:
        """Extract JSON from the crew result."""
        # Try to find JSON in code blocks
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', result_text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find raw JSON object
        brace_match = re.search(r'\{[\s\S]*\}', result_text)
        if brace_match:
            try:
                return json.loads(brace_match.group())
            except json.JSONDecodeError:
                pass

        # Return default structure if parsing fails
        logger.warning("Failed to parse JSON from crew result")
        return {
            "score": 5,
            "win_probability_assessment": "Unable to assess",
            "executive_summary": result_text[:500] if result_text else "Analysis could not be parsed.",
            "qualification": {"score": 5, "assessment": "Unable to parse"},
            "stakeholders": {},
            "value_proposition": {},
            "competitive_position": {},
            "risks": [],
            "critical_path": {},
            "winning_theme": "",
            "red_flags": [],
            "coaching_for_rep": "",
        }

    def _create_agent(self):
        """Create the deal strategist agent."""
        config = self.agents_config.get("deal_strategist", {})

        self.strategist = Agent(
            role=config.get("role", "Senior Deal Strategist"),
            goal=config.get("goal", "Develop winning deal strategies"),
            backstory=config.get("backstory", "Expert deal strategist"),
            verbose=config.get("verbose", True),
            allow_delegation=config.get("allow_delegation", False),
            llm=self.llm,
        )

    def _create_task(
        self,
        opportunity_name: str,
        account_name: str,
        amount: float,
        stage_name: str,
        probability: int,
        close_date: str,
        owner_name: str,
        opportunity_details: str,
        account_context: str,
        meeting_data: str,
        support_data: str,
    ):
        """Create the analysis task with data interpolation."""
        task_config = self.tasks_config.get("analyze_opportunity_strategy", {})

        description = task_config.get("description", "").format(
            opportunity_name=opportunity_name,
            account_name=account_name,
            amount=amount or 0,
            stage_name=stage_name or "Unknown",
            probability=probability or 0,
            close_date=close_date or "Not set",
            owner_name=owner_name or "Unknown",
            opportunity_details=opportunity_details,
            account_context=account_context,
            meeting_data=meeting_data,
            support_data=support_data,
        )

        self.analyze_task = Task(
            description=description,
            expected_output=task_config.get("expected_output", "JSON analysis"),
            agent=self.strategist,
        )

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
                # Truncate long transcripts
                text = text[:4000] if len(text) > 4000 else text
                formatted.append(f"=== {subject} ({date}) ===\n{text}\n")

        return "\n".join(formatted) if formatted else "No meeting transcripts available."

    def run(
        self,
        opportunity_id: str,
        user_id: Optional[str] = None,
        force_refresh: bool = False,
        step_callback: Optional[callable] = None,
        opportunity_data: Optional[Dict[str, Any]] = None,
        transcription_data: Optional[List[Dict[str, Any]]] = None,
        salesforce_account_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run the opportunity strategy analysis.

        Args:
            opportunity_id: The opportunity ID (UUID or Salesforce ID)
            user_id: Optional user ID for context
            force_refresh: If True, bypass cache
            step_callback: Optional callback for progress updates
            opportunity_data: Optional pre-fetched opportunity data from Next.js
            transcription_data: Optional pre-fetched transcription data from Next.js
            salesforce_account_id: Optional Salesforce account ID for fetching context

        Returns:
            Dict with analysis result and metadata
        """
        if step_callback:
            step_callback("Fetching opportunity data...")

        # Use pre-fetched opportunity data if provided, otherwise fetch from Supabase
        opportunity = None
        if opportunity_data and opportunity_data.get("name"):
            logger.info(f"Using pre-fetched opportunity data: {opportunity_data.get('name')}")
            # Convert the data format to match what _fetch_opportunity returns
            opportunity = {
                "id": opportunity_data.get("id"),
                "salesforce_id": opportunity_data.get("salesforce_id"),
                "name": opportunity_data.get("name"),
                "amount": opportunity_data.get("amount"),
                "stage_name": opportunity_data.get("stage_name"),
                "probability": opportunity_data.get("probability"),
                "close_date": opportunity_data.get("close_date"),
                "type": opportunity_data.get("type"),
                "lead_source": opportunity_data.get("lead_source"),
                "next_step": opportunity_data.get("next_step"),
                "description": opportunity_data.get("description"),
                "is_won": opportunity_data.get("is_won"),
                "is_closed": opportunity_data.get("is_closed"),
                "owner_name": opportunity_data.get("owner_name"),
                "owner_email": opportunity_data.get("owner_email"),
                "fiscal_quarter": opportunity_data.get("fiscal_quarter"),
                "fiscal_year": opportunity_data.get("fiscal_year"),
                "salesforce_account_id": opportunity_data.get("salesforce_account_id") or salesforce_account_id,
                "accounts": {
                    "name": opportunity_data.get("account_name"),
                    "industry": opportunity_data.get("account_industry"),
                    "account_tier": opportunity_data.get("account_tier"),
                } if opportunity_data.get("account_name") else None,
            }
        else:
            # Fallback to fetching from Supabase
            opportunity = self._fetch_opportunity(opportunity_id)

        if not opportunity:
            return {
                "result": {
                    "score": None,
                    "executive_summary": "Opportunity not found.",
                },
                "input_hash": None,
                "error": "Opportunity not found",
            }

        opportunity_name = opportunity.get("name", "Unknown Opportunity")
        account = opportunity.get("accounts") or {}
        account_name = account.get("name", "Unknown Account")
        salesforce_account_id = opportunity.get("salesforce_account_id")

        if step_callback:
            step_callback("Gathering account context...")

        # Fetch context data
        account_context = self._fetch_account_context(salesforce_account_id)

        # Use pre-fetched transcription data if provided, otherwise fetch from Supabase
        if transcription_data and len(transcription_data) > 0:
            logger.info(f"Using {len(transcription_data)} pre-fetched transcriptions")
            meeting_data = self._format_transcription_data(transcription_data)
        else:
            meeting_data = self._fetch_meeting_data(salesforce_account_id)

        support_data = self._fetch_support_data(salesforce_account_id)

        # Format data for prompt
        opportunity_details = self._format_opportunity_details(opportunity)
        account_context_str = self._format_account_context(account_context)

        # Compute input hash
        total_length = len(opportunity_details) + len(account_context_str) + len(meeting_data) + len(support_data)
        input_hash = self._compute_input_hash(opportunity_id, total_length)

        if step_callback:
            step_callback("Running strategic analysis...")

        # Create agent and task
        self._create_agent()
        self._create_task(
            opportunity_name=opportunity_name,
            account_name=account_name,
            amount=opportunity.get("amount"),
            stage_name=opportunity.get("stage_name"),
            probability=opportunity.get("probability"),
            close_date=opportunity.get("close_date"),
            owner_name=opportunity.get("owner_name"),
            opportunity_details=opportunity_details,
            account_context=account_context_str,
            meeting_data=meeting_data,
            support_data=support_data,
        )

        # Run the crew
        crew = Crew(
            agents=[self.strategist],
            tasks=[self.analyze_task],
            process=Process.sequential,
            verbose=True,
        )

        if step_callback:
            step_callback("Analyzing qualification, stakeholders, and competitive position...")

        result = crew.kickoff()
        result_text = str(result)

        if step_callback:
            step_callback("Parsing results...")

        # Parse the JSON result
        parsed_result = self._parse_json_result(result_text)

        # Ensure score is valid
        if parsed_result.get("score"):
            try:
                parsed_result["score"] = max(1, min(10, int(parsed_result["score"])))
            except (ValueError, TypeError):
                parsed_result["score"] = 5

        return {
            "result": parsed_result,
            "input_hash": input_hash,
            "opportunity_id": opportunity_id,
            "opportunity_name": opportunity_name,
            "account_name": account_name,
            "provider": "openai",
            "model": os.environ.get("OPENAI_MODEL_NAME", "gpt-4o"),
        }
