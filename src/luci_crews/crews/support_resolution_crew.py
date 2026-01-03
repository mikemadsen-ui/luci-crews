"""
Support Resolution Crew

Analyzes a support case and provides actionable suggestions for resolution,
including a suggested response, diagnostic questions, and resolution steps.
"""

import os
import json
from typing import Dict, Any, Optional
from crewai import Agent, Task, Crew, Process

from ..config_loader import load_agents_config, load_tasks_config


class SupportResolutionCrew:
    """Crew for analyzing support cases and providing resolution suggestions."""

    def __init__(self):
        self.agents_config = load_agents_config()
        self.tasks_config = load_tasks_config()

    def run(
        self,
        case_subject: str,
        case_description: str,
        case_type: Optional[str] = None,
        case_priority: Optional[str] = None,
        account_name: Optional[str] = None,
        contact_name: Optional[str] = None,
        step_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Run the support resolution crew analysis.

        Args:
            case_subject: Subject/title of the case
            case_description: Full description of the case
            case_type: Type of case (e.g., Technical, Billing)
            case_priority: Priority level (High, Medium, Low)
            account_name: Customer account name
            contact_name: Contact person name
            step_callback: Optional callback for progress updates

        Returns:
            Structured resolution suggestions
        """
        # Create the support analyst agent
        analyst_config = self.agents_config.get("support_coach", {})
        support_analyst = Agent(
            role="Support Resolution Specialist",
            goal="Analyze support cases and provide clear, actionable resolution guidance",
            backstory="""You are an expert support analyst who helps support agents resolve
            customer issues efficiently. You excel at understanding customer problems,
            suggesting appropriate responses, identifying the right questions to ask,
            and providing step-by-step resolution guidance. You focus on being helpful,
            empathetic, and thorough.""",
            verbose=True,
            allow_delegation=False,
        )

        # Send progress update if callback provided
        if step_callback:
            step_callback("Analyzing case details...")

        # Build the task description
        task_description = f"""
Analyze this support case and provide actionable guidance for resolution.

CASE DETAILS:
- Subject: {case_subject}
- Type: {case_type or 'Not specified'}
- Priority: {case_priority or 'Not specified'}
- Account: {account_name or 'Not specified'}
- Contact: {contact_name or 'Not specified'}

CASE DESCRIPTION:
{case_description or 'No description provided'}

Provide your analysis as a JSON object with this structure:
{{
    "suggestedOpening": "A warm, professional opening response to send to the customer (2-3 sentences acknowledging their issue)",
    "recommendedApproach": {{
        "summary": "Brief summary of the recommended approach (1-2 sentences)",
        "issueCategory": "Category of issue (e.g., Configuration, Integration, Bug, Training)",
        "estimatedComplexity": "Low/Medium/High",
        "matchesExpertise": true
    }},
    "diagnosticQuestions": [
        "Question 1 to ask the customer to better understand the issue",
        "Question 2",
        "Question 3"
    ],
    "resolutionSteps": [
        "Step 1 to resolve the issue",
        "Step 2",
        "Step 3"
    ],
    "tips": [
        "Helpful tip for handling this type of case",
        "Another tip"
    ],
    "confidenceScore": 0.8
}}

Be specific and actionable. The suggested opening should be ready to copy-paste.
"""

        analysis_task = Task(
            description=task_description,
            expected_output="A valid JSON object with suggestedOpening, recommendedApproach, diagnosticQuestions, resolutionSteps, tips, and confidenceScore",
            agent=support_analyst
        )

        # Create and run the crew
        crew = Crew(
            agents=[support_analyst],
            tasks=[analysis_task],
            process=Process.sequential,
            verbose=True
        )

        result = crew.kickoff()

        # Parse the result
        result_text = str(result)

        # Try to extract JSON from the result
        try:
            import re
            json_match = re.search(r'\{[\s\S]*\}', result_text)
            if json_match:
                parsed_result = json.loads(json_match.group())
                return {
                    "success": True,
                    "result": parsed_result
                }
        except json.JSONDecodeError:
            pass

        # Return structured fallback if JSON parsing fails
        return {
            "success": True,
            "result": {
                "suggestedOpening": f"Thank you for reaching out regarding {case_subject}. I understand this is important and I'm here to help.",
                "recommendedApproach": {
                    "summary": "Review the case details and gather more information",
                    "issueCategory": case_type or "General",
                    "estimatedComplexity": "Medium",
                    "matchesExpertise": True
                },
                "diagnosticQuestions": [
                    "When did you first notice this issue?",
                    "Have there been any recent changes to your setup?",
                    "Can you provide any error messages or screenshots?"
                ],
                "resolutionSteps": [
                    "Gather additional details from the customer",
                    "Review relevant documentation",
                    "Test the reported scenario if possible",
                    "Provide solution or escalate if needed"
                ],
                "tips": [
                    "Be empathetic and acknowledge the customer's frustration",
                    "Set clear expectations about next steps and timeline"
                ],
                "confidenceScore": 0.6,
                "rawResponse": result_text
            }
        }
