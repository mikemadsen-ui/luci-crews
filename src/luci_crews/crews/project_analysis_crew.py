"""
Project Analysis Crew - Unified analysis combining strategic health and customer sentiment.

This crew consolidates implementation analysis and project sentiment into a single
comprehensive project assessment. It provides:
- Strategic health analysis (tasks, timeline, resources)
- Customer sentiment analysis (from transcripts, with task context)
- Coaching recommendations for the project owner (PM or IC)

Key improvement: Sentiment analyst receives Mavenlink task data, preventing false
"missing task assignments" risks.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

from crewai import Agent, Crew, Task
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)


class ProjectAnalysisCrew:
    """Unified project analysis crew combining strategic health and sentiment."""

    def __init__(self):
        """Initialize the project analysis crew."""
        self.llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini"),
            temperature=0.7,
            openai_api_key=os.getenv("OPENAI_API_KEY"),
        )

    def _create_strategic_analyst(self) -> Agent:
        """Create the strategic health analyst agent."""
        return Agent(
            role="Strategic Project Health Analyst",
            goal="Analyze project health from strategic perspective: tasks, timeline, resources, and risks",
            backstory="""You are an expert project health analyst with deep experience in
            Professional Services implementations. You excel at identifying project risks,
            timeline issues, resource allocation problems, and task completion patterns.
            You analyze Mavenlink task data, time entries, and project metrics to provide
            actionable insights.""",
            llm=self.llm,
            verbose=True,
            allow_delegation=False,
        )

    def _create_sentiment_analyst(self) -> Agent:
        """Create the customer sentiment analyst agent."""
        return Agent(
            role="Customer Sentiment Analyst",
            goal="Analyze customer sentiment and engagement from conversation transcripts",
            backstory="""You are an expert at understanding customer sentiment from
            conversations. You identify tone, engagement levels, concerns, and satisfaction
            indicators. IMPORTANT: You now have access to Mavenlink task data, so you can
            accurately assess whether tasks are assigned and avoid false positives about
            'missing assignments'. Consider the task context when analyzing discussions
            about project progress and deliverables.""",
            llm=self.llm,
            verbose=True,
            allow_delegation=False,
        )

    def _create_project_coach(self) -> Agent:
        """Create the project coach agent that synthesizes and provides recommendations."""
        return Agent(
            role="Project Coach",
            goal="Synthesize all analysis into actionable coaching for the project owner",
            backstory="""You are a senior Professional Services coach with expertise in
            implementation success. You synthesize strategic health and sentiment analysis
            to provide targeted coaching recommendations. You tailor your advice to whether
            the project owner is a Project Manager (PM) or Implementation Consultant (IC).
            When PM exists, they own the project and need leadership-focused coaching.
            When only IC exists, they need execution-focused coaching.""",
            llm=self.llm,
            verbose=True,
            allow_delegation=False,
        )

    def _format_project_context(self, project: Dict[str, Any], project_owner: Dict[str, Any]) -> str:
        """Format project data for task context."""
        owner_type = project_owner.get("type", "unknown")
        owner_name = project_owner.get("name", "Unknown")

        pm_name = project.get("accountProjectManagerName") or project.get("account_project_manager_name")
        ic_name = project.get("implementationConsultantName") or project.get("implementation_consultant_name")

        return f"""
PROJECT DETAILS:
- Name: {project.get('project_name', 'Unknown')}
- Status: {project.get('project_status', 'Unknown')}
- Start Date: {project.get('start_date', 'N/A')}
- Target Go-Live: {project.get('target_go_live_date') or project.get('ps_forecasted_live_date', 'N/A')}
- Completion: {project.get('completion_percentage', 'N/A')}%
- Hours Used: {project.get('billable_hours', 'N/A')} / {project.get('service_hours_in_contract', 'N/A')} contracted
- Budget Used: ${project.get('budget_used', 'N/A')} / ${project.get('budget', 'N/A')}

TEAM ROLES:
- Project Manager (PM): {pm_name or 'Not assigned'}
- Implementation Consultant (IC): {ic_name or 'Not assigned'}
- Project Owner: {owner_type.upper()} - {owner_name}
  {"(PM owns this project)" if owner_type == "pm" else "(IC owns this project - no PM assigned)"}
"""

    def _format_tasks_context(self, tasks: List[Dict[str, Any]]) -> str:
        """Format Mavenlink tasks for analysis context."""
        if not tasks:
            return "NO MAVENLINK TASKS AVAILABLE"

        assigned_count = sum(1 for t in tasks if t.get("has_assignee"))
        unassigned_count = len(tasks) - assigned_count

        task_summary = f"""
MAVENLINK TASKS SUMMARY:
- Total Tasks: {len(tasks)}
- Assigned: {assigned_count}
- Unassigned: {unassigned_count}

TASK DETAILS:
"""
        for task in tasks[:20]:  # Limit to first 20 for context
            assignees = ", ".join(task.get("assignee_names", [])) or "Unassigned"
            task_summary += f"- [{task.get('story_type', 'task').upper()}] {task.get('title', 'Untitled')}\n"
            task_summary += f"  Status: {task.get('status', 'unknown')} | Assignee: {assignees}\n"
            if task.get("due_date"):
                task_summary += f"  Due: {task.get('due_date')}\n"

        return task_summary

    def _format_transcripts_context(self, transcripts: List[Dict[str, Any]]) -> str:
        """Format transcripts for sentiment analysis."""
        if not transcripts:
            return "NO TRANSCRIPTS AVAILABLE"

        context = "RECENT CONVERSATION TRANSCRIPTS:\n\n"
        for t in transcripts:
            subject = t.get("meeting_subject", "Untitled Meeting")
            date = t.get("meeting_date", "Unknown date")
            text = t.get("transcription_text", "")

            # Truncate very long transcripts
            if len(text) > 5000:
                text = text[:5000] + "\n... [truncated]"

            context += f"--- {subject} ({date}) ---\n{text}\n\n"

        return context

    def run(
        self,
        project: Dict[str, Any],
        project_owner: Dict[str, Any],
        transcripts: List[Dict[str, Any]],
        mavenlink_tasks: List[Dict[str, Any]],
        mavenlink_time_entries: List[Dict[str, Any]],
        call_activity: Optional[Dict[str, Any]] = None,
        stream_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        Run the project analysis.

        Args:
            project: Project data from implementation_projects
            project_owner: Dict with type ('pm' or 'ic'), id, and name
            transcripts: List of transcript data
            mavenlink_tasks: List of Mavenlink task data with assignees
            mavenlink_time_entries: List of time entry data
            call_activity: Optional call activity metrics
            stream_callback: Optional callback for streaming progress

        Returns:
            Dict with scores, summaries, and coaching recommendations
        """
        logger.info(f"Running project analysis for: {project.get('project_name')}")
        logger.info(f"Project owner: {project_owner.get('type', 'unknown').upper()} - {project_owner.get('name', 'Unknown')}")
        logger.info(f"Data: {len(transcripts)} transcripts, {len(mavenlink_tasks)} tasks")

        def send_progress(step: str, message: str):
            if stream_callback:
                stream_callback({"type": "progress", "step": step, "message": message})
            logger.info(f"[{step}] {message}")

        # Format context for tasks
        project_context = self._format_project_context(project, project_owner)
        tasks_context = self._format_tasks_context(mavenlink_tasks)
        transcripts_context = self._format_transcripts_context(transcripts)

        # Create agents
        strategic_analyst = self._create_strategic_analyst()
        sentiment_analyst = self._create_sentiment_analyst()
        project_coach = self._create_project_coach()

        # Task 1: Strategic Health Analysis
        send_progress("Step 1", "Analyzing strategic project health...")
        strategic_task = Task(
            description=f"""Analyze the strategic health of this implementation project.

{project_context}

{tasks_context}

TIME ENTRIES:
- Total entries: {len(mavenlink_time_entries)}
- Total hours logged: {sum(e.get('hours', 0) or 0 for e in mavenlink_time_entries):.1f}

Evaluate:
1. Task completion and assignment status
2. Timeline health (on track, at risk, delayed)
3. Resource utilization (hours vs budget)
4. Identified risks and blockers

Provide a structured assessment with specific observations.""",
            expected_output="""Strategic health assessment including:
- Overall health status (Healthy/At Risk/Critical)
- Task completion analysis
- Timeline assessment
- Resource utilization analysis
- Key risks identified
- Specific recommendations""",
            agent=strategic_analyst,
        )

        # Task 2: Customer Sentiment Analysis
        send_progress("Step 2", "Analyzing customer sentiment...")
        sentiment_task = Task(
            description=f"""Analyze customer sentiment from recent conversations.

{project_context}

IMPORTANT CONTEXT - You have access to Mavenlink task data:
{tasks_context}

Use this task data to:
- Validate concerns about task assignments (don't flag "missing assignments" if tasks ARE assigned)
- Understand context when customers discuss project progress
- Identify if discussion topics align with actual task status

{transcripts_context}

CALL ACTIVITY:
{json.dumps(call_activity.get('metrics', {}) if call_activity else {}, indent=2)}

Analyze:
1. Overall customer sentiment (positive/neutral/negative)
2. Key themes and concerns raised
3. Engagement level and communication quality
4. Specific quotes that indicate sentiment
5. Participant-level sentiment if identifiable""",
            expected_output="""Sentiment analysis including:
- Sentiment score (1-10, where 10 is very positive)
- Overall sentiment assessment
- Key themes identified
- Important quotes
- Customer concerns (validated against task data)
- Engagement assessment""",
            agent=sentiment_analyst,
        )

        # Task 3: Synthesis and Coaching
        owner_type = project_owner.get("type", "unknown")
        owner_context = "Project Manager (PM)" if owner_type == "pm" else "Implementation Consultant (IC)"

        send_progress("Step 3", "Synthesizing analysis and generating coaching...")
        coaching_task = Task(
            description=f"""Synthesize all analysis into actionable coaching for the project owner.

The project owner is: {owner_context} - {project_owner.get('name', 'Unknown')}

{"As the PM, they are ultimately responsible for project success and need leadership-focused guidance." if owner_type == "pm" else "As the IC (with no PM assigned), they own this project and need execution-focused guidance."}

Based on the strategic health and sentiment analyses, provide:
1. Overall health score (1-10)
2. Executive summary (2-3 sentences)
3. Coaching recommendations tailored to {owner_context}
4. Immediate priorities (top 3)
5. Risk mitigation actions

Be specific and actionable. Reference specific tasks, quotes, or data points.""",
            expected_output="""JSON object with:
{{
  "overall_health_score": <1-10>,
  "sentiment_score": <1-10>,
  "owner_effectiveness_score": <1-10>,
  "executive_summary": "<2-3 sentence summary>",
  "strategic_analysis": "<strategic findings>",
  "customer_sentiment_summary": "<sentiment findings>",
  "owner_coaching_summary": "<coaching specific to PM or IC>",
  "timeline_deliverables_summary": "<timeline assessment>",
  "risks_summary": "<risk summary>",
  "identified_risks": [<list of specific risks>],
  "coaching_recommendations": [<list of actionable recommendations>],
  "key_quotes": [<important customer quotes>],
  "participants_sentiment": {{}},
  "project_owner_type": "<pm or ic>"
}}""",
            agent=project_coach,
            context=[strategic_task, sentiment_task],
        )

        # Create and run crew
        crew = Crew(
            agents=[strategic_analyst, sentiment_analyst, project_coach],
            tasks=[strategic_task, sentiment_task, coaching_task],
            verbose=True,
        )

        send_progress("Step 4", "Running analysis...")
        result = crew.kickoff()

        send_progress("Complete", "Analysis complete!")

        # Parse result
        try:
            # Try to extract JSON from the result
            result_str = str(result)

            # Find JSON in the response
            json_start = result_str.find("{")
            json_end = result_str.rfind("}") + 1

            if json_start >= 0 and json_end > json_start:
                json_str = result_str[json_start:json_end]
                parsed_result = json.loads(json_str)
                parsed_result["provider"] = "openai"
                parsed_result["model"] = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
                return parsed_result
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON from result: {e}")

        # Fallback: return raw result with default structure
        return {
            "overall_health_score": None,
            "sentiment_score": None,
            "owner_effectiveness_score": None,
            "executive_summary": str(result),
            "strategic_analysis": "",
            "customer_sentiment_summary": "",
            "owner_coaching_summary": "",
            "timeline_deliverables_summary": "",
            "risks_summary": "",
            "identified_risks": [],
            "coaching_recommendations": [],
            "key_quotes": [],
            "participants_sentiment": {},
            "project_owner_type": project_owner.get("type", "unknown"),
            "raw_result": str(result),
            "provider": "openai",
            "model": os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini"),
        }
