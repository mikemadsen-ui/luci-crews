"""
Crew Studio Routes - Dynamic crew execution endpoint.

Allows users to create and run custom crews with MCP tool access.
"""

import os
import json
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from crewai import Agent, Task, Crew, Process, LLM

from ..models import StudioCrewRequest
from ..mcp_client import get_mcp_tools

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/crew", tags=["studio"])


@router.post("/studio-run")
async def run_studio_crew(request: StudioCrewRequest):
    """
    Run a Crew Studio crew with dynamic configuration.

    Supports both simple mode (expertise + questions) and advanced mode (full agent/task configs).
    Can optionally use MCP tools for live data access from Avoma, Salesforce, Zendesk, etc.
    """
    start_time = datetime.utcnow()

    async def generate_stream():
        try:
            # Load MCP tools if requested
            mcp_tools = []
            if request.mcp_tools:
                logger.info(f"Loading MCP tools: {request.mcp_tools}")
                try:
                    mcp_tools = get_mcp_tools(request.mcp_tools)
                    logger.info(f"Loaded {len(mcp_tools)} MCP tools")
                    yield f"data: {json.dumps({'type': 'progress', 'message': f'Loaded {len(mcp_tools)} MCP tools'})}\n\n"
                except Exception as e:
                    logger.error(f"Error loading MCP tools: {e}")
                    yield f"data: {json.dumps({'type': 'progress', 'message': f'Warning: Could not load MCP tools: {str(e)}'})}\n\n"

            # Initialize LLM
            llm = LLM(
                model=os.environ.get("OPENAI_MODEL_NAME", "gpt-4o-mini"),
                api_key=os.environ.get("OPENAI_API_KEY"),
            )

            # Create agent based on mode
            if request.mode == "simple":
                agent = Agent(
                    role=request.name,
                    goal="Answer the questions using available data and tools",
                    backstory=request.expertise or "",
                    verbose=True,
                    allow_delegation=False,
                    llm=llm,
                    tools=mcp_tools,
                )

                # Build task description
                description = f"""
Target ID: {request.target_id}
Target Type: {request.target_type}
Additional Context: {json.dumps(request.context or {}, indent=2)}

Please answer the following questions:
{request.questions}
"""
                if request.output_format:
                    description += f"\n\nOutput Format: {request.output_format}"

                task = Task(
                    description=description,
                    expected_output="Comprehensive answers to all questions" + (f" in {request.output_format}" if request.output_format else ""),
                    agent=agent,
                )

            else:  # advanced mode
                agent_config = request.agent or {}
                agent = Agent(
                    role=agent_config.get("role", request.name),
                    goal=agent_config.get("goal", "Complete the assigned task"),
                    backstory=agent_config.get("backstory", ""),
                    verbose=agent_config.get("verbose", True),
                    allow_delegation=agent_config.get("allow_delegation", False),
                    llm=llm,
                    tools=mcp_tools,
                )

                task_config = request.task or {}
                description = task_config.get("description", "")

                # Replace variables in description
                description = description.replace("{target_id}", str(request.target_id))
                description = description.replace("{target_type}", str(request.target_type))

                # Replace context variables
                if request.context:
                    for key, value in request.context.items():
                        description = description.replace(f"{{{key}}}", str(value))

                task = Task(
                    description=description,
                    expected_output=task_config.get("expected_output", "Completed task output"),
                    agent=agent,
                )

            # Create and run crew
            crew = Crew(
                agents=[agent],
                tasks=[task],
                process=Process.sequential,
                verbose=False,
            )

            yield f"data: {json.dumps({'type': 'progress', 'message': f'Starting {request.name}...', 'agent': agent.role})}\n\n"

            # Prepare inputs
            inputs = {
                "target_id": request.target_id,
                "target_type": request.target_type,
                **(request.context or {}),
            }

            # Run crew
            result = crew.kickoff(inputs=inputs)

            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"Studio crew '{request.name}' completed in {execution_time:.2f}s")

            # Send result
            yield f"data: {json.dumps({'type': 'result', 'result': str(result)})}\n\n"

        except Exception as e:
            logger.error(f"Error running studio crew: {e}", exc_info=True)
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
