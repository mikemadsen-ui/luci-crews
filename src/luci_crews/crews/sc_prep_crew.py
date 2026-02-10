"""
SC Prep Crew

Helps Solutions Consultants prepare for discovery calls and demos by analyzing
opportunity context, synthesizing discovery findings, and generating demo prep
materials including competitive battle cards and objection handling.
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
from ..ai_settings_helper import create_llm_for_user, DEFAULT_AI_SETTINGS

logger = logging.getLogger(__name__)


class SCPrepCrew:
    """Crew for SC discovery and demo preparation."""

    def __init__(self, user_id: Optional[str] = None):
        """Initialize the crew with optional user-specific AI settings.

        Args:
            user_id: Optional user ID to fetch management-level AI settings.
                    If not provided, uses default settings.
        """
        self.user_id = user_id
        if user_id:
            self.llm = create_llm_for_user(user_id)
        else:
            self.llm = LLM(
                model=os.environ.get("OPENAI_MODEL_NAME", DEFAULT_AI_SETTINGS["model_id"]),
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
                "*, accounts(id, name, industry, account_tier, salesforce_id, website, employee_count)"
            ).eq("id", opportunity_id).maybeSingle().execute()

            if not result.data:
                # Try by Salesforce ID
                result = supabase.table("opportunities").select(
                    "*, accounts(id, name, industry, account_tier, salesforce_id, website, employee_count)"
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
            "tech_stack": [],
        }

        try:
            # Fetch account details
            account_result = supabase.table("accounts").select(
                "name, industry, account_tier, arr, employee_count, website"
            ).eq("salesforce_id", salesforce_account_id).maybeSingle().execute()
            context["account_details"] = account_result.data

            # Fetch contacts - focus on decision makers and technical folks
            contacts_result = supabase.table("contacts").select(
                "name, title, email, department"
            ).eq("salesforce_account_id", salesforce_account_id).limit(30).execute()
            context["contacts"] = contacts_result.data or []

            # Fetch other opportunities for context (won deals show successful patterns)
            opps_result = supabase.table("opportunities").select(
                "name, amount, stage_name, probability, close_date, is_won, is_closed, type"
            ).eq("salesforce_account_id", salesforce_account_id).limit(10).execute()
            context["other_opportunities"] = opps_result.data or []

        except Exception as e:
            logger.error(f"Error fetching account context: {e}")

        return context

    def _fetch_meeting_transcripts(self, salesforce_account_id: str, limit: int = 5) -> str:
        """Fetch recent meeting transcripts for discovery synthesis."""
        supabase = get_supabase()
        if not supabase or not salesforce_account_id:
            return "No meeting data available."

        try:
            cutoff = (datetime.utcnow() - timedelta(days=90)).isoformat()
            result = supabase.table("transcriptions").select(
                "transcription_text, meeting_subject, meeting_date"
            ).eq("salesforce_account_id", salesforce_account_id).gte(
                "meeting_date", cutoff
            ).order("meeting_date", desc=True).limit(limit).execute()

            if not result.data:
                return "No recent meetings found."

            formatted = []
            for t in result.data:
                subject = t.get("meeting_subject", "Untitled")
                date = t.get("meeting_date", "Unknown date")
                text = t.get("transcription_text", "")[:4000]  # Truncate
                formatted.append(f"=== {subject} ({date}) ===\n{text}\n")

            return "\n".join(formatted)
        except Exception as e:
            logger.error(f"Error fetching meeting data: {e}")
            return "Error fetching meeting data."

    def _fetch_support_cases(self, salesforce_account_id: str) -> str:
        """Fetch support cases to understand technical challenges."""
        supabase = get_supabase()
        if not supabase or not salesforce_account_id:
            return "No support data available."

        try:
            result = supabase.table("cases").select(
                "subject, status, priority, created_date, description, type"
            ).eq("salesforce_account_id", salesforce_account_id).order(
                "created_date", desc=True
            ).limit(15).execute()

            if not result.data:
                return "No support cases found."

            formatted = []
            for c in result.data:
                formatted.append(
                    f"- [{c.get('priority', 'N/A')}] {c.get('subject', 'No subject')} "
                    f"({c.get('status', 'Unknown')} - {c.get('type', 'N/A')}): "
                    f"{(c.get('description') or '')[:300]}"
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
            details.append(f"Description: {opp['description'][:1500]}")
        if opp.get("stage_name"):
            details.append(f"Current Stage: {opp['stage_name']}")

        return "\n".join(details) if details else "No additional details available."

    def _format_contacts(self, contacts: List[Dict[str, Any]]) -> str:
        """Format contacts with emphasis on roles relevant to SC."""
        if not contacts:
            return "No contacts found."

        # Prioritize technical and decision-making roles
        priority_keywords = ['vp', 'director', 'manager', 'lead', 'architect', 'engineer',
                           'admin', 'operations', 'revenue', 'sales ops', 'marketing ops']

        prioritized = []
        others = []

        for c in contacts:
            title = (c.get('title') or '').lower()
            is_priority = any(kw in title for kw in priority_keywords)
            entry = f"- {c.get('name', 'Unknown')} | {c.get('title', 'No title')} | {c.get('department', '')}"
            if is_priority:
                prioritized.append(entry)
            else:
                others.append(entry)

        formatted = []
        if prioritized:
            formatted.append("Key Stakeholders:")
            formatted.extend(prioritized[:10])
        if others:
            formatted.append("\nOther Contacts:")
            formatted.extend(others[:5])

        return "\n".join(formatted)

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
            "discovery_synthesis": {
                "summary": result_text[:500] if result_text else "Analysis could not be parsed.",
                "key_findings": [],
                "business_drivers": [],
                "technical_requirements": [],
                "decision_criteria": [],
            },
            "demo_plan": {
                "recommended_flow": [],
                "key_features_to_highlight": [],
                "use_cases_to_demonstrate": [],
                "stakeholder_specific_value": {},
            },
            "competitive_intel": {
                "likely_competitors": [],
                "our_differentiators": [],
                "objection_responses": [],
            },
            "preparation_checklist": [],
            "questions_to_ask": [],
            "risks_and_concerns": [],
        }

    def _create_agent(self):
        """Create the SC prep specialist agent."""
        config = self.agents_config.get("sc_prep_specialist", {})

        self.specialist = Agent(
            role=config.get("role", "Senior Solutions Consultant"),
            goal=config.get("goal", "Prepare comprehensive discovery and demo materials"),
            backstory=config.get("backstory", "Expert solutions consultant"),
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
        close_date: str,
        opportunity_details: str,
        contacts_data: str,
        meeting_transcripts: str,
        support_data: str,
        prep_type: str,
    ):
        """Create the SC prep task with data interpolation."""
        task_config = self.tasks_config.get("prepare_sc_materials", {})

        description = task_config.get("description", "").format(
            opportunity_name=opportunity_name,
            account_name=account_name,
            amount=amount or 0,
            stage_name=stage_name or "Unknown",
            close_date=close_date or "Not set",
            opportunity_details=opportunity_details,
            contacts_data=contacts_data,
            meeting_transcripts=meeting_transcripts,
            support_data=support_data,
            prep_type=prep_type,
        )

        self.prep_task = Task(
            description=description,
            expected_output=task_config.get("expected_output", "JSON prep materials"),
            agent=self.specialist,
        )

    def run(
        self,
        opportunity_id: str,
        prep_type: str = "discovery",  # "discovery", "demo", "competitive", "full"
        user_id: Optional[str] = None,
        force_refresh: bool = False,
        step_callback: Optional[callable] = None,
        opportunity_data: Optional[Dict[str, Any]] = None,
        transcription_data: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Run the SC prep analysis.

        Args:
            opportunity_id: The opportunity ID (UUID or Salesforce ID)
            prep_type: Type of prep needed - "discovery", "demo", "competitive", or "full"
            user_id: Optional user ID for context
            force_refresh: If True, bypass cache
            step_callback: Optional callback for progress updates
            opportunity_data: Optional pre-fetched opportunity data
            transcription_data: Optional pre-fetched transcription data

        Returns:
            Dict with prep materials and metadata
        """
        if step_callback:
            step_callback("Fetching opportunity data...")

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
                "type": opportunity_data.get("type"),
                "lead_source": opportunity_data.get("lead_source"),
                "next_step": opportunity_data.get("next_step"),
                "description": opportunity_data.get("description"),
                "salesforce_account_id": opportunity_data.get("salesforce_account_id"),
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
                "result": {
                    "error": "Opportunity not found.",
                },
                "input_hash": None,
                "error": "Opportunity not found",
            }

        opportunity_name = opportunity.get("name", "Unknown Opportunity")
        account = opportunity.get("accounts") or {}
        account_name = account.get("name", "Unknown Account")
        salesforce_account_id = opportunity.get("salesforce_account_id")

        if step_callback:
            step_callback("Gathering account and contact information...")

        # Fetch context data
        account_context = self._fetch_account_context(salesforce_account_id)
        contacts_data = self._format_contacts(account_context.get("contacts", []))

        if step_callback:
            step_callback("Analyzing meeting transcripts...")

        # Use pre-fetched transcription data if provided
        if transcription_data and len(transcription_data) > 0:
            logger.info(f"Using {len(transcription_data)} pre-fetched transcriptions")
            formatted = []
            for t in transcription_data:
                subject = t.get("subject", "Untitled Meeting")
                date = t.get("date", "Unknown date")
                text = t.get("text", "")[:4000]
                if text:
                    formatted.append(f"=== {subject} ({date}) ===\n{text}\n")
            meeting_transcripts = "\n".join(formatted) if formatted else "No meeting transcripts available."
        else:
            meeting_transcripts = self._fetch_meeting_transcripts(salesforce_account_id)

        support_data = self._fetch_support_cases(salesforce_account_id)

        # Format data for prompt
        opportunity_details = self._format_opportunity_details(opportunity)

        # Compute input hash
        total_length = len(opportunity_details) + len(contacts_data) + len(meeting_transcripts) + len(support_data)
        input_hash = self._compute_input_hash(opportunity_id, total_length)

        if step_callback:
            step_callback(f"Generating {prep_type} preparation materials...")

        # Create agent and task
        self._create_agent()
        self._create_task(
            opportunity_name=opportunity_name,
            account_name=account_name,
            amount=opportunity.get("amount"),
            stage_name=opportunity.get("stage_name"),
            close_date=opportunity.get("close_date"),
            opportunity_details=opportunity_details,
            contacts_data=contacts_data,
            meeting_transcripts=meeting_transcripts,
            support_data=support_data,
            prep_type=prep_type,
        )

        # Run the crew
        crew = Crew(
            agents=[self.specialist],
            tasks=[self.prep_task],
            process=Process.sequential,
            verbose=False,
        )

        if step_callback:
            step_callback("Synthesizing discovery insights and building prep materials...")

        result = crew.kickoff()
        result_text = str(result)

        if step_callback:
            step_callback("Parsing results...")

        # Parse the JSON result
        parsed_result = self._parse_json_result(result_text)

        # Get actual model info from LLM
        model_name = getattr(self.llm, 'model', os.environ.get("OPENAI_MODEL_NAME", "gpt-4o"))
        provider = "openai"
        if "claude" in model_name.lower() or "anthropic" in model_name.lower():
            provider = "anthropic"
        elif "gemini" in model_name.lower():
            provider = "google"

        return {
            "result": parsed_result,
            "input_hash": input_hash,
            "opportunity_id": opportunity_id,
            "opportunity_name": opportunity_name,
            "account_name": account_name,
            "prep_type": prep_type,
            "provider": provider,
            "model": model_name,
        }
