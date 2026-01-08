"""
Sales Pipeline Analysis Crew

Analyzes sales opportunities and provides strategic recommendations.
"""

import os
import yaml
from typing import Optional
from crewai import Agent, Task, Crew, Process
from crewai import LLM

from ..ai_settings_helper import create_llm_for_user, DEFAULT_AI_SETTINGS


class SalesPipelineCrew:
    """Crew for analyzing sales pipeline and opportunities."""

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
        analyst_config = self.agents_config.get("sales_pipeline_analyst", {})
        strategist_config = self.agents_config.get("sales_strategist", {})

        self.analyst = Agent(
            role=analyst_config.get("role", "Sales Pipeline Analyst"),
            goal=analyst_config.get("goal", "Analyze sales pipeline health"),
            backstory=analyst_config.get("backstory", "Expert sales analyst"),
            verbose=analyst_config.get("verbose", True),
            allow_delegation=analyst_config.get("allow_delegation", False),
            llm=self.llm,
        )

        self.strategist = Agent(
            role=strategist_config.get("role", "Sales Strategy Advisor"),
            goal=strategist_config.get("goal", "Develop winning strategies"),
            backstory=strategist_config.get("backstory", "Expert sales strategist"),
            verbose=strategist_config.get("verbose", True),
            allow_delegation=strategist_config.get("allow_delegation", False),
            llm=self.llm,
        )

    def _create_tasks(self, user_email: str, opportunities: list, summary: dict):
        """Create tasks from configuration with data interpolation."""
        analyze_config = self.tasks_config.get("analyze_pipeline", {})
        strategy_config = self.tasks_config.get("develop_deal_strategies", {})

        # Format opportunities data
        if opportunities:
            opps_text = "\n".join([
                f"- {opp.get('name', 'Unknown')}: ${opp.get('amount', 0):,.0f} | "
                f"{opp.get('stageName', 'Unknown Stage')} | "
                f"{opp.get('probability', 0)}% | "
                f"Close: {opp.get('closeDate', 'No date')}"
                for opp in opportunities[:20]  # Limit to top 20
            ])
        else:
            opps_text = "No opportunities data available"

        # Interpolate task description
        description = analyze_config.get("description", "").format(
            user_name=user_email,
            opportunities_data=opps_text,
            total_amount=summary.get("totalAmount", 0),
            opp_count=len(opportunities),
            avg_probability=summary.get("avgProbability", 0),
        )

        self.analyze_task = Task(
            description=description,
            expected_output=analyze_config.get("expected_output", "Pipeline analysis"),
            agent=self.analyst,
        )

        self.strategy_task = Task(
            description=strategy_config.get("description", "Develop deal strategies"),
            expected_output=strategy_config.get("expected_output", "Strategic recommendations"),
            agent=self.strategist,
            context=[self.analyze_task],
        )

    def run(
        self,
        user_email: str,
        opportunities: list,
        summary: Optional[dict] = None,
    ) -> str:
        """Run the sales pipeline crew and return the analysis."""
        summary = summary or {}

        # Create agents and tasks
        self._create_agents()
        self._create_tasks(user_email, opportunities, summary)

        # Create and run crew
        crew = Crew(
            agents=[self.analyst, self.strategist],
            tasks=[self.analyze_task, self.strategy_task],
            process=Process.sequential,
            verbose=True,
        )

        result = crew.kickoff()
        return str(result)
