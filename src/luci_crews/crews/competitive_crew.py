"""
Competitive Intelligence Analysis Crew

Analyzes competitor companies and provides battle cards, positioning strategies,
and actionable competitive intelligence.
"""

from typing import Optional, List, Dict, Any
from crewai import Agent, Task, Crew, Process

from .base_crew import BaseCrew
from ..utils import extract_json_from_llm_response


class CompetitiveCrew(BaseCrew):
    """Crew for analyzing competitors and generating competitive intelligence."""

    def _create_agents(self):
        """Create agents from configuration."""
        analyst_config = self._get_agent_config("competitive_analyst")

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
        task_config = self._get_task_config("analyze_companies_competitive")

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
        return extract_json_from_llm_response(
            str(result),
            default={"analysis_text": str(result)},
        )

    def run(
        self,
        companies: List[Dict[str, Any]],
        analysis_type: str = "comparative",
        step_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """Run the competitive analysis crew and return the analysis.

        Args:
            companies: List of company objects to analyze
            analysis_type: 'single' for one company, 'comparative' for multiple
            step_callback: Optional callback for progress updates

        Returns:
            Dict containing structured analysis results
        """
        if step_callback:
            step_callback("Creating analysis agents...")

        self._create_agents()
        self._create_tasks(companies, analysis_type)

        if step_callback:
            step_callback("Running competitive analysis...")

        crew = Crew(
            agents=[self.analyst],
            tasks=[self.analyze_task],
            process=Process.sequential,
            verbose=False,
        )

        result = crew.kickoff()

        if step_callback:
            step_callback("Parsing results...")

        parsed_result = self._parse_json_result(str(result))

        return {
            "result": parsed_result,
            "analysis": parsed_result,
            "analysisType": analysis_type,
            "provider": "openai",
            "model": self.llm.model if hasattr(self.llm, 'model') else None,
        }
