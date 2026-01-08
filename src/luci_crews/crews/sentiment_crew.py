"""
Sentiment Analysis Crew

Analyzes customer sentiment from communications and interactions.
"""

import os
import json
import re
import yaml
import logging
from typing import Optional, Dict, Any
from crewai import Agent, Task, Crew, Process
from crewai import LLM

from ..ai_settings_helper import create_llm_for_user, DEFAULT_AI_SETTINGS

logger = logging.getLogger(__name__)


class SentimentCrew:
    """Crew for analyzing customer sentiment."""

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

    def _parse_json_result(self, result_text: str) -> Dict[str, Any]:
        """Parse JSON from the crew result, handling various formats."""
        # Try to find JSON in the result
        json_match = re.search(r'\{[\s\S]*\}', result_text)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                return parsed
            except json.JSONDecodeError:
                logger.warning("Found JSON-like content but failed to parse")

        # If no JSON found, return raw text in a structured format
        return {
            "score": None,
            "summary": None,
            "comprehensiveAnalysis": result_text,
        }

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
            agents=[self.analyst],
            tasks=[self.analyze_task],
            process=Process.sequential,
            verbose=True,
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
            "recommended_actions": parsed_result.get("recommended_actions", []),
            "talking_points": parsed_result.get("talking_points", []),
            "comprehensiveAnalysis": parsed_result.get("comprehensiveAnalysis"),
        }
