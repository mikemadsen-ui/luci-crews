"""
Implementation Project Analysis Crew

Analyzes implementation project health and provides recommendations.
"""

import os
import yaml
from typing import Optional
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

        # Summary metrics
        lines.append("=== CALL ACTIVITY SUMMARY ===")
        lines.append(f"- Total recent calls: {metrics.get('totalRecentCalls', 0)}")
        lines.append(f"- Calls in last 30 days: {metrics.get('callsLast30Days', 0)}")
        lines.append(f"- Calls in last 60 days: {metrics.get('callsLast60Days', 0)}")
        days_since = metrics.get('daysSinceLastCall')
        if days_since is not None:
            lines.append(f"- Days since last call: {days_since}")
        lines.append(f"- Upcoming calls scheduled: {metrics.get('upcomingCallsCount', 0)}")
        if metrics.get('nextCallDate'):
            lines.append(f"- Next scheduled call: {metrics.get('nextCallDate')}")

        # Recent calls
        recent_calls = call_activity.get("recentCalls", [])
        if recent_calls:
            lines.append("\n=== RECENT CALLS ===")
            for call in recent_calls[:5]:
                duration = f" ({call.get('duration_minutes', '?')} min)" if call.get('duration_minutes') else ""
                lines.append(f"- {call.get('date', 'Unknown date')}: {call.get('subject', 'Untitled')}{duration}")

        # Upcoming calls
        upcoming_calls = call_activity.get("upcomingCalls", [])
        if upcoming_calls:
            lines.append("\n=== UPCOMING CALLS ===")
            for call in upcoming_calls:
                lines.append(f"- {call.get('date', 'Unknown date')}: {call.get('subject', 'Untitled')}")

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
    ):
        """Create tasks from configuration with data interpolation."""
        task_config = self.tasks_config.get("analyze_implementation", {})

        # Format call activity data
        call_activity_text = self._format_call_activity(call_activity)

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
    ) -> str:
        """Run the implementation crew and return the analysis."""
        self._create_agents()
        self._create_tasks(
            project_name, account_name, project_status,
            start_date, target_go_live, completion_pct,
            hours_used, hours_budgeted, budget_used, budget_total,
            milestones_data, risks_data, call_activity
        )

        crew = Crew(
            agents=[self.analyst],
            tasks=[self.analyze_task],
            process=Process.sequential,
            verbose=True,
        )

        result = crew.kickoff()
        return str(result)
