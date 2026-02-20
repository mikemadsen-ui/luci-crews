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
        mcp_tools = []

        try:
            # Load MCP tools if requested (with timeout protection)
            if request.mcp_tools:
                logger.info(f"Loading MCP tools: {request.mcp_tools}")
                yield f"data: {json.dumps({'type': 'progress', 'message': 'Loading MCP tools...'})}\n\n"

                try:
                    # MCP tools connect to remote servers (Avoma, Salesforce, etc.)
                    # and need time for schema discovery. 30s is generous but safe.
                    import asyncio
                    mcp_future = asyncio.to_thread(get_mcp_tools, request.mcp_tools)
                    mcp_tools = await asyncio.wait_for(mcp_future, timeout=30.0)

                    if mcp_tools:
                        logger.info(f"Loaded {len(mcp_tools)} MCP tools")
                        yield f"data: {json.dumps({'type': 'progress', 'message': f'Loaded {len(mcp_tools)} MCP tools'})}\n\n"
                    else:
                        logger.warning(f"No MCP tools loaded")
                        yield f"data: {json.dumps({'type': 'progress', 'message': 'Continuing without MCP tools'})}\n\n"
                except asyncio.TimeoutError:
                    logger.warning("MCP tool loading timed out after 30 seconds")
                    yield f"data: {json.dumps({'type': 'progress', 'message': 'MCP tools timed out, continuing without them'})}\n\n"
                except Exception as e:
                    logger.warning(f"Error loading MCP tools: {str(e)[:100]}")
                    yield f"data: {json.dumps({'type': 'progress', 'message': 'Continuing without MCP tools'})}\n\n"

            # Initialize LLM — use OPENAI_MODEL_NAME env var (default gpt-4o).
            # TODO: Wire up user's management-level model preference (needs local testing first)
            model_name = os.environ.get("OPENAI_MODEL_NAME", "gpt-4o")
            logger.info(f"Using model: {model_name}")
            llm = LLM(
                model=model_name,
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

                # Build task description with MCP tool guidance
                mcp_guidance = ""
                if mcp_tools:
                    mcp_guidance = """
IMPORTANT - MCP Tool Usage Guidelines:
- When querying Salesforce, ALWAYS use salesforce_describe first to discover the actual fields on an object before writing SOQL queries. Do NOT guess custom field names.
- If a query fails with "No such column", use salesforce_describe to find the correct field name and retry.
- Use salesforce_get_record with the target ID to get a quick overview of the record.
- Keep SOQL queries simple - select only the fields you need.
- For meetings, use list_meetings with date ranges to find relevant calls.
"""

                description = f"""
Target ID: {request.target_id}
Target Type: {request.target_type}
Additional Context: {json.dumps(request.context or {}, indent=2)}
{mcp_guidance}
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
