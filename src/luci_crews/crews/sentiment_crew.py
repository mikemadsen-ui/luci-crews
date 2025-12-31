"""
Sentiment Analysis Crew

Analyzes customer sentiment from communications and interactions.
"""

import os
import yaml
from typing import Optional
from crewai import Agent, Task, Crew, Process
from crewai import LLM


class SentimentCrew:
    """Crew for analyzing customer sentiment."""

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
        analyst_config = self.agents_config.get("sentiment_analyst", {})

        self.analyst = Agent(
            role=analyst_config.get("role", "Customer Sentiment Analyst"),
            goal=analyst_config.get("goal", "Analyze customer sentiment"),
            backstory=analyst_config.get("backstory", "Expert sentiment analyst"),
            verbose=analyst_config.get("verbose", True),
            allow_delegation=analyst_config.get("allow_delegation", False),
            llm=self.llm,
        )

    def _create_tasks(
        self,
        account_name: str,
        communications_data: Optional[str],
        support_data: Optional[str],
        meeting_notes: Optional[str],
    ):
        """Create tasks from configuration with data interpolation."""
        task_config = self.tasks_config.get("analyze_sentiment", {})

        description = task_config.get("description", "").format(
            account_name=account_name,
            communications_data=communications_data or "No communications data available",
            support_data=support_data or "No support data available",
            meeting_notes=meeting_notes or "No meeting notes available",
        )

        self.analyze_task = Task(
            description=description,
            expected_output=task_config.get("expected_output", "Sentiment analysis"),
            agent=self.analyst,
        )

    def run(
        self,
        account_name: str,
        communications_data: Optional[str] = None,
        support_data: Optional[str] = None,
        meeting_notes: Optional[str] = None,
    ) -> str:
        """Run the sentiment crew and return the analysis."""
        self._create_agents()
        self._create_tasks(
            account_name, communications_data,
            support_data, meeting_notes
        )

        crew = Crew(
            agents=[self.analyst],
            tasks=[self.analyze_task],
            process=Process.sequential,
            verbose=True,
        )

        result = crew.kickoff()
        return str(result)
