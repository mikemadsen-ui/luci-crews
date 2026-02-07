"""
Project Sentiment Analysis Crew

Analyzes implementation project health from meeting transcripts,
focusing on PM effectiveness and customer reception.
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
from ..avoma_mcp import get_avoma_client
from ..ai_settings_helper import create_llm_for_user, DEFAULT_AI_SETTINGS

logger = logging.getLogger(__name__)


class ProjectSentimentCrew:
    """Crew for analyzing project sentiment from meeting transcripts."""

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

    def _fetch_transcriptions(
        self,
        salesforce_account_id: str,
        transcription_ids: Optional[List[str]] = None,
        mavenlink_workspace_id: Optional[str] = None,
        use_mcp_fallback: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Fetch transcriptions from Supabase cache, with optional MCP/Mavenlink fallback.

        Args:
            salesforce_account_id: The Salesforce account ID
            transcription_ids: Optional list of specific transcription IDs
            mavenlink_workspace_id: Optional Mavenlink workspace ID for email fallback
            use_mcp_fallback: If True and cache is empty, try fetching from Avoma

        Returns:
            List of transcription dicts
        """
        supabase = get_supabase()
        transcriptions = []

        # Try Supabase cache first
        if supabase:
            try:
                select_cols = "id, transcription_text, meeting_subject, meeting_date, meeting_url, salesforce_account_id"

                if transcription_ids and len(transcription_ids) > 0:
                    result = supabase.table("transcriptions").select(
                        select_cols
                    ).in_("id", transcription_ids).execute()
                else:
                    cutoff = (datetime.utcnow() - timedelta(days=60)).isoformat()
                    result = supabase.table("transcriptions").select(
                        select_cols
                    ).eq("salesforce_account_id", salesforce_account_id).gte(
                        "meeting_date", cutoff
                    ).order("meeting_date", desc=True).limit(10).execute()

                for t in result.data or []:
                    transcriptions.append({
                        "id": t.get("id"),
                        "transcription": t.get("transcription_text"),
                        "meeting": {
                            "subject": t.get("meeting_subject"),
                            "meeting_date": t.get("meeting_date"),
                            "url": t.get("meeting_url"),
                        }
                    })
            except Exception as e:
                logger.error(f"Error fetching transcriptions from Supabase: {e}")
        else:
            logger.warning("Supabase not configured")

        # If cache is empty and MCP fallback is enabled, try Avoma with Mavenlink email fallback
        if not transcriptions and use_mcp_fallback:
            logger.info(f"No cached transcriptions for account {salesforce_account_id}, trying Avoma with fallback")
            try:
                avoma = get_avoma_client()
                # Use the new fallback method that tries CRM account ID first,
                # then falls back to customer emails from Mavenlink
                transcriptions = avoma.fetch_transcriptions_with_fallback(
                    salesforce_account_id=salesforce_account_id,
                    mavenlink_workspace_id=mavenlink_workspace_id,
                    limit=10,
                )
                if transcriptions:
                    logger.info(f"Fetched {len(transcriptions)} transcriptions from Avoma")
            except Exception as e:
                logger.error(f"Error fetching from Avoma: {e}")

        return transcriptions

    def _fetch_project(self, salesforce_project_id: str) -> Optional[Dict[str, Any]]:
        """Fetch project details from Supabase."""
        supabase = get_supabase()
        if not supabase:
            return None

        try:
            result = supabase.table("implementation_projects").select(
                "project_name, salesforce_account_id, mavenlink_workspace_id, account"
            ).eq("salesforce_project_id", salesforce_project_id).maybeSingle().execute()
            return result.data
        except Exception as e:
            logger.error(f"Error fetching project: {e}")
            return None

    def _format_transcripts(self, transcriptions: List[Dict[str, Any]]) -> str:
        """Format transcriptions for the prompt."""
        if not transcriptions:
            return "No transcriptions available for analysis."

        formatted = []
        for t in transcriptions:
            meeting = t.get("meeting", {}) or {}
            subject = meeting.get("subject", "Untitled Meeting")
            date = meeting.get("meeting_date", "Unknown date")
            transcript = t.get("transcription", "")

            # Truncate long transcripts
            if len(transcript) > 8000:
                transcript = transcript[:8000] + "\n[... truncated ...]"

            formatted.append(f"=== CALL: {subject} ({date}) ===\n{transcript}\n")

        return "\n".join(formatted)

    def _compute_input_hash(
        self,
        salesforce_project_id: str,
        transcription_ids: List[str],
        transcription_length: int,
    ) -> str:
        """Compute a hash for caching based on inputs."""
        content = f"{salesforce_project_id}:{','.join(sorted(transcription_ids))}:{transcription_length}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _parse_json_result(self, result_text: str) -> Dict[str, Any]:
        """Extract JSON from the crew result, handling markdown code blocks."""
        # Try to find JSON in code blocks first
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

        # Return a default structure if parsing fails
        logger.warning("Failed to parse JSON from crew result")
        return {
            "score": 5,
            "pm_effectiveness_score": 5,
            "summary": result_text[:500] if result_text else "Analysis could not be parsed.",
            "pm_summary": "",
            "customer_sentiment_summary": "",
            "timeline_deliverables_summary": "",
            "risks_summary": "",
            "deliverables": [],
            "timeline_dates": [],
            "participants_sentiment": {"customer": [], "pm": [], "notes": ""},
            "key_quotes": [],  # Each quote has: speaker, quote, sentiment (positive/negative/neutral), call, call_date
        }

    def _create_agents(self):
        """Create agents from configuration."""
        coach_config = self.agents_config.get("implementation_coach", {})

        self.coach = Agent(
            role=coach_config.get("role", "Implementation Coach"),
            goal=coach_config.get("goal", "Analyze project sentiment"),
            backstory=coach_config.get("backstory", "Expert implementation coach"),
            verbose=coach_config.get("verbose", True),
            allow_delegation=coach_config.get("allow_delegation", False),
            llm=self.llm,
        )

    def _create_tasks(
        self,
        project_name: str,
        account_name: str,
        transcripts_data: str,
    ):
        """Create tasks from configuration with data interpolation."""
        task_config = self.tasks_config.get("analyze_project_sentiment", {})

        description = task_config.get("description", "").format(
            project_name=project_name,
            account_name=account_name,
            transcripts_data=transcripts_data,
        )

        self.analyze_task = Task(
            description=description,
            expected_output=task_config.get("expected_output", "JSON analysis"),
            agent=self.coach,
        )

    def run(
        self,
        salesforce_project_id: str,
        salesforce_account_id: str,
        transcription_ids: Optional[List[str]] = None,
        force_refresh: bool = False,
        step_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        Run the project sentiment crew and return structured analysis.

        Args:
            salesforce_project_id: The Salesforce project ID
            salesforce_account_id: The Salesforce account ID
            transcription_ids: Optional list of specific transcription IDs to analyze
            force_refresh: If True, bypass cache
            step_callback: Optional callback for progress updates

        Returns:
            Dict with analysis result, input_hash, and metadata
        """
        if step_callback:
            step_callback("Fetching project data...")

        # Fetch project details
        project = self._fetch_project(salesforce_project_id)
        project_name = project.get("project_name", "Unknown Project") if project else "Unknown Project"
        account = project.get("account", {}) if project else {}
        account_name = account.get("name", "Unknown Account") if isinstance(account, dict) else "Unknown Account"
        mavenlink_workspace_id = project.get("mavenlink_workspace_id") if project else None

        if step_callback:
            step_callback("Fetching transcriptions...")

        # Fetch transcriptions (with Mavenlink email fallback if CRM account ID search fails)
        transcriptions = self._fetch_transcriptions(
            salesforce_account_id,
            transcription_ids,
            mavenlink_workspace_id=mavenlink_workspace_id,
        )

        if not transcriptions:
            return {
                "result": {
                    "score": None,
                    "pm_effectiveness_score": None,
                    "summary": "No transcriptions available for analysis.",
                    "pm_summary": "",
                    "customer_sentiment_summary": "",
                    "timeline_deliverables_summary": "",
                    "risks_summary": "",
                    "deliverables": [],
                    "timeline_dates": [],
                    "participants_sentiment": {},
                    "key_quotes": [],
                },
                "input_hash": None,
                "transcription_count": 0,
                "transcription_length": 0,
                "transcription_ids": [],
                "provider": "none",
                "model": "none",
            }

        # Format transcripts
        transcripts_data = self._format_transcripts(transcriptions)
        transcription_length = len(transcripts_data)
        actual_ids = [t.get("id") for t in transcriptions if t.get("id")]

        # Compute input hash for caching
        input_hash = self._compute_input_hash(
            salesforce_project_id,
            actual_ids,
            transcription_length,
        )

        if step_callback:
            step_callback("Running AI analysis...")

        # Create agents and tasks
        self._create_agents()
        self._create_tasks(project_name, account_name, transcripts_data)

        # Run the crew
        crew = Crew(
            name="Project Sentiment Crew",
            agents=[self.coach],
            tasks=[self.analyze_task],
            process=Process.sequential,
            verbose=True,
        )

        if step_callback:
            step_callback("Analyzing PM effectiveness and customer reception...")

        result = crew.kickoff()
        result_text = str(result)

        if step_callback:
            step_callback("Parsing results...")

        # Parse the JSON result
        parsed_result = self._parse_json_result(result_text)

        # Ensure scores are valid integers 1-10
        if parsed_result.get("score"):
            try:
                parsed_result["score"] = max(1, min(10, int(parsed_result["score"])))
            except (ValueError, TypeError):
                parsed_result["score"] = 5

        if parsed_result.get("pm_effectiveness_score"):
            try:
                parsed_result["pm_effectiveness_score"] = max(1, min(10, int(parsed_result["pm_effectiveness_score"])))
            except (ValueError, TypeError):
                parsed_result["pm_effectiveness_score"] = 5

        # Get actual model info from LLM
        model_name = getattr(self.llm, 'model', os.environ.get("OPENAI_MODEL_NAME", "gpt-4o-mini"))
        provider = "openai"
        if "claude" in model_name.lower() or "anthropic" in model_name.lower():
            provider = "anthropic"
        elif "gemini" in model_name.lower():
            provider = "google"

        return {
            "result": parsed_result,
            "input_hash": input_hash,
            "transcription_count": len(transcriptions),
            "transcription_length": transcription_length,
            "transcription_ids": actual_ids,
            "provider": provider,
            "model": model_name,
        }
