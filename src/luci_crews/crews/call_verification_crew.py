"""
Call Verification Crew

Analyzes call transcripts to verify which agenda items were completed,
identify new action items, and flag items that need carry-forward.
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from crewai import Agent, Task, Crew, Process

from .base_crew import BaseCrew
from ..utils import extract_json_from_llm_response

logger = logging.getLogger(__name__)


class CallVerificationCrew(BaseCrew):
    """Crew for verifying agenda item completion from call transcripts."""

    def _create_agents(self):
        """Create agents from configuration."""
        analyst_config = self._get_agent_config("call_verification_analyst")

        self.analyst = Agent(
            role=analyst_config.get("role", "Call Verification Analyst"),
            goal=analyst_config.get("goal", "Verify agenda item completion from call transcripts"),
            backstory=analyst_config.get("backstory", "Expert at analyzing meeting transcripts"),
            verbose=analyst_config.get("verbose", True),
            allow_delegation=analyst_config.get("allow_delegation", False),
            llm=self.llm,
        )

    def _format_agenda_items(self, items: List[Dict]) -> str:
        """Format agenda items for verification."""
        if not items:
            return "No agenda items to verify"

        lines = []
        for item in items:
            lines.append(f"- ID: {item.get('id', 'unknown')}")
            lines.append(f"  Title: {item.get('title', 'Untitled')}")
            lines.append(f"  Type: {item.get('item_type', 'discussion')}")
            lines.append(f"  Priority: {item.get('priority', 'normal')}")
            if item.get("assigned_to_name"):
                lines.append(f"  Assigned to: {item['assigned_to_name']} ({item.get('assigned_to_type', 'unknown')})")
            if item.get("description"):
                lines.append(f"  Description: {item['description']}")
            if item.get("due_date"):
                lines.append(f"  Due date: {item['due_date']}")
            lines.append("")  # Empty line between items

        return "\n".join(lines)

    def _format_transcript(self, transcript: str, speakers: Optional[List[Dict]] = None) -> str:
        """Format transcript for analysis."""
        formatted = ["=== CALL TRANSCRIPT ==="]

        if speakers:
            formatted.append("\nSPEAKERS:")
            for speaker in speakers:
                name = speaker.get("name", "Unknown")
                role = speaker.get("role", "")
                company = speaker.get("company", "")
                info = f"- {name}"
                if role:
                    info += f" ({role})"
                if company:
                    info += f" - {company}"
                formatted.append(info)
            formatted.append("")

        formatted.append("\nTRANSCRIPT:")
        formatted.append(transcript)

        return "\n".join(formatted)

    def _format_context(self, project_name: str, account_name: str, call_date: str) -> str:
        """Format call context."""
        return f"""=== CALL CONTEXT ===
Project: {project_name}
Account: {account_name}
Call Date: {call_date}
"""

    def _create_task(self, context: str, agenda_items: str, transcript: str):
        """Create the verification task."""
        task_config = self._get_task_config("verify_call_completion")

        description = task_config.get("description", "Verify call completion").format(
            context=context,
            agenda_items=agenda_items,
            transcript=transcript
        )

        return Task(
            description=description,
            expected_output=task_config.get("expected_output", "JSON verification results"),
            agent=self.analyst,
        )

    def _parse_json_result(self, raw_result: str) -> Dict[str, Any]:
        """Parse the raw crew result into structured JSON."""
        return extract_json_from_llm_response(raw_result, default={"rawText": raw_result})

    def run(
        self,
        project_name: str,
        account_name: str,
        call_date: str,
        agenda_items: List[Dict],
        transcript: str,
        speakers: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Run the crew to verify agenda item completion.

        Args:
            project_name: Implementation project name
            account_name: Customer account name
            call_date: Date/time of the call
            agenda_items: List of agenda items to verify
            transcript: Full call transcript text
            speakers: Optional list of speaker information

        Returns:
            Dict with verified_items, new_action_items, and call_summary
        """
        self._create_agents()

        # Build context
        context = self._format_context(project_name, account_name, call_date)
        formatted_items = self._format_agenda_items(agenda_items)
        formatted_transcript = self._format_transcript(transcript, speakers)

        task = self._create_task(context, formatted_items, formatted_transcript)

        crew = Crew(
            agents=[self.analyst],
            tasks=[task],
            process=Process.sequential,
            verbose=False,
        )

        result = crew.kickoff()
        raw_result = str(result)

        parsed = self._parse_json_result(raw_result)

        return {
            "result": parsed,
            "raw_output": raw_result,
            "project_name": project_name,
            "account_name": account_name,
            "call_date": call_date,
            "items_verified": len(agenda_items),
            "analyzed_at": datetime.utcnow().isoformat(),
        }
