"""
Implementation Project Analysis Crew

Analyzes implementation project health and provides recommendations.
"""

import os
import yaml
from datetime import datetime
from typing import Optional, List
from crewai import Agent, Task, Crew, Process
from crewai import LLM


class ImplementationCrew:
    """Crew for analyzing implementation project health."""

    def __init__(self):
        self.llm = LLM(
            model=os.environ.get("OPENAI_MODEL_NAME", "gpt-4o-mini"),
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
        analyst_config = self.agents_config.get("implementation_analyst", {})

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

        # Check calendar connection status
        calendar_connected = metrics.get('calendarConnected', False)
        if not calendar_connected:
            lines.append("*** WARNING: CALENDAR NOT CONNECTED ***")
            lines.append("The user has not connected their Google Calendar.")
            lines.append("Upcoming meetings data is UNAVAILABLE - this may negatively affect")
            lines.append("the accuracy of customer engagement assessment.")
            lines.append("Recommend: Connect calendar in Settings for complete project visibility.")
            lines.append("")

        # Summary metrics
        lines.append("=== CALL ACTIVITY SUMMARY ===")
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
            lines.append("- Upcoming calls scheduled: UNKNOWN (calendar not connected)")

        # Recent calls (from Avoma transcriptions - always available)
        recent_calls = call_activity.get("recentCalls", [])
        if recent_calls:
            lines.append("\n=== RECENT CALLS ===")
            for call in recent_calls[:5]:
                duration = f" ({call.get('duration_minutes', '?')} min)" if call.get('duration_minutes') else ""
                lines.append(f"- {call.get('date', 'Unknown date')}: {call.get('subject', 'Untitled')}{duration}")

        # Upcoming calls (requires calendar connection)
        if calendar_connected:
            upcoming_calls = call_activity.get("upcomingCalls", [])
            if upcoming_calls:
                lines.append("\n=== UPCOMING CALLS ===")
                for call in upcoming_calls:
                    lines.append(f"- {call.get('date', 'Unknown date')}: {call.get('subject', 'Untitled')}")
            else:
                lines.append("\n=== UPCOMING CALLS ===")
                lines.append("- No upcoming calls scheduled in the next 30 days")

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
    ):
        """Create tasks from configuration with data interpolation."""
        task_config = self.tasks_config.get("analyze_implementation", {})

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
    ) -> str:
        """Run the implementation crew and return the analysis."""
        self._create_agents()
        self._create_tasks(
            project_name, account_name, project_status,
            start_date, target_go_live, completion_pct,
            hours_used, hours_budgeted, budget_used, budget_total,
            milestones_data, risks_data, call_activity, mavenlink_tasks
        )

        crew = Crew(
            agents=[self.analyst],
            tasks=[self.analyze_task],
            process=Process.sequential,
            verbose=True,
        )

        result = crew.kickoff()
        return str(result)
