"""
Account Health Analysis Crew

Analyzes customer account health and provides recommendations.
"""

import logging
from typing import Optional, Dict, Any
from crewai import Agent, Task, Crew, Process

from .base_crew import BaseCrew
from ..utils import extract_json_from_llm_response

logger = logging.getLogger(__name__)


class AccountHealthCrew(BaseCrew):
    """Crew for analyzing account health and churn risk."""

    def _create_agents(self):
        """Create agents from configuration."""
        analyst_config = self._get_agent_config("account_health_analyst")

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
        task_config = self._get_task_config("assess_account_health")

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

    def _parse_json_result(self, result_text: str) -> Dict[str, Any]:
        """Extract JSON from the crew result, handling markdown code blocks."""
        default = {
            "score": 5,
            "status": "stable",
            "trend": "stable",
            "summary": result_text[:500] if result_text else "Analysis could not be parsed.",
            "health_indicators": {},
            "strengths": [],
            "concerns": [],
            "churn_risk": {"level": "medium", "factors": [], "early_warnings": []},
            "expansion_opportunities": [],
            "stakeholder_analysis": {},
            "actions": [],
            "talking_points": [],
            "strategic_focus": "",
        }
        return extract_json_from_llm_response(result_text, default=default)

    def run(
        self,
        account_name: str,
        account_tier: Optional[str] = None,
        arr: Optional[float] = None,
        activity_data: Optional[str] = None,
        support_data: Optional[str] = None,
        engagement_data: Optional[str] = None,
        step_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """Run the account health crew and return the analysis.

        Returns:
            Dict with parsed result and metadata
        """
        if step_callback:
            step_callback("Creating analysis agents...")

        self._create_agents()
        self._create_tasks(
            account_name, account_tier, arr,
            activity_data, support_data, engagement_data
        )

        if step_callback:
            step_callback("Running account health analysis...")

        crew = Crew(
            name="Account Health Crew",
            agents=[self.analyst],
            tasks=[self.analyze_task],
            process=Process.sequential,
            verbose=False,
        )

        result = crew.kickoff()
        result_text = str(result)

        if step_callback:
            step_callback("Parsing results...")

        # Parse the JSON result
        parsed_result = self._parse_json_result(result_text)

        # Ensure score is valid
        if parsed_result.get("score"):
            try:
                parsed_result["score"] = max(1, min(10, int(parsed_result["score"])))
            except (ValueError, TypeError):
                parsed_result["score"] = 5

        # Get actual model info from LLM
        model_name = getattr(self.llm, 'model', 'unknown')
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
