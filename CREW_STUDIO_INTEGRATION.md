# Crew Studio MCP Integration Guide

This document explains how to implement the `/api/crew/studio-run` endpoint in the Python service to support Crew Studio with MCP tools.

## Overview

Crew Studio sends crew configurations in two modes:
- **Simple Mode**: Expertise + questions (beginner-friendly)
- **Advanced Mode**: Full agent + task configs (power users)

Both modes can include MCP tool selections (Avoma, Salesforce, Zendesk, etc.)

## Request Format

```json
{
  "mode": "simple" | "advanced",
  "name": "Crew Name",
  "target_type": "account" | "opportunity" | "project" | "case",
  "target_id": "0013100001...",
  "context": { "additional": "data" },
  "mcp_tools": ["avoma", "salesforce", "zendesk"],
  "userId": "uuid",

  // Simple mode fields:
  "expertise": "You are a senior sales strategist...",
  "questions": "1. What is...\n2. How can...",
  "data_sources": ["accounts", "opportunities", "meetings"],
  "output_format": "Markdown with clear sections",

  // OR Advanced mode fields:
  "agent": {
    "role": "Sales Analyst",
    "goal": "...",
    "backstory": "...",
    "verbose": true,
    "allow_delegation": false
  },
  "task": {
    "description": "...",
    "expected_output": "..."
  }
}
```

## Implementation Example

```python
# luci-crews/src/luci_crews/routes/studio.py

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from crewai import Agent, Task, Crew, Process, LLM
from ..mcp_client import get_mcp_tools
import os
import json
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/crew/studio-run", tags=["studio"])


@router.post("")
async def run_studio_crew(request: Request):
    """
    Run a Crew Studio crew with streaming results.

    Supports both simple mode and advanced mode with optional MCP tools.
    """
    try:
        body = await request.json()
        mode = body.get("mode")
        name = body.get("name")
        target_type = body.get("target_type")
        target_id = body.get("target_id")
        context = body.get("context", {})
        mcp_tools_requested = body.get("mcp_tools", [])
        user_id = body.get("userId")

        # Get MCP tools if requested
        mcp_tools = []
        if mcp_tools_requested:
            logger.info(f"Loading MCP tools: {mcp_tools_requested}")
            mcp_tools = get_mcp_tools(mcp_tools_requested)
            logger.info(f"Loaded {len(mcp_tools)} MCP tools")

        # Initialize LLM
        llm = LLM(
            model=os.environ.get("OPENAI_MODEL_NAME", "gpt-4o-mini"),
            api_key=os.environ.get("OPENAI_API_KEY"),
        )

        # Create agent based on mode
        if mode == "simple":
            agent = create_simple_mode_agent(body, llm, mcp_tools)
            task = create_simple_mode_task(body, target_id, context)
        else:  # advanced
            agent = create_advanced_mode_agent(body, llm, mcp_tools)
            task = create_advanced_mode_task(body, target_id, context)

        # Create crew
        crew = Crew(
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            verbose=False,
        )

        # Stream results
        async def generate_stream():
            # Send progress
            yield f"data: {json.dumps({'type': 'progress', 'message': f'Starting {name}...', 'agent': agent.role})}\n\n"

            try:
                # Prepare inputs
                inputs = {
                    "target_id": target_id,
                    "target_type": target_type,
                    **context,
                }

                # Run crew
                result = crew.kickoff(inputs=inputs)

                # Send result
                yield f"data: {json.dumps({'type': 'result', 'result': str(result)})}\n\n"

            except Exception as e:
                logger.error(f"Error running crew: {e}")
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except Exception as e:
        logger.error(f"Error in studio-run: {e}")
        return {"error": str(e)}, 500


def create_simple_mode_agent(body, llm, mcp_tools):
    """Create agent from simple mode config."""
    expertise = body.get("expertise", "")

    return Agent(
        role=body.get("name"),
        goal=f"Answer the questions using available data and tools",
        backstory=expertise,
        verbose=True,
        allow_delegation=False,
        llm=llm,
        tools=mcp_tools,
    )


def create_simple_mode_task(body, target_id, context):
    """Create task from simple mode config."""
    questions = body.get("questions", "")
    output_format = body.get("output_format", "")

    description = f"""
    Target ID: {target_id}
    Additional Context: {json.dumps(context, indent=2)}

    Please answer the following questions:
    {questions}
    """

    if output_format:
        description += f"\n\nOutput Format: {output_format}"

    return Task(
        description=description,
        expected_output="Comprehensive answers to all questions" + (f" in {output_format}" if output_format else ""),
        agent=None,  # Will be assigned by crew
    )


def create_advanced_mode_agent(body, llm, mcp_tools):
    """Create agent from advanced mode config."""
    agent_config = body.get("agent", {})

    return Agent(
        role=agent_config.get("role"),
        goal=agent_config.get("goal"),
        backstory=agent_config.get("backstory"),
        verbose=agent_config.get("verbose", True),
        allow_delegation=agent_config.get("allow_delegation", False),
        llm=llm,
        tools=mcp_tools,
    )


def create_advanced_mode_task(body, target_id, context):
    """Create task from advanced mode config."""
    task_config = body.get("task", {})

    # Replace {target_id} and other variables in description
    description = task_config.get("description", "")
    description = description.replace("{target_id}", str(target_id))

    # Add context variables
    for key, value in context.items():
        description = description.replace(f"{{{key}}}", str(value))

    return Task(
        description=description,
        expected_output=task_config.get("expected_output", "Completed task output"),
        agent=None,  # Will be assigned by crew
    )
```

## Fetching Data for Crews

When crews have `data_sources` selected (simple mode), you may want to pre-fetch data:

```python
async def fetch_data_for_crew(target_type, target_id, data_sources):
    """Fetch data based on selected data sources."""
    data = {}

    if "accounts" in data_sources and target_type == "account":
        # Fetch account data from Supabase or use Salesforce MCP tool
        data["account"] = await fetch_account(target_id)

    if "opportunities" in data_sources:
        # Fetch related opportunities
        data["opportunities"] = await fetch_opportunities_for_account(target_id)

    if "meetings" in data_sources:
        # Let the agent use Avoma MCP tool instead of pre-fetching
        pass

    return data
```

## Register the Router

In `luci-crews/src/luci_crews/main.py`:

```python
from .routes import studio

app.include_router(studio.router, prefix="/api")
```

## Testing

Test with curl:

```bash
curl -X POST http://localhost:8000/api/crew/studio-run \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "simple",
    "name": "Account Analyst",
    "expertise": "You are an expert account analyst",
    "questions": "1. What is the account health?\n2. What are the risks?",
    "target_type": "account",
    "target_id": "0013100001abc123",
    "mcp_tools": ["salesforce", "avoma"],
    "userId": "user-123"
  }'
```

## Available MCP Tools

The `get_mcp_tools()` function from `mcp_client.py` supports:

- **avoma**: `list_meetings`, `get_meeting`, `get_meeting_transcript`, `get_meeting_notes`
- **salesforce**: `salesforce_query`, `salesforce_search`, `salesforce_get_record`, `salesforce_describe`
- **zendesk**: `zendesk_get_tickets`, `zendesk_get_ticket`, `zendesk_create_ticket`
- **snowflake**: `snowflake_query`, `snowflake_list_tables`, `snowflake_describe_table`
- **hubspot**: `hubspot_search_contacts`, `hubspot_search_companies`, `hubspot_search_deals`
- **userevidence**: `userevidence_search_assets`

Agents can use these tools automatically when they need data.
