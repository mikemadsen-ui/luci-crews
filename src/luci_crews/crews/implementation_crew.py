"""
Implementation Project Analysis Crew

Analyzes implementation project health and provides recommendations.
"""

import os
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from crewai import Agent, Task, Crew, Process, LLM

from .base_crew import BaseCrew

logger = logging.getLogger(__name__)


class ImplementationCrew(BaseCrew):
    """Crew for analyzing implementation project health."""

    def _create_agents(self):
        """Create agents from configuration."""
        analyst_config = self._get_agent_config("implementation_analyst")

        self.analyst = Agent(
            role=analyst_config.get("role", "Implementation Project Analyst"),
            goal=analyst_config.get("goal", "Analyze implementation health"),
            backstory=analyst_config.get("backstory", "Expert implementation consultant"),
            verbose=analyst_config.get("verbose", True),
            allow_delegation=analyst_config.get("allow_delegation", False),
            llm=self.llm,
        )

    def _format_call_activity(self, call_activity: Optional[dict]) -> str:
        """Format call activity data into a readable string for the prompt."""
        if not call_activity:
            return "No call activity data available"

        lines = []
        metrics = call_activity.get("metrics", {})

        # Check calendar connection status - this is the IC's (Implementation Consultant's) calendar
        calendar_connected = metrics.get('calendarConnected', False)

        # Summary metrics
        lines.append("=== CALL ACTIVITY SUMMARY ===")
        lines.append(f"IC Calendar Status: {'CONNECTED' if calendar_connected else 'NOT CONNECTED'}")
        lines.append(f"- Total recent calls: {metrics.get('totalRecentCalls', 0)}")
        lines.append(f"- Calls in last 30 days: {metrics.get('callsLast30Days', 0)}")
        lines.append(f"- Calls in last 60 days: {metrics.get('callsLast60Days', 0)}")
        days_since = metrics.get('daysSinceLastCall')
        if days_since is not None:
            lines.append(f"- Days since last call: {days_since}")

        if calendar_connected:
            lines.append(f"- Upcoming calls scheduled: {metrics.get('upcomingCallsCount', 0)}")
            if metrics.get('nextCallDate'):
                lines.append(f"- Next scheduled call: {metrics.get('nextCallDate')}")
        else:
            lines.append("- Upcoming calls scheduled: DATA UNAVAILABLE")
            lines.append("  (IC has not connected their Google Calendar - upcoming meeting data cannot be retrieved)")

        # Recent calls (from Avoma transcriptions - always available)
        recent_calls = call_activity.get("recentCalls", [])
        if recent_calls:
            lines.append("\n=== RECENT CALLS (from Avoma) ===")
            for call in recent_calls[:5]:
                duration = f" ({call.get('duration_minutes', '?')} min)" if call.get('duration_minutes') else ""
                lines.append(f"- {call.get('date', 'Unknown date')}: {call.get('subject', 'Untitled')}{duration}")

        # Upcoming calls (requires calendar connection)
        if calendar_connected:
            upcoming_calls = call_activity.get("upcomingCalls", [])
            lines.append("\n=== UPCOMING CALLS (from IC's Google Calendar) ===")
            if upcoming_calls:
                for call in upcoming_calls:
                    lines.append(f"- {call.get('date', 'Unknown date')}: {call.get('subject', 'Untitled')}")
            else:
                lines.append("- No upcoming calls scheduled with this customer in the next 30 days")
                lines.append("  (This is normal if the project is stable or awaiting customer action)")

        # Important note for the AI
        lines.append("\n=== IMPORTANT CONTEXT ===")
        if calendar_connected:
            lines.append("The IC's calendar IS connected. If no upcoming calls are shown, it means")
            lines.append("there genuinely are no meetings scheduled - do NOT recommend connecting calendar.")
        else:
            lines.append("The IC's calendar is NOT connected. This is an internal tool limitation.")
            lines.append("Do NOT recommend the customer connect their calendar - this is about the IC's calendar.")
            lines.append("If recommending calendar connection, specify it's for the IC (internal action).")

        return "\n".join(lines)

    def _format_mavenlink_tasks(self, tasks: Optional[List[dict]]) -> str:
        """Format Mavenlink tasks into a readable string for the prompt, flagging risks."""
        if not tasks:
            return "No Mavenlink task data available"

        today = datetime.now().date()
        lines = []
        issues = []

        # Categorize tasks - check both completed_at field AND status field
        # Mavenlink API may not set completed_at even when status is 'completed'
        def is_completed(task):
            if task.get('completed_at'):
                return True
            status = (task.get('status') or '').lower()
            return status == 'completed'

        incomplete_tasks = [t for t in tasks if not is_completed(t)]
        completed_tasks = [t for t in tasks if is_completed(t)]

        # Summary
        lines.append("=== MAVENLINK TASKS SUMMARY ===")
        lines.append(f"- Total tasks/stories: {len(tasks)}")
        lines.append(f"- Completed: {len(completed_tasks)}")
        lines.append(f"- Incomplete: {len(incomplete_tasks)}")

        # Analyze incomplete tasks for issues
        overdue_tasks = []
        unassigned_tasks = []
        unassigned_client_tasks = []

        for task in incomplete_tasks:
            title = task.get('title', 'Untitled')
            due_date_str = task.get('due_date')
            has_assignee = task.get('has_assignee', False)
            is_client_task = task.get('is_client_task', False)
            assignee_names = task.get('assignee_names', [])

            # Check for overdue
            if due_date_str:
                try:
                    due_date = datetime.fromisoformat(due_date_str.replace('Z', '+00:00')).date()
                    if due_date < today:
                        days_overdue = (today - due_date).days
                        overdue_tasks.append({
                            'title': title,
                            'due_date': due_date_str,
                            'days_overdue': days_overdue,
                            'assignees': assignee_names
                        })
                except (ValueError, TypeError):
                    pass

            # Check for unassigned tasks
            if not has_assignee:
                unassigned_tasks.append({'title': title, 'is_client': is_client_task})
                if is_client_task:
                    unassigned_client_tasks.append(title)

        # Report issues
        if overdue_tasks:
            lines.append(f"\n=== OVERDUE TASKS ({len(overdue_tasks)}) - CRITICAL ===")
            for task in sorted(overdue_tasks, key=lambda x: x['days_overdue'], reverse=True):
                assignee_str = ', '.join(task['assignees']) if task['assignees'] else 'UNASSIGNED'
                lines.append(f"- {task['title']} (Due: {task['due_date']}, {task['days_overdue']} days overdue, Assigned: {assignee_str})")
            issues.append(f"{len(overdue_tasks)} overdue task(s)")

        if unassigned_client_tasks:
            lines.append(f"\n=== UNASSIGNED CLIENT TASKS ({len(unassigned_client_tasks)}) - HIGH RISK ===")
            for title in unassigned_client_tasks:
                lines.append(f"- {title}")
            issues.append(f"{len(unassigned_client_tasks)} unassigned client task(s)")

        if unassigned_tasks and not unassigned_client_tasks:
            other_unassigned = [t for t in unassigned_tasks if not t['is_client']]
            if other_unassigned:
                lines.append(f"\n=== UNASSIGNED TASKS ({len(other_unassigned)}) ===")
                for task in other_unassigned[:10]:  # Limit to 10
                    lines.append(f"- {task['title']}")
                if len(other_unassigned) > 10:
                    lines.append(f"  ... and {len(other_unassigned) - 10} more")

        # List upcoming tasks with due dates
        upcoming_tasks = []
        for task in incomplete_tasks:
            due_date_str = task.get('due_date')
            if due_date_str:
                try:
                    due_date = datetime.fromisoformat(due_date_str.replace('Z', '+00:00')).date()
                    if due_date >= today:
                        days_until = (due_date - today).days
                        upcoming_tasks.append({
                            'title': task.get('title', 'Untitled'),
                            'due_date': due_date_str,
                            'days_until': days_until,
                            'assignees': task.get('assignee_names', []),
                            'story_type': task.get('story_type', 'task')
                        })
                except (ValueError, TypeError):
                    pass

        if upcoming_tasks:
            lines.append(f"\n=== UPCOMING TASKS (next 30 days) ===")
            for task in sorted(upcoming_tasks, key=lambda x: x['days_until'])[:15]:
                if task['days_until'] <= 30:
                    assignee_str = ', '.join(task['assignees']) if task['assignees'] else 'UNASSIGNED'
                    type_label = f"[{task['story_type'].upper()}] " if task['story_type'] != 'task' else ''
                    lines.append(f"- {type_label}{task['title']} (Due: {task['due_date']}, in {task['days_until']} days, Assigned: {assignee_str})")

        # Tasks without due dates (potential concern)
        no_due_date = [t for t in incomplete_tasks if not t.get('due_date')]
        if no_due_date:
            lines.append(f"\n=== TASKS WITHOUT DUE DATES ({len(no_due_date)}) ===")
            for task in no_due_date[:10]:
                assignee_str = ', '.join(task.get('assignee_names', [])) if task.get('assignee_names') else 'UNASSIGNED'
                lines.append(f"- {task.get('title', 'Untitled')} (Assigned: {assignee_str})")
            if len(no_due_date) > 10:
                lines.append(f"  ... and {len(no_due_date) - 10} more")

        # Add issue summary at top if there are issues
        if issues:
            issue_summary = f"\n*** TASK ISSUES REQUIRING ATTENTION: {', '.join(issues)} ***\n"
            lines.insert(0, issue_summary)

        return "\n".join(lines)

    def _parse_json_result(self, result_text: str) -> Dict[str, Any]:
        """Extract JSON from the crew result, handling markdown code blocks."""
        default_result = {
            "status": "at_risk",
            "status_summary": "Analysis could not be parsed into structured format.",
            "score": 5,
            "executive_summary": result_text[:1000] if result_text else "Analysis unavailable.",
            "risks": [],
            "customer_engagement": {
                "assessment": "unknown",
                "meeting_frequency": "Unable to determine",
                "communication_gaps": [],
                "sentiment_indicators": [],
                "recommendations": []
            },
            "task_analysis": {
                "summary": "Unable to parse task analysis",
                "overdue_count": 0,
                "unassigned_count": 0,
                "overdue_tasks": [],
                "unassigned_tasks": [],
                "upcoming_milestones": []
            },
            "actions": [],
            "timeline_assessment": {
                "on_track": False,
                "confidence": "low",
                "notes": "Unable to determine timeline status"
            },
            "escalation": {
                "needed": False,
                "reason": None,
                "recommended_to": None
            },
            "coaching": "Review the raw analysis text for insights."
        }
        return extract_json_from_llm_response(result_text, default=default_result)

    def _create_tasks(
        self,
        project_name: str,
        account_name: str,
        project_status: Optional[str],
        start_date: Optional[str],
        target_go_live: Optional[str],
        completion_pct: Optional[float],
        hours_used: Optional[float],
        hours_budgeted: Optional[float],
        budget_used: Optional[float],
        budget_total: Optional[float],
        milestones_data: Optional[str],
        risks_data: Optional[str],
        call_activity: Optional[dict] = None,
        mavenlink_tasks: Optional[List[dict]] = None,
        data_availability_warnings: Optional[List[str]] = None,
    ):
        """Create tasks from configuration with data interpolation."""
        task_config = self._get_task_config("analyze_implementation")

        # Format data availability warnings
        if data_availability_warnings and len(data_availability_warnings) > 0:
            warnings_text = "\n\n=== ⚠️ DATA AVAILABILITY WARNINGS ===\n" + "\n".join(data_availability_warnings) + "\n\nIMPORTANT: You MUST acknowledge these data gaps in your analysis and clearly state that certain assessments cannot be made due to missing data.\n"
        else:
            warnings_text = ""

        # Format call activity data
        call_activity_text = self._format_call_activity(call_activity)

        # Format Mavenlink tasks data
        mavenlink_tasks_text = self._format_mavenlink_tasks(mavenlink_tasks)

        description = task_config.get("description", "").format(
            project_name=project_name,
            account_name=account_name,
            project_status=project_status or "Unknown",
            start_date=start_date or "Not set",
            target_go_live=target_go_live or "Not set",
            current_phase="Active",
            completion_pct=completion_pct or 0,
            hours_used=hours_used or 0,
            hours_budgeted=hours_budgeted or 0,
            budget_used=budget_used or 0,
            budget_total=budget_total or 0,
            milestones_data=milestones_data or "No milestone data available",
            risks_data=risks_data or "No risk data available",
            call_activity=call_activity_text,
            mavenlink_tasks=mavenlink_tasks_text,
        )

        # Prepend data availability warnings if any
        if warnings_text:
            description = warnings_text + "\n" + description

        self.analyze_task = Task(
            description=description,
            expected_output=task_config.get("expected_output", "Implementation health report"),
            agent=self.analyst,
        )

    def run(
        self,
        project_name: str,
        account_name: str,
        project_status: Optional[str] = None,
        start_date: Optional[str] = None,
        target_go_live: Optional[str] = None,
        completion_pct: Optional[float] = None,
        hours_used: Optional[float] = None,
        hours_budgeted: Optional[float] = None,
        budget_used: Optional[float] = None,
        budget_total: Optional[float] = None,
        milestones_data: Optional[str] = None,
        risks_data: Optional[str] = None,
        call_activity: Optional[dict] = None,
        mavenlink_tasks: Optional[List[dict]] = None,
        step_callback: Optional[callable] = None,
        data_availability_warnings: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Run the implementation crew and return structured analysis.

        Args:
            project_name: Name of the project
            account_name: Customer account name
            project_status: Current project status
            start_date: Project start date
            target_go_live: Target go-live date
            completion_pct: Completion percentage
            hours_used: Hours consumed
            hours_budgeted: Hours budgeted
            budget_used: Budget consumed
            budget_total: Total budget
            milestones_data: Formatted milestone info
            risks_data: Formatted risk info
            call_activity: Call activity data dict
            mavenlink_tasks: List of Mavenlink task dicts
            step_callback: Optional callback for progress updates
            data_availability_warnings: List of data gap warnings to include in analysis

        Returns:
            Dict with parsed result and metadata
        """
        if step_callback:
            step_callback("Creating analysis agents...")

        self._create_agents()
        self._create_tasks(
            project_name, account_name, project_status,
            start_date, target_go_live, completion_pct,
            hours_used, hours_budgeted, budget_used, budget_total,
            milestones_data, risks_data, call_activity, mavenlink_tasks,
            data_availability_warnings
        )

        if step_callback:
            step_callback("Running implementation health analysis...")

        crew = Crew(
            name="Implementation Health Crew",
            agents=[self.analyst],
            tasks=[self.analyze_task],
            process=Process.sequential,
            verbose=False,
        )

        result = crew.kickoff()
        result_text = str(result)

        if step_callback:
            step_callback("Parsing analysis results...")

        # Parse the JSON result
        parsed_result = self._parse_json_result(result_text)

        # Ensure score is a valid integer 1-10
        if parsed_result.get("score"):
            try:
                parsed_result["score"] = max(1, min(10, int(parsed_result["score"])))
            except (ValueError, TypeError):
                parsed_result["score"] = 5

        # Get actual model info from LLM
        model_name = getattr(self.llm, 'model', os.environ.get("OPENAI_MODEL_NAME", "gpt-4o-mini"))
        provider = "openai"
        if "claude" in model_name.lower() or "anthropic" in model_name.lower():
            provider = "anthropic"
        elif "gemini" in model_name.lower():
            provider = "google"

        return {
            "result": parsed_result,
            "provider": provider,
            "model": model_name,
        }
