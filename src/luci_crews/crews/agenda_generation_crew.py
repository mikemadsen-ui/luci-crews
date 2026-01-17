"""
Call Agenda Generation Crew

Generates pre-call agendas by analyzing:
- Mavenlink tasks due within 14 days
- Previous incomplete agenda items (for carry-forward)
- Recent call context and deliverables
- Project milestones and status
"""

import os
import re
import json
import yaml
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from crewai import Agent, Task, Crew, Process
from crewai import LLM

from ..ai_settings_helper import create_llm_for_user, DEFAULT_AI_SETTINGS

logger = logging.getLogger(__name__)


class AgendaGenerationCrew:
    """Crew for generating call agendas for Implementation Consultants."""

    def __init__(self, user_id: Optional[str] = None):
        """Initialize the crew with optional user-specific AI settings."""
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

    def _create_agents(self):
        """Create agents from configuration."""
        planner_config = self.agents_config.get("call_agenda_planner", {})

        self.planner = Agent(
            role=planner_config.get("role", "Call Agenda Planner"),
            goal=planner_config.get("goal", "Generate effective call agendas for implementation projects"),
            backstory=planner_config.get("backstory", "Expert implementation consultant focused on call preparation"),
            verbose=planner_config.get("verbose", True),
            allow_delegation=planner_config.get("allow_delegation", False),
            llm=self.llm,
        )

    def _format_mavenlink_tasks(self, tasks: List[Dict]) -> str:
        """Format Mavenlink tasks for the prompt."""
        if not tasks:
            return "No Mavenlink tasks available"

        lines = ["=== MAVENLINK TASKS DUE WITHIN 14 DAYS ==="]

        # Sort by due date
        sorted_tasks = sorted(tasks, key=lambda t: t.get("due_date") or "9999-12-31")

        for task in sorted_tasks:
            due_date = task.get("due_date", "No due date")
            assignee = task.get("assignee_name", "Unassigned")
            status = task.get("status", "unknown")
            task_type = task.get("story_type", "task")

            # Flag overdue
            is_overdue = False
            if task.get("due_date"):
                try:
                    due = datetime.strptime(task["due_date"], "%Y-%m-%d")
                    if due < datetime.now() and status not in ["completed", "archived"]:
                        is_overdue = True
                except ValueError:
                    pass

            prefix = "[OVERDUE] " if is_overdue else ""
            lines.append(f"- {prefix}{task.get('title', 'Untitled')} (Due: {due_date})")
            lines.append(f"  Assignee: {assignee} | Type: {task_type} | Status: {status}")
            if task.get("description"):
                desc = task["description"][:200] + "..." if len(task.get("description", "")) > 200 else task.get("description", "")
                lines.append(f"  Description: {desc}")

        return "\n".join(lines)

    def _format_incomplete_items(self, items: List[Dict]) -> str:
        """Format incomplete items from previous calls for carry-forward."""
        if not items:
            return "No incomplete items from previous calls"

        lines = ["=== INCOMPLETE ITEMS FROM PREVIOUS CALLS ==="]
        lines.append("(These items should be carried forward to the new agenda)")

        for item in items:
            carry_count = item.get("carry_forward_count", 0)
            is_late = item.get("is_late", False)

            if is_late:
                prefix = "[LATE - CARRY FORWARD] "
            elif carry_count > 0:
                prefix = f"[RESCHEDULED x{carry_count}] "
            else:
                prefix = "[INCOMPLETE] "

            lines.append(f"- {prefix}{item.get('title', 'Untitled')}")
            lines.append(f"  Priority: {item.get('priority', 'normal')} | Type: {item.get('item_type', 'discussion')}")
            if item.get("assigned_to_name"):
                assignee_type = f" ({item.get('assigned_to_type', 'unknown')})" if item.get('assigned_to_type') else ""
                lines.append(f"  Assigned to: {item['assigned_to_name']}{assignee_type}")
            if item.get("due_date"):
                lines.append(f"  Original due date: {item['due_date']}")

            # Include original call info
            if item.get("call_subject"):
                lines.append(f"  From call: {item['call_subject']} on {item.get('call_scheduled_at', 'unknown date')}")

        return "\n".join(lines)

    def _format_recent_calls(self, calls: List[Dict]) -> str:
        """Format recent call summaries for context."""
        if not calls:
            return "No recent call history available"

        lines = ["=== RECENT CALL CONTEXT ==="]

        for call in calls[:5]:  # Last 5 calls
            lines.append(f"- {call.get('date', 'Unknown date')}: {call.get('subject', 'Untitled')}")
            if call.get("ai_summary"):
                summary = call["ai_summary"][:300] + "..." if len(call.get("ai_summary", "")) > 300 else call.get("ai_summary", "")
                lines.append(f"  Summary: {summary}")
            if call.get("key_outcomes"):
                lines.append(f"  Key outcomes: {call['key_outcomes']}")

        return "\n".join(lines)

    def _format_project_context(self, project: Dict) -> str:
        """Format project context for the prompt."""
        lines = ["=== PROJECT CONTEXT ==="]
        lines.append(f"Project: {project.get('project_name', 'Unknown')}")
        lines.append(f"Account: {project.get('account_name', 'Unknown')}")
        lines.append(f"Status: {project.get('project_status', 'Unknown')}")

        if project.get("target_go_live"):
            lines.append(f"Target Go-Live: {project['target_go_live']}")
        if project.get("completion_pct") is not None:
            lines.append(f"Completion: {project['completion_pct']}%")
        if project.get("days_until_go_live") is not None:
            days = project["days_until_go_live"]
            urgency = " (URGENT)" if days < 14 else " (approaching)" if days < 30 else ""
            lines.append(f"Days until go-live: {days}{urgency}")

        return "\n".join(lines)

    def _format_call_context(self, call_info: Dict) -> str:
        """Format the upcoming call context."""
        lines = ["=== UPCOMING CALL ==="]
        lines.append(f"Subject: {call_info.get('call_subject', 'Implementation Call')}")
        lines.append(f"Scheduled: {call_info.get('call_scheduled_at', 'Unknown')}")

        if call_info.get("attendees"):
            lines.append(f"Attendees: {', '.join(call_info['attendees'])}")

        return "\n".join(lines)

    def _create_task(self, context: str):
        """Create the agenda generation task."""
        task_config = self.tasks_config.get("generate_call_agenda", {})

        return Task(
            description=task_config.get("description", "Generate a comprehensive call agenda").format(
                context=context
            ),
            expected_output=task_config.get("expected_output", "JSON agenda items"),
            agent=self.planner,
        )

    def _parse_json_result(self, raw_result: str) -> Dict[str, Any]:
        """Parse the raw crew result into structured JSON."""
        try:
            # Try to extract JSON from the response
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', raw_result)
            if json_match:
                return json.loads(json_match.group(1))

            # Try to find JSON object directly
            json_match = re.search(r'\{[\s\S]*\}', raw_result)
            if json_match:
                return json.loads(json_match.group(0))

            # Return as text if no JSON found
            return {"rawText": raw_result}
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON: {e}")
            return {"rawText": raw_result, "parseError": str(e)}

    def run(
        self,
        project_name: str,
        account_name: str,
        project_status: str,
        call_subject: str,
        call_scheduled_at: str,
        target_go_live: Optional[str] = None,
        completion_pct: Optional[float] = None,
        mavenlink_tasks: Optional[List[Dict]] = None,
        incomplete_items: Optional[List[Dict]] = None,
        recent_calls: Optional[List[Dict]] = None,
        attendees: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Run the crew to generate a call agenda.

        Args:
            project_name: Implementation project name
            account_name: Customer account name
            project_status: Current project status
            call_subject: Subject of the upcoming call
            call_scheduled_at: Scheduled datetime of the call
            target_go_live: Target go-live date
            completion_pct: Project completion percentage
            mavenlink_tasks: List of Mavenlink tasks due within 14 days
            incomplete_items: List of incomplete items from previous agendas
            recent_calls: List of recent call summaries for context
            attendees: List of expected attendees

        Returns:
            Dict with agenda_items list and metadata
        """
        self._create_agents()

        # Calculate days until go-live
        days_until_go_live = None
        if target_go_live:
            try:
                go_live_date = datetime.strptime(target_go_live, "%Y-%m-%d")
                days_until_go_live = (go_live_date - datetime.now()).days
            except ValueError:
                pass

        # Build context
        project_context = self._format_project_context({
            "project_name": project_name,
            "account_name": account_name,
            "project_status": project_status,
            "target_go_live": target_go_live,
            "completion_pct": completion_pct,
            "days_until_go_live": days_until_go_live,
        })

        call_context = self._format_call_context({
            "call_subject": call_subject,
            "call_scheduled_at": call_scheduled_at,
            "attendees": attendees,
        })

        tasks_context = self._format_mavenlink_tasks(mavenlink_tasks or [])
        incomplete_context = self._format_incomplete_items(incomplete_items or [])
        calls_context = self._format_recent_calls(recent_calls or [])

        full_context = "\n\n".join([
            project_context,
            call_context,
            tasks_context,
            incomplete_context,
            calls_context,
        ])

        task = self._create_task(full_context)

        crew = Crew(
            agents=[self.planner],
            tasks=[task],
            process=Process.sequential,
            verbose=True,
        )

        result = crew.kickoff()
        raw_result = str(result)

        parsed = self._parse_json_result(raw_result)

        return {
            "result": parsed,
            "raw_output": raw_result,
            "project_name": project_name,
            "account_name": account_name,
            "call_subject": call_subject,
            "call_scheduled_at": call_scheduled_at,
            "analyzed_at": datetime.utcnow().isoformat(),
        }
