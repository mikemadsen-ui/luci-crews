"""
Support Agent Coaching Crew

Analyzes a support agent's case history to provide personalized coaching
recommendations, identify strengths and improvement areas, and compare
performance against team benchmarks.
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from crewai import Agent, Task, Crew, Process
from supabase import create_client, Client

from ..config_loader import load_agents_config, load_tasks_config


class SupportCoachingCrew:
    """Crew for analyzing support agent performance and providing coaching."""

    def __init__(self):
        self.agents_config = load_agents_config()
        self.tasks_config = load_tasks_config()
        self.supabase = self._get_supabase_client()

    def _get_supabase_client(self) -> Optional[Client]:
        """Get Supabase client for database access."""
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if url and key:
            return create_client(url, key)
        return None

    def _format_cases_data(self, cases: List[Dict[str, Any]]) -> str:
        """Format cases data for the prompt."""
        if not cases:
            return "No cases found for this agent."

        formatted = []
        for case in cases:
            case_info = f"""
Case #{case.get('case_number', 'N/A')}
- Subject: {case.get('subject', 'N/A')}
- Status: {case.get('status', 'N/A')}
- Priority: {case.get('priority', 'N/A')}
- Type: {case.get('type', 'N/A')}
- Account: {case.get('account_name', 'N/A')}
- Created: {case.get('created_date', 'N/A')}
- Closed: {case.get('closed_date', 'N/A') or 'Still Open'}
- Description: {(case.get('description') or 'No description')[:500]}
"""
            formatted.append(case_info)

        return "\n---\n".join(formatted)

    def _calculate_team_benchmarks(self, agent_owner_id: str) -> Dict[str, Any]:
        """Calculate team benchmarks from all cases."""
        if not self.supabase:
            return {
                "team_avg_cases": "N/A",
                "team_avg_resolution_time": "N/A",
                "team_avg_csat": "N/A"
            }

        try:
            # Get date threshold (90 days)
            date_threshold = (datetime.now() - timedelta(days=90)).isoformat()

            # Get all cases from last 90 days
            result = self.supabase.from_("cases").select(
                "owner_id, owner_name, created_date, closed_date, status"
            ).gte("created_date", date_threshold).execute()

            cases = result.data or []
            if not cases:
                return {
                    "team_avg_cases": "N/A",
                    "team_avg_resolution_time": "N/A",
                    "team_avg_csat": "N/A"
                }

            # Count cases per agent
            agent_cases = {}
            resolution_times = []

            for case in cases:
                owner_id = case.get("owner_id")
                if owner_id:
                    agent_cases[owner_id] = agent_cases.get(owner_id, 0) + 1

                # Calculate resolution time for closed cases
                if case.get("closed_date") and case.get("created_date"):
                    try:
                        created = datetime.fromisoformat(case["created_date"].replace("Z", "+00:00"))
                        closed = datetime.fromisoformat(case["closed_date"].replace("Z", "+00:00"))
                        resolution_days = (closed - created).days
                        if resolution_days >= 0:
                            resolution_times.append(resolution_days)
                    except:
                        pass

            # Calculate averages
            num_agents = len(agent_cases)
            avg_cases = sum(agent_cases.values()) / num_agents if num_agents > 0 else 0
            avg_resolution = sum(resolution_times) / len(resolution_times) if resolution_times else None

            return {
                "team_avg_cases": f"{avg_cases:.1f} cases per agent",
                "team_avg_resolution_time": f"{avg_resolution:.1f} days" if avg_resolution else "N/A",
                "team_avg_csat": "N/A"  # Would need CSAT data
            }

        except Exception as e:
            print(f"Error calculating team benchmarks: {e}")
            return {
                "team_avg_cases": "N/A",
                "team_avg_resolution_time": "N/A",
                "team_avg_csat": "N/A"
            }

    def _fetch_agent_cases(self, owner_id: str, days_back: int = 90) -> List[Dict[str, Any]]:
        """Fetch cases for a specific agent from Supabase."""
        if not self.supabase:
            return []

        try:
            date_threshold = (datetime.now() - timedelta(days=days_back)).isoformat()

            result = self.supabase.from_("cases").select("*").eq(
                "owner_id", owner_id
            ).gte("created_date", date_threshold).order(
                "created_date", desc=True
            ).limit(100).execute()

            return result.data or []

        except Exception as e:
            print(f"Error fetching agent cases: {e}")
            return []

    def run(
        self,
        agent_name: str,
        agent_email: str,
        owner_id: str,
        cases_data: Optional[List[Dict[str, Any]]] = None,
        days_back: int = 90,
        step_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Run the support coaching crew analysis.

        Args:
            agent_name: Name of the support agent
            agent_email: Email of the support agent
            owner_id: Salesforce Owner ID for the agent
            cases_data: Optional pre-fetched cases data
            days_back: Number of days to analyze
            step_callback: Optional callback for progress updates

        Returns:
            Coaching analysis results
        """
        # Fetch cases if not provided
        if cases_data is None:
            cases_data = self._fetch_agent_cases(owner_id, days_back)

        # Format cases for the prompt
        formatted_cases = self._format_cases_data(cases_data)

        # Get team benchmarks
        benchmarks = self._calculate_team_benchmarks(owner_id)

        # Send progress update if callback provided
        if step_callback:
            step_callback("Analyzing case history...")

        # Create the support coach agent
        coach_config = self.agents_config.get("support_coach", {})
        support_coach = Agent(
            role=coach_config.get("role", "Support Agent Coach"),
            goal=coach_config.get("goal", "Provide coaching recommendations"),
            backstory=coach_config.get("backstory", "You are an experienced support coach."),
            verbose=coach_config.get("verbose", True),
            allow_delegation=coach_config.get("allow_delegation", False),
        )

        # Create the analysis task
        task_config = self.tasks_config.get("analyze_support_agent_performance", {})
        task_description = task_config.get("description", "").format(
            agent_name=agent_name,
            agent_email=agent_email,
            days_back=days_back,
            cases_data=formatted_cases,
            team_avg_cases=benchmarks["team_avg_cases"],
            team_avg_resolution_time=benchmarks["team_avg_resolution_time"],
            team_avg_csat=benchmarks["team_avg_csat"]
        )

        analysis_task = Task(
            description=task_description,
            expected_output=task_config.get("expected_output", "JSON coaching analysis"),
            agent=support_coach
        )

        # Create and run the crew
        crew = Crew(
            agents=[support_coach],
            tasks=[analysis_task],
            process=Process.sequential,
            verbose=True
        )

        result = crew.kickoff()

        # Parse the result
        result_text = str(result)

        # Try to extract JSON from the result
        try:
            # Look for JSON in the response
            import re
            json_match = re.search(r'\{[\s\S]*\}', result_text)
            if json_match:
                parsed_result = json.loads(json_match.group())
                return {
                    "success": True,
                    "analysis": parsed_result,
                    "agent_name": agent_name,
                    "agent_email": agent_email,
                    "cases_analyzed": len(cases_data),
                    "days_back": days_back
                }
        except json.JSONDecodeError:
            pass

        # Return raw result if JSON parsing fails
        return {
            "success": True,
            "analysis": result_text,
            "agent_name": agent_name,
            "agent_email": agent_email,
            "cases_analyzed": len(cases_data),
            "days_back": days_back,
            "raw_response": True
        }
