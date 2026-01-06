"""
Example: CrewAI Agent with Avoma MCP Tools

This demonstrates how to create an agent that can directly query Avoma
meetings and transcripts using the MCP protocol.

REQUIRED ENVIRONMENT VARIABLES:
  AVOMA_API_KEY - Your Avoma API key (from Settings > API Access in Avoma)
  AVOMA_MCP_URL - Optional, defaults to https://mcp.avoma.com/mcp
"""

import os
from crewai import Agent, Task, Crew, Process, LLM
from ..avoma_mcp import get_avoma_tools


def create_meeting_analyst_crew():
    """
    Create a crew with an agent that has direct access to Avoma meetings.

    The agent can use these MCP tools:
    - list_meetings: Search for meetings by account, customer name, date range
    - get_meeting: Get detailed info about a specific meeting
    - get_meeting_transcript: Get the full transcript
    - get_meeting_notes: Get AI-generated meeting notes
    """

    llm = LLM(
        model=os.environ.get("OPENAI_MODEL_NAME", "gpt-4o-mini"),
        api_key=os.environ.get("OPENAI_API_KEY"),
    )

    # Get Avoma MCP tools - these let the agent query Avoma directly
    avoma_tools = get_avoma_tools()

    meeting_analyst = Agent(
        role="Meeting Analyst",
        goal="Analyze customer meetings to extract insights and patterns",
        backstory="""You are an expert at analyzing sales and customer success meetings.
        You have access to Avoma to search for meetings, read transcripts, and review notes.
        You provide actionable insights based on meeting content.""",
        verbose=True,
        allow_delegation=False,
        llm=llm,
        tools=avoma_tools,  # Give agent access to Avoma MCP tools
    )

    analysis_task = Task(
        description="""Analyze recent meetings for the account.

        1. Use list_meetings to find recent meetings for the account
        2. For each relevant meeting, use get_meeting_transcript to read the content
        3. Identify key themes, concerns, and action items
        4. Summarize your findings

        Account: {account_name}
        Salesforce Account ID: {salesforce_account_id}
        """,
        expected_output="""A structured analysis including:
        - Meeting summary (dates, participants, topics)
        - Key themes and patterns
        - Customer concerns or objections
        - Action items and next steps
        - Overall sentiment assessment
        """,
        agent=meeting_analyst,
    )

    crew = Crew(
        agents=[meeting_analyst],
        tasks=[analysis_task],
        process=Process.sequential,
        verbose=True,
    )

    return crew


def run_meeting_analysis(account_name: str, salesforce_account_id: str) -> str:
    """
    Run meeting analysis for an account.

    Args:
        account_name: The account name
        salesforce_account_id: The Salesforce Account ID

    Returns:
        Analysis results as a string
    """
    crew = create_meeting_analyst_crew()
    result = crew.kickoff(inputs={
        "account_name": account_name,
        "salesforce_account_id": salesforce_account_id,
    })
    return str(result)


if __name__ == "__main__":
    # Example usage
    import sys

    if len(sys.argv) < 3:
        print("Usage: python -m luci_crews.crews.avoma_agent_example <account_name> <sf_account_id>")
        sys.exit(1)

    account_name = sys.argv[1]
    sf_account_id = sys.argv[2]

    print(f"Analyzing meetings for {account_name} ({sf_account_id})...")
    result = run_meeting_analysis(account_name, sf_account_id)
    print("\n=== Analysis Result ===\n")
    print(result)
