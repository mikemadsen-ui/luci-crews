"""
Account Health Analysis Crew

Analyzes customer account health and provides recommendations.
"""

import os
import yaml
from typing import Optional
from crewai import Agent, Task, Crew, Process
from crewai import LLM

from ..ai_settings_helper import create_llm_for_user, DEFAULT_AI_SETTINGS


class AccountHealthCrew:
    """Crew for analyzing account health and churn risk."""

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

    def _create_agents(self):
        """Create agents from configuration."""
        analyst_config = self.agents_config.get("account_health_analyst", {})

        self.analyst = Agent(
            role=analyst_config.get("role", "Customer Success Analyst"),
            goal=analyst_config.get("goal", "Assess account health"),
            backstory=analyst_config.get("backstory", "Expert customer success analyst"),
            verbose=analyst_config.get("verbose", True),
            allow_delegation=analyst_config.get("allow_delegation", False),
            llm=self.llm,
        )

    def _create_tasks(
        self,
        account_name: str,
        account_tier: Optional[str],
        arr: Optional[float],
        activity_data: Optional[str],
        support_data: Optional[str],
        engagement_data: Optional[str],
    ):
        """Create tasks from configuration with data interpolation."""
        task_config = self.tasks_config.get("assess_account_health", {})

        description = task_config.get("description", "").format(
            account_name=account_name,
            account_tier=account_tier or "Unknown",
            arr=arr or 0,
            activity_data=activity_data or "No activity data available",
            support_data=support_data or "No support data available",
            engagement_data=engagement_data or "No engagement data available",
        )

        self.analyze_task = Task(
            description=description,
            expected_output=task_config.get("expected_output", "Account health assessment"),
            agent=self.analyst,
        )

    def run(
        self,
        account_name: str,
        account_tier: Optional[str] = None,
        arr: Optional[float] = None,
        activity_data: Optional[str] = None,
        support_data: Optional[str] = None,
        engagement_data: Optional[str] = None,
    ) -> str:
        """Run the account health crew and return the analysis."""
        self._create_agents()
        self._create_tasks(
            account_name, account_tier, arr,
            activity_data, support_data, engagement_data
        )

        crew = Crew(
            agents=[self.analyst],
            tasks=[self.analyze_task],
            process=Process.sequential,
            verbose=False,
        )

        result = crew.kickoff()
        return str(result)
