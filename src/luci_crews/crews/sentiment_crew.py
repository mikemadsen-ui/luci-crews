"""
Sentiment Analysis Crew

Analyzes customer sentiment from communications and interactions.
"""

import logging
from typing import Optional, Dict, Any
from crewai import Agent, Task, Crew, Process, LLM

from .base_crew import BaseCrew

logger = logging.getLogger(__name__)


class SentimentCrew(BaseCrew):
    """Crew for analyzing customer sentiment."""

    def _create_agents(self):
        """Create agents from configuration."""
        analyst_config = self._get_agent_config("sentiment_analyst")

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
        task_config = self._get_task_config("analyze_sentiment")

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

    def _parse_json_result(self, result_text: str) -> Dict[str, Any]:
        """Parse JSON from the crew result, handling various formats."""
        return super()._parse_json_result(
            result_text,
            default={
                "score": None,
                "summary": None,
                "comprehensiveAnalysis": result_text,
            },
        )

    def run(
        self,
        account_name: str,
        communications_data: Optional[str] = None,
        support_data: Optional[str] = None,
        meeting_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run the sentiment crew and return the analysis."""
        self._create_agents()
        self._create_tasks(
            account_name, communications_data,
            support_data, meeting_notes
        )

        crew = Crew(
            name="Sentiment Analysis Crew",
            agents=[self.analyst],
            tasks=[self.analyze_task],
            process=Process.sequential,
            verbose=False,
        )

        result = crew.kickoff()
        result_text = str(result)

        # Parse the JSON result
        parsed_result = self._parse_json_result(result_text)

        # Map to frontend expected format
        return {
            "score": parsed_result.get("score"),
            "confidence": parsed_result.get("confidence"),
            "trend": parsed_result.get("trend"),
            "summary": parsed_result.get("summary"),
            "positive_signals": parsed_result.get("positive_signals", []),
            "warning_signs": parsed_result.get("warning_signs", []),
            "key_themes": parsed_result.get("key_themes", []),
            "key_quotes": parsed_result.get("key_quotes", []),
            "actions": parsed_result.get("actions", []),
            "talking_points": parsed_result.get("talking_points", []),
            "comprehensiveAnalysis": parsed_result.get("comprehensiveAnalysis"),
        }
