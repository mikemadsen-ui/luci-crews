"""
Competitive Intelligence Analysis Crew

Analyzes competitor companies and provides battle cards, positioning strategies,
and actionable competitive intelligence.
"""

import os
import json
import yaml
from typing import Optional, List, Dict, Any
from crewai import Agent, Task, Crew, Process
from crewai import LLM

from ..ai_settings_helper import create_llm_for_user, DEFAULT_AI_SETTINGS


class CompetitiveCrew:
    """Crew for analyzing competitors and generating competitive intelligence."""

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
        analyst_config = self.agents_config.get("competitive_analyst", {})

        self.analyst = Agent(
            role=analyst_config.get("role", "Competitive Intelligence Analyst"),
            goal=analyst_config.get("goal", "Analyze competitive positioning"),
            backstory=analyst_config.get("backstory", "Expert competitive analyst"),
            verbose=analyst_config.get("verbose", True),
            allow_delegation=analyst_config.get("allow_delegation", False),
            llm=self.llm,
        )

    def _format_companies(self, companies: List[Dict[str, Any]]) -> str:
        """Format company data for the prompt."""
        formatted = []
        for i, company in enumerate(companies, 1):
            # Handle both nested properties and flat structure
            props = company.get('properties') or {}
            name = props.get('name') or company.get('name') or 'Unknown'
            domain = props.get('domain') or company.get('domain') or 'N/A'
            industry = props.get('industry') or company.get('industry') or 'N/A'
            description = props.get('description') or company.get('description') or ''

            company_info = f"""
Company {i}: {name}
  - Domain: {domain}
  - Industry: {industry}
  - Description: {description[:500] if description else 'No description available'}
"""
            formatted.append(company_info)

        return "\n".join(formatted)

    def _create_tasks(
        self,
        companies: List[Dict[str, Any]],
        analysis_type: str,
    ):
        """Create tasks from configuration with data interpolation."""
        task_config = self.tasks_config.get("analyze_companies_competitive", {})

        companies_text = self._format_companies(companies)
        company_names = [(c.get('properties') or {}).get('name') or c.get('name') or 'Unknown' for c in companies]

        description = task_config.get("description", "").format(
            companies_text=companies_text,
            company_names=", ".join(company_names),
            analysis_type=analysis_type,
            num_companies=len(companies),
        )

        self.analyze_task = Task(
            description=description,
            expected_output=task_config.get("expected_output", "Competitive analysis report"),
            agent=self.analyst,
        )

    def _parse_json_result(self, result: str) -> Dict[str, Any]:
        """Extract JSON from the crew result."""
        result_str = str(result)

        # Try to find JSON in the response
        try:
            # First try direct parse
            return json.loads(result_str)
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from markdown code blocks
        import re
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', result_str)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find JSON object in the text
        json_match = re.search(r'\{[\s\S]*\}', result_str)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        # Return as text if no JSON found
        return {"analysis_text": result_str}

    def run(
        self,
        companies: List[Dict[str, Any]],
        analysis_type: str = "comparative",
    ) -> Dict[str, Any]:
        """Run the competitive analysis crew and return the analysis.

        Args:
            companies: List of company objects to analyze
            analysis_type: 'single' for one company, 'comparative' for multiple

        Returns:
            Dict containing structured analysis results
        """
        self._create_agents()
        self._create_tasks(companies, analysis_type)

        crew = Crew(
            agents=[self.analyst],
            tasks=[self.analyze_task],
            process=Process.sequential,
            verbose=True,
        )

        result = crew.kickoff()
        parsed_result = self._parse_json_result(str(result))

        return {
            "result": parsed_result,
            "analysis": parsed_result,
            "analysisType": analysis_type,
            "provider": "openai",
            "model": self.llm.model if hasattr(self.llm, 'model') else None,
        }
