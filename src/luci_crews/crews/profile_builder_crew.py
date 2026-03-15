"""
Profile Builder Crew

Analyzes historical case data to build performance profiles for support agents.
Identifies top performers and extracts their communication patterns, expertise
areas, and successful resolution approaches into reusable profiles.

Profiles are stored in the support_agent_profiles table and used by the
support-training crew for real-time coaching suggestions.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from crewai import Agent, Task, Crew, Process

from .base_crew import BaseCrew
from ..utils import extract_json_from_llm_response

logger = logging.getLogger(__name__)


class ProfileBuilderCrew(BaseCrew):
    """Crew for building support agent performance profiles."""

    needs_supabase = True

    def _fetch_all_agent_cases(self, days_back: int = 90) -> Dict[str, List[Dict]]:
        """Fetch cases grouped by owner_id for the analysis window."""
        if not self.supabase:
            return {}

        date_threshold = (datetime.now() - timedelta(days=days_back)).isoformat()

        result = self.supabase.from_("cases").select(
            "owner_id, owner_name, case_number, subject, status, priority, type, "
            "created_date, closed_date, account_name, description"
        ).gte("created_date", date_threshold).not_.is_("owner_id", "null").execute()

        cases = result.data or []
        grouped: Dict[str, List[Dict]] = {}
        for case in cases:
            owner_id = case.get("owner_id")
            if owner_id:
                grouped.setdefault(owner_id, []).append(case)

        return grouped

    def _calculate_agent_metrics(self, cases: List[Dict]) -> Dict[str, Any]:
        """Calculate performance metrics for a single agent."""
        total = len(cases)
        closed = [c for c in cases if c.get("closed_date")]
        open_cases = [c for c in cases if not c.get("closed_date")]

        resolution_hours = []
        for case in closed:
            try:
                created = datetime.fromisoformat(case["created_date"].replace("Z", "+00:00"))
                closed_dt = datetime.fromisoformat(case["closed_date"].replace("Z", "+00:00"))
                hours = (closed_dt - created).total_seconds() / 3600
                if hours >= 0:
                    resolution_hours.append(hours)
            except (ValueError, TypeError, KeyError):
                pass

        avg_resolution = sum(resolution_hours) / len(resolution_hours) if resolution_hours else None
        owner_name = cases[0].get("owner_name", "Unknown") if cases else "Unknown"

        # Count by priority
        priority_counts = {}
        for case in cases:
            p = case.get("priority", "Unknown")
            priority_counts[p] = priority_counts.get(p, 0) + 1

        # Count by type
        type_counts = {}
        for case in cases:
            t = case.get("type", "Unknown")
            type_counts[t] = type_counts.get(t, 0) + 1

        return {
            "owner_name": owner_name,
            "total_cases": total,
            "closed_cases": len(closed),
            "open_cases": len(open_cases),
            "close_rate": len(closed) / total if total > 0 else 0,
            "avg_resolution_hours": avg_resolution,
            "priority_distribution": priority_counts,
            "type_distribution": type_counts,
        }

    def _identify_top_performers(
        self,
        agent_metrics: Dict[str, Dict],
        top_percentile: int = 80
    ) -> List[str]:
        """Identify agents in the top percentile by composite score."""
        scores = {}
        for owner_id, metrics in agent_metrics.items():
            # Need minimum 5 cases to be considered
            if metrics["total_cases"] < 5:
                continue

            # Composite: close rate (40%) + inverse resolution time (30%) + volume (30%)
            close_score = metrics["close_rate"]
            # Normalize resolution time (lower is better, cap at 168h / 1 week)
            avg_res = metrics["avg_resolution_hours"]
            time_score = max(0, 1 - (avg_res / 168)) if avg_res is not None else 0.5
            # Normalize volume (more is better, cap contribution)
            vol_score = min(1.0, metrics["total_cases"] / 50)

            scores[owner_id] = (close_score * 0.4) + (time_score * 0.3) + (vol_score * 0.3)

        if not scores:
            return []

        threshold = sorted(scores.values())[int(len(scores) * (top_percentile / 100))] if len(scores) > 1 else 0
        return [oid for oid, score in scores.items() if score >= threshold]

    def _format_agent_summary(self, owner_id: str, metrics: Dict, cases: List[Dict]) -> str:
        """Format a single agent's data for the AI prompt."""
        # Include up to 15 most recent closed cases with descriptions
        closed_cases = sorted(
            [c for c in cases if c.get("closed_date")],
            key=lambda c: c.get("closed_date", ""),
            reverse=True
        )[:15]

        case_summaries = []
        for c in closed_cases:
            desc = (c.get("description") or "")[:300]
            case_summaries.append(
                f"  - #{c.get('case_number','?')} [{c.get('type','?')}/{c.get('priority','?')}] "
                f"{c.get('subject','No subject')} → {c.get('status','?')} "
                f"(Created: {c.get('created_date','?')}, Closed: {c.get('closed_date','?')})\n"
                f"    Description: {desc}"
            )

        return f"""
Agent: {metrics['owner_name']} (ID: {owner_id})
Total Cases: {metrics['total_cases']} | Closed: {metrics['closed_cases']} | Close Rate: {metrics['close_rate']:.0%}
Avg Resolution: {metrics['avg_resolution_hours']:.1f} hours
Types: {metrics['type_distribution']}
Priorities: {metrics['priority_distribution']}

Recent Closed Cases:
{chr(10).join(case_summaries) if case_summaries else '  (none)'}
"""

    def run(
        self,
        days_back: int = 90,
        top_percentile: int = 80,
        step_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        Build performance profiles for top support agents.

        Args:
            days_back: Number of days of case history to analyze
            top_percentile: Percentile threshold for "top performer" (e.g. 80 = top 20%)
            step_callback: Optional callback for progress updates

        Returns:
            Dict with profiles_built count and profile data
        """
        if step_callback:
            step_callback("Fetching case data...")

        # 1. Fetch and group cases by agent
        agent_cases = self._fetch_all_agent_cases(days_back)
        if not agent_cases:
            return {"success": True, "profiles_built": 0, "reason": "no_cases_found"}

        # 2. Calculate metrics per agent
        agent_metrics = {
            owner_id: self._calculate_agent_metrics(cases)
            for owner_id, cases in agent_cases.items()
        }

        logger.info(f"Calculated metrics for {len(agent_metrics)} agents")

        # 3. Identify top performers
        top_ids = self._identify_top_performers(agent_metrics, top_percentile)
        if not top_ids:
            return {"success": True, "profiles_built": 0, "reason": "no_qualifying_agents"}

        logger.info(f"Identified {len(top_ids)} top performers (>= {top_percentile}th percentile)")

        if step_callback:
            step_callback(f"Analyzing {len(top_ids)} top performers...")

        # 4. Build combined prompt with all top performers
        agent_summaries = "\n---\n".join(
            self._format_agent_summary(oid, agent_metrics[oid], agent_cases[oid])
            for oid in top_ids
        )

        # Team-wide stats
        all_totals = [m["total_cases"] for m in agent_metrics.values()]
        all_res = [m["avg_resolution_hours"] for m in agent_metrics.values() if m["avg_resolution_hours"] is not None]
        team_avg_cases = sum(all_totals) / len(all_totals) if all_totals else 0
        team_avg_res = sum(all_res) / len(all_res) if all_res else 0

        # 5. Run AI analysis
        profile_analyst = Agent(
            role="Support Team Profile Analyst",
            goal="Analyze top-performing support agents and extract reusable patterns",
            backstory=(
                "You are a support operations expert who studies high-performing agents "
                "to extract repeatable patterns. You analyze case handling data to identify "
                "communication styles, expertise areas, diagnostic approaches, and resolution "
                "strategies that make agents successful. Your profiles are used to train and "
                "coach other agents."
            ),
            verbose=False,
            allow_delegation=False,
            llm=self.llm,
        )

        analysis_task = Task(
            description=f"""Analyze the following top-performing support agents (top {100 - top_percentile}% by composite score)
from the last {days_back} days of case data.

Team averages: {team_avg_cases:.0f} cases/agent, {team_avg_res:.1f} hours avg resolution.

TOP PERFORMER DATA:
{agent_summaries}

For EACH agent listed above, produce a profile with:
1. communication_patterns: tone, technical_depth, empathy_markers
2. expertise_areas: list of categories with confidence scores (0-1) based on case volume and resolution speed
3. successful_patterns: common approaches, diagnostic questions, resolution strategies observed
4. performance_summary: what makes this agent stand out

Also produce ONE team_best_practices profile that synthesizes the common patterns across ALL top performers.

Return valid JSON with this structure:
{{
  "team_best_practices": {{
    "communication_patterns": {{"tone": "...", "technical_depth": "...", "empathy_markers": [...]}},
    "expertise_areas": [{{"category": "...", "confidence": 0.9}}],
    "successful_patterns": {{"opening_approaches": [...], "diagnostic_questions": [...], "resolution_strategies": [...]}},
    "key_insights": "..."
  }},
  "individual_profiles": [
    {{
      "owner_id": "...",
      "owner_name": "...",
      "communication_patterns": {{...}},
      "expertise_areas": [{{...}}],
      "successful_patterns": {{...}},
      "performance_summary": "..."
    }}
  ]
}}""",
            expected_output="Valid JSON with team_best_practices and individual_profiles array",
            agent=profile_analyst,
        )

        crew = Crew(
            agents=[profile_analyst],
            tasks=[analysis_task],
            process=Process.sequential,
            verbose=False,
        )

        result = crew.kickoff()
        parsed = extract_json_from_llm_response(str(result))

        if step_callback:
            step_callback("Saving profiles...")

        # 6. Save profiles to Supabase
        profiles_saved = 0

        if self.supabase and isinstance(parsed, dict):
            # Save team best practices
            team_profile = parsed.get("team_best_practices")
            if team_profile:
                try:
                    self.supabase.from_("support_agent_profiles").upsert({
                        "profile_type": "team_best_practices",
                        "user_id": None,
                        "salesforce_user_id": None,
                        "total_cases_analyzed": sum(
                            agent_metrics[oid]["total_cases"] for oid in top_ids
                        ),
                        "avg_resolution_hours": team_avg_res,
                        "performance_percentile": top_percentile,
                        "profile_data": team_profile,
                        "analyzed_at": datetime.now().isoformat(),
                    }, on_conflict="profile_type").execute()
                    profiles_saved += 1
                except Exception as e:
                    logger.error(f"Error saving team profile: {e}")

            # Save individual profiles
            for profile in parsed.get("individual_profiles", []):
                owner_id = profile.get("owner_id")
                if not owner_id or owner_id not in agent_metrics:
                    continue

                metrics = agent_metrics[owner_id]
                try:
                    self.supabase.from_("support_agent_profiles").upsert({
                        "profile_type": "individual",
                        "salesforce_user_id": owner_id,
                        "total_cases_analyzed": metrics["total_cases"],
                        "avg_resolution_hours": metrics["avg_resolution_hours"],
                        "performance_percentile": top_percentile,
                        "profile_data": profile,
                        "analyzed_at": datetime.now().isoformat(),
                    }, on_conflict="salesforce_user_id").execute()
                    profiles_saved += 1
                except Exception as e:
                    logger.error(f"Error saving profile for {owner_id}: {e}")

        logger.info(f"Profile build complete: {profiles_saved} profiles saved")

        return {
            "success": True,
            "profiles_built": profiles_saved,
            "agents_analyzed": len(top_ids),
            "total_agents": len(agent_metrics),
            "days_back": days_back,
            "top_percentile": top_percentile,
        }
