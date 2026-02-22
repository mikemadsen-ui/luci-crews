"""
LUCI CrewAI Service - FastAPI Application

Provides API endpoints for running CrewAI crews and serves the CrewAI Studio UI.
"""

import os
import sys
from io import StringIO

# Disable CrewAI tracing/telemetry before any crewai imports
os.environ["CREWAI_TRACING_ENABLED"] = "false"
os.environ["CREWAI_TELEMETRY_OPT_OUT"] = "true"
os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"

# Suppress rich console output (CrewAI uses rich for banners)
os.environ["TERM"] = "dumb"
os.environ["NO_COLOR"] = "1"

# Patch rich.console.Console BEFORE any imports to suppress all banners
from rich.console import Console
_original_console_print = Console.print
def _silent_print(self, *args, **kwargs):
    # Only suppress Panel objects (the fancy boxes)
    from rich.panel import Panel
    if args and isinstance(args[0], Panel):
        return  # Suppress banner panels
    return _original_console_print(self, *args, **kwargs)
Console.print = _silent_print

# Suppress stdout during crewai imports
_original_stdout = sys.stdout
sys.stdout = StringIO()

import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from dotenv import load_dotenv

from .models import (
    CrewResponse,
    SalesPipelineRequest,
    AccountHealthRequest,
    AccountAnalysisRequest,
    MavenlinkTaskModel,
    ImplementationRequest,
    SentimentRequest,
    SCPrepRequest,
    TranscriptChunkModel,
    FeatureExtractionRequest,
    AgendaGenerationRequest,
    CallVerificationRequest,
    CallAnalysisRequest,
    SandboxTestRequest,
    CustomAnalysisContext,
    CustomAnalysisRequest,
    QbrSummaryRequest,
    EmailDraftRequest,
    RenewalReadinessRequest,
    ExpansionSpecialistRequest,
    StrategicActionRequest,
    ExecutiveBriefingRequest,
    ContextualDrilldownRequest,
)
from .crews.sales_pipeline_crew import SalesPipelineCrew
from .crews.account_health_crew import AccountHealthCrew
from .crews.implementation_crew import ImplementationCrew
from .crews.sentiment_crew import SentimentCrew
from .crews.sc_prep_crew import SCPrepCrew
from .crews.feature_extraction_crew import FeatureExtractionCrew
from .crews.agenda_generation_crew import AgendaGenerationCrew
from .crews.call_verification_crew import CallVerificationCrew
from .crews.call_analysis_crew import CallAnalysisCrew
from .crews.account_analysis_crew import AccountAnalysisCrew
from .crews.qbr_summary_crew import QbrSummaryCrew
from .crews.email_draft_crew import EmailDraftCrew
from .crews.renewal_readiness_crew import RenewalReadinessCrew
from .crews.expansion_specialist_crew import ExpansionSpecialistCrew
from .crews.strategic_action_crew import StrategicActionCrew
from .crews.executive_briefing_crew import ExecutiveMorningBriefingCrew
from .crews.contextual_drilldown_crew import ContextualDrilldownCrew
from .batch_router import router as batch_router
from .routes.analysis import router as analysis_router
from .routes.coaching import router as coaching_router
from .routes.config import router as config_router
from .routes.health import router as health_router
from .routes.studio import router as studio_router
from .ai_settings_helper import (
    run_with_fallback,
    is_quota_error,
    get_available_providers,
)
from .utils.streaming import (
    SimpleStreamingContext,
    ThreadedStreamingContext,
    create_streaming_response,
    sse_progress,
)
from .utils.account_lookup import lookup_account

# Restore stdout after crewai imports
sys.stdout = _original_stdout

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Suppress verbose HTTP request logging from httpx (shows as errors in Railway)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# Store running jobs
running_jobs: Dict[str, Dict[str, Any]] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting LUCI CrewAI Service...")
    yield
    logger.info("Shutting down LUCI CrewAI Service...")


# Create FastAPI app
app = FastAPI(
    title="LUCI CrewAI Service",
    description="AI-powered analysis crews for LUCI application",
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://luci.vercel.app",
        "https://luci-*.vercel.app",
        "http://localhost:3000",
        "http://localhost:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(analysis_router)  # Analysis crew endpoints (project, opportunity, competitive, support)
app.include_router(batch_router)  # Batch processing for overnight sync jobs
app.include_router(coaching_router)  # Coaching crew endpoints
app.include_router(config_router)  # Config management for Crew Studio
app.include_router(health_router)  # Health check and capabilities endpoints
app.include_router(studio_router)  # Crew Studio dynamic crew execution


# =============================================================================
# Crew Endpoints
# =============================================================================

@app.post("/api/crew/sales_pipeline", response_model=CrewResponse)
async def run_sales_pipeline_crew(request: SalesPipelineRequest):
    """Run the sales pipeline analysis crew."""
    start_time = datetime.utcnow()

    try:
        logger.info(f"Running sales pipeline crew for user: {request.user_email}")

        crew = SalesPipelineCrew(user_id=request.user_id)
        result = crew.run(
            user_email=request.user_email,
            opportunities=request.opportunities,
            summary=request.summary or {},
        )

        execution_time = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"Sales pipeline crew completed in {execution_time:.2f}s")

        return CrewResponse(
            success=True,
            result=result,
            execution_time=execution_time,
        )

    except Exception as e:
        logger.error(f"Sales pipeline crew failed: {str(e)}")
        return CrewResponse(
            success=False,
            error=str(e),
        )


@app.post("/api/crew/account", response_model=CrewResponse)
async def run_account_health_crew(request: AccountHealthRequest):
    """Run the account health analysis crew."""
    start_time = datetime.utcnow()

    try:
        # Get account details - either from request or fetch from Supabase
        account_name = request.account_name
        account_tier = request.account_tier
        arr = request.arr

        # If we have accountId or salesforceAccountId but no account_name, fetch from Supabase
        if not account_name and (request.accountId or request.salesforceAccountId):
            account_data = lookup_account(
                account_id=request.accountId,
                salesforce_account_id=request.salesforceAccountId,
            )
            if account_data.found:
                account_name = account_data.name
                account_tier = account_tier or account_data.account_tier
                arr = arr or account_data.contract_value_numeric

        if not account_name:
            return CrewResponse(
                success=False,
                error="Account name is required. Please provide account_name or a valid accountId/salesforceAccountId.",
            )

        logger.info(f"Running account health crew for: {account_name}")

        crew = AccountHealthCrew(user_id=request.userId)
        result = crew.run(
            account_name=account_name,
            account_tier=account_tier,
            arr=arr,
            activity_data=request.activity_data,
            support_data=request.support_data,
            engagement_data=request.engagement_data,
        )

        execution_time = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"Account health crew completed in {execution_time:.2f}s")

        return CrewResponse(
            success=True,
            result=result,
            execution_time=execution_time,
        )

    except Exception as e:
        logger.error(f"Account health crew failed: {str(e)}")
        return CrewResponse(
            success=False,
            error=str(e),
        )


@app.post("/api/crew/account-analysis")
async def run_account_analysis_crew(request: AccountAnalysisRequest):
    """
    Run the unified account analysis crew (combines sentiment + health).

    Returns a single score with breakdown details for both sentiment and health.
    """
    start_time = datetime.utcnow()

    try:
        # Get account name - from request or fetch from Supabase
        account_name = request.accountName

        if not account_name and (request.accountId or request.salesforceAccountId):
            account_data = lookup_account(
                account_id=request.accountId,
                salesforce_account_id=request.salesforceAccountId,
            )
            if account_data.found:
                account_name = account_data.name
                if not request.accountTier:
                    request.accountTier = account_data.account_tier
                if not request.arr:
                    request.arr = account_data.contract_value_numeric

        if not account_name:
            return {
                "success": False,
                "error": "Account name is required. Please provide accountName or a valid accountId/salesforceAccountId.",
            }

        logger.info(f"Running unified account analysis for: {account_name}")

        # Extract support data from salesforceContext
        support_data = None
        if request.salesforceContext:
            support_data = {
                "total_cases_count": request.salesforceContext.get("total_cases_count", 0),
                "recent_tickets": request.salesforceContext.get("recent_tickets", []),
            }

        # Use fallback mechanism to handle quota/rate limit errors
        # This will automatically try other providers if the primary fails
        def crew_factory(llm):
            return AccountAnalysisCrew(user_id=request.userId, llm=llm)

        run_args = {
            "account_name": account_name,
            "account_tier": request.accountTier,
            "arr": request.arr,
            "transcription": request.transcription,
            "support_data": support_data,
            "engagement_data": request.engagementData,
        }

        result = run_with_fallback(
            crew_factory=crew_factory,
            run_args=run_args,
            user_id=request.userId,
        )

        execution_time = (datetime.utcnow() - start_time).total_seconds()

        # Log which provider was used
        provider_used = result.get("_provider_used", "unknown") if isinstance(result, dict) else "unknown"
        providers_tried = result.get("_providers_tried", []) if isinstance(result, dict) else []
        logger.info(f"Unified account analysis completed in {execution_time:.2f}s using provider: {provider_used}")
        if len(providers_tried) > 1:
            logger.info(f"Providers tried before success: {providers_tried}")
        logger.info(f"Score: {result.get('score')}, Status: {result.get('status')}")

        return {
            "success": True,
            "result": result,
            "execution_time": execution_time,
        }

    except Exception as e:
        logger.error(f"Unified account analysis failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
        }


@app.post("/api/crew/implementation", response_model=CrewResponse)
async def run_implementation_crew(request: ImplementationRequest):
    """Run the implementation project analysis crew."""
    start_time = datetime.utcnow()

    try:
        logger.info(f"Running implementation crew for: {request.project_name}")
        if request.callActivity:
            metrics = request.callActivity.get("metrics", {})
            logger.info(f"Call activity: {metrics.get('totalRecentCalls', 0)} past calls, {metrics.get('upcomingCallsCount', 0)} upcoming")
        if request.mavenlinkTasks:
            logger.info(f"Mavenlink tasks: {len(request.mavenlinkTasks)} stories/tasks")

        # Log data availability warnings if present
        if request.dataAvailabilityWarnings:
            logger.warning(f"Data availability warnings: {request.dataAvailabilityWarnings}")

        crew = ImplementationCrew(user_id=request.userId)
        result = crew.run(
            project_name=request.project_name,
            account_name=request.account_name,
            project_status=request.project_status,
            start_date=request.start_date,
            target_go_live=request.target_go_live,
            completion_pct=request.completion_pct,
            hours_used=request.hours_used,
            hours_budgeted=request.hours_budgeted,
            budget_used=request.budget_used,
            budget_total=request.budget_total,
            milestones_data=request.milestones_data,
            risks_data=request.risks_data,
            call_activity=request.callActivity,
            mavenlink_tasks=request.mavenlinkTasks,
            data_availability_warnings=request.dataAvailabilityWarnings,
        )

        execution_time = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"Implementation crew completed in {execution_time:.2f}s")

        return CrewResponse(
            success=True,
            result=result,
            execution_time=execution_time,
        )

    except Exception as e:
        logger.error(f"Implementation crew failed: {str(e)}")
        return CrewResponse(
            success=False,
            error=str(e),
        )


@app.post("/api/crew/sentiment", response_model=CrewResponse)
async def run_sentiment_crew(request: SentimentRequest):
    """Run the sentiment analysis crew with automatic provider fallback."""
    start_time = datetime.utcnow()

    try:
        # Extract account name from salesforceContext or customerIdentifier
        account_name = request.customerIdentifier
        if request.salesforceContext and request.salesforceContext.get("account_name"):
            account_name = request.salesforceContext.get("account_name")

        logger.info(f"Running sentiment crew for: {account_name}")

        # Build support data summary from salesforceContext
        support_data = None
        if request.salesforceContext:
            ctx = request.salesforceContext
            recent_tickets = ctx.get("recent_tickets", [])
            support_parts = []
            if ctx.get("total_cases_count"):
                support_parts.append(f"Total support cases: {ctx.get('total_cases_count')}")
            if recent_tickets:
                support_parts.append(f"Recent tickets ({len(recent_tickets)}):")
                for ticket in recent_tickets[:10]:
                    support_parts.append(f"  - {ticket.get('subject', 'No subject')} [{ticket.get('status', 'Unknown')}] Priority: {ticket.get('priority', 'Unknown')}")
            support_data = "\n".join(support_parts) if support_parts else None

        # Prepare run arguments
        run_args = {
            "account_name": account_name or "Unknown Account",
            "communications_data": request.transcription,
            "support_data": support_data,
            "meeting_notes": None,
        }

        # Use fallback mechanism to handle quota/rate limit errors
        # This will automatically try other providers if the primary fails
        def crew_factory(llm):
            return SentimentCrew(llm=llm)

        result = run_with_fallback(
            crew_factory=crew_factory,
            run_args=run_args,
            user_id=request.userId,
        )

        execution_time = (datetime.utcnow() - start_time).total_seconds()

        # Log which provider was used
        provider_used = result.get("_provider_used", "unknown") if isinstance(result, dict) else "unknown"
        providers_tried = result.get("_providers_tried", []) if isinstance(result, dict) else []
        logger.info(f"Sentiment crew completed in {execution_time:.2f}s using provider: {provider_used}")
        if len(providers_tried) > 1:
            logger.info(f"Providers tried before success: {providers_tried}")

        return CrewResponse(
            success=True,
            result=result,
            execution_time=execution_time,
        )

    except Exception as e:
        logger.error(f"Sentiment crew failed: {str(e)}")
        return CrewResponse(
            success=False,
            error=str(e),
        )


# =============================================================================
# Coaching endpoints moved to routes/coaching.py
# Analysis endpoints (project-sentiment, project-analysis, opportunity,
# competitive, support_resolution) moved to routes/analysis.py
# =============================================================================


@app.post("/api/crew/sc-prep")
async def run_sc_prep_crew(request: Request):
    """Run the SC preparation crew for discovery synthesis, demo prep, and competitive intel."""
    stream = request.query_params.get("stream", "false").lower() == "true"

    try:
        body = await request.json()
        req = SCPrepRequest(**body)
        logger.info(f"Running SC prep crew for opportunity: {req.opportunityId} (type: {req.prepType})")

        crew = SCPrepCrew(user_id=req.userId)

        if stream:
            ctx = SimpleStreamingContext()

            async def generate():
                try:
                    yield ctx.init_message("Starting SC preparation...")
                    result = crew.run(
                        opportunity_id=req.opportunityId,
                        prep_type=req.prepType or "full",
                        user_id=req.userId,
                        force_refresh=req.forceRefresh or False,
                        step_callback=ctx.step_callback,
                        opportunity_data=req.opportunityData.model_dump() if req.opportunityData else None,
                        transcription_data=[t.model_dump() for t in req.transcriptionData] if req.transcriptionData else None,
                    )
                    for msg in ctx.get_progress_messages():
                        yield msg
                    logger.info(f"SC prep crew completed in {ctx.execution_time:.2f}s")
                    yield ctx.result_message(result.get('result'),
                        input_hash=result.get('input_hash'),
                        opportunity_name=result.get('opportunity_name'),
                        account_name=result.get('account_name'),
                        prep_type=result.get('prep_type'),
                        provider=result.get('provider'), model=result.get('model'))
                except Exception as e:
                    logger.error(f"SC prep crew failed: {str(e)}")
                    yield ctx.error_message(str(e))

            return create_streaming_response(generate())
        else:
            start_time = datetime.utcnow()
            result = crew.run(
                opportunity_id=req.opportunityId,
                prep_type=req.prepType or "full",
                user_id=req.userId,
                force_refresh=req.forceRefresh or False,
                opportunity_data=req.opportunityData.model_dump() if req.opportunityData else None,
                transcription_data=[t.model_dump() for t in req.transcriptionData] if req.transcriptionData else None,
            )
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"SC prep crew completed in {execution_time:.2f}s")
            return {
                "success": True, "result": result.get("result"),
                "input_hash": result.get("input_hash"),
                "opportunity_name": result.get("opportunity_name"),
                "account_name": result.get("account_name"),
                "prep_type": result.get("prep_type"),
                "provider": result.get("provider"), "model": result.get("model"),
                "execution_time": execution_time,
            }

    except Exception as e:
        logger.error(f"SC prep crew failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Config endpoints moved to routes/config.py
# =============================================================================


# =============================================================================
# Sandbox Test Runner (Crew Studio)
# =============================================================================

@app.post("/api/crew/sandbox-test")
async def run_sandbox_test(request: SandboxTestRequest):
    """Run a sandbox test with custom agent/task configurations."""
    from crewai import Agent, Task, Crew, Process, LLM

    ctx = ThreadedStreamingContext()

    async def generate():
        try:
            yield ctx.init_message("Initializing sandbox test...")

            def run_crew(step_callback):
                llm = LLM(
                    model=os.environ.get("OPENAI_MODEL_NAME", "gpt-4o-mini"),
                    api_key=os.environ.get("OPENAI_API_KEY"),
                )
                agent_config = request.agent
                agent_role = agent_config.get("role", "Test Agent")
                step_callback(f"Creating agent: {agent_role}")

                test_agent = Agent(
                    role=agent_role,
                    goal=agent_config.get("goal", "Complete the assigned task"),
                    backstory=agent_config.get("backstory", "An expert assistant."),
                    verbose=agent_config.get("verbose", True),
                    allow_delegation=agent_config.get("allow_delegation", False),
                    llm=llm,
                )
                task_config = request.task
                task_description = task_config.get("description", "Analyze the provided data.")
                for key, value in (request.sampleData or {}).items():
                    task_description = task_description.replace(f"{{{key}}}", str(value))

                step_callback("Creating task...")
                test_task = Task(
                    description=task_description,
                    expected_output=task_config.get("expected_output", "A comprehensive analysis."),
                    agent=test_agent,
                )
                step_callback("Running analysis...")
                crew = Crew(agents=[test_agent], tasks=[test_task], process=Process.sequential, verbose=True)
                result = crew.kickoff()
                result_text = str(result) if result else "No result"
                step_callback(f"Completed in {ctx.execution_time:.1f}s")
                return {"result": result_text, "duration": ctx.execution_time}

            async for msg in ctx.run_with_progress(run_crew):
                yield msg

            if ctx.error:
                logger.error(f"Sandbox test error: {ctx.error}")
                yield ctx.error_message()
            elif ctx.result:
                yield ctx.result_message(ctx.result.get("result"), duration=ctx.result.get("duration"))

        except Exception as e:
            logger.error(f"Sandbox test error: {e}")
            yield ctx.error_message(str(e))

    return create_streaming_response(generate())


# =============================================================================
# Feature Extraction Crew
# =============================================================================

@app.post("/api/crew/feature-extraction")
async def run_feature_extraction_crew(request: FeatureExtractionRequest):
    """Run the feature extraction crew to extract feature requests from transcript chunks."""
    start_time = datetime.utcnow()

    try:
        chunks = request.transcriptChunks
        if not chunks:
            raise HTTPException(status_code=400, detail="No transcript chunks provided")

        logger.info(f"Running feature extraction crew on {len(chunks)} transcript chunks")

        # Convert Pydantic models to dicts for the crew
        chunk_dicts = [
            {
                "content": chunk.content,
                "accountId": chunk.accountId,
                "accountName": chunk.accountName,
                "meetingSubject": chunk.meetingSubject,
                "meetingDate": chunk.meetingDate,
                "meetingUrl": chunk.meetingUrl,
                "transcriptionId": chunk.transcriptionId,
            }
            for chunk in chunks
        ]

        crew = FeatureExtractionCrew(user_id=request.userId)
        result = crew.run(transcript_chunks=chunk_dicts)

        execution_time = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"Feature extraction crew completed in {execution_time:.2f}s, extracted {result.get('count', 0)} requests")

        return {
            "success": True,
            "feature_requests": result.get("feature_requests", []),
            "count": result.get("count", 0),
            "execution_time": execution_time,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Feature extraction crew failed: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "feature_requests": [],
            "count": 0,
        }


# =============================================================================
# Agenda Generation Crew
# =============================================================================

@app.post("/api/crew/agenda-generation")
async def run_agenda_generation_crew(request: AgendaGenerationRequest):
    """Generate a call agenda for an upcoming implementation call."""
    start_time = datetime.utcnow()

    try:
        logger.info(f"Running agenda generation crew for project: {request.projectName}")
        logger.info(f"Call subject: {request.callSubject}, scheduled: {request.callScheduledAt}")

        if request.mavenlinkTasks:
            logger.info(f"Mavenlink tasks provided: {len(request.mavenlinkTasks)}")
        if request.incompleteItems:
            logger.info(f"Incomplete items to carry forward: {len(request.incompleteItems)}")

        crew = AgendaGenerationCrew(user_id=request.userId)
        result = crew.run(
            project_name=request.projectName,
            account_name=request.accountName,
            project_status=request.projectStatus,
            call_subject=request.callSubject,
            call_scheduled_at=request.callScheduledAt,
            target_go_live=request.targetGoLive,
            completion_pct=request.completionPct,
            mavenlink_tasks=request.mavenlinkTasks,
            incomplete_items=request.incompleteItems,
            recent_calls=request.recentCalls,
            attendees=request.attendees,
        )

        execution_time = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"Agenda generation crew completed in {execution_time:.2f}s")

        # Extract agenda items from result
        parsed_result = result.get("result", {})
        agenda_items = parsed_result.get("agenda_items", [])

        return {
            "success": True,
            "agenda_items": agenda_items,
            "suggested_duration": parsed_result.get("suggested_duration_minutes"),
            "call_objectives": parsed_result.get("call_objectives", []),
            "preparation_notes": parsed_result.get("preparation_notes"),
            "raw_output": result.get("raw_output"),
            "execution_time": execution_time,
        }

    except Exception as e:
        logger.error(f"Agenda generation crew failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "agenda_items": [],
        }


# =============================================================================
# Call Verification Crew
# =============================================================================

@app.post("/api/crew/call-verification")
async def run_call_verification_crew(request: CallVerificationRequest):
    """Verify agenda item completion from a call transcript."""
    start_time = datetime.utcnow()

    try:
        logger.info(f"Running call verification crew for project: {request.projectName}")
        logger.info(f"Verifying {len(request.agendaItems)} agenda items")

        if not request.transcript:
            return {
                "success": False,
                "error": "No transcript provided",
                "verified_items": [],
            }

        crew = CallVerificationCrew(user_id=request.userId)
        result = crew.run(
            project_name=request.projectName,
            account_name=request.accountName,
            call_date=request.callDate,
            agenda_items=request.agendaItems,
            transcript=request.transcript,
            speakers=request.speakers,
        )

        execution_time = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"Call verification crew completed in {execution_time:.2f}s")

        # Extract verification results
        parsed_result = result.get("result", {})

        return {
            "success": True,
            "verified_items": parsed_result.get("verified_items", []),
            "new_action_items": parsed_result.get("new_action_items", []),
            "call_summary": parsed_result.get("call_summary"),
            "follow_up_needed": parsed_result.get("follow_up_needed", False),
            "next_call_topics": parsed_result.get("next_call_suggested_topics", []),
            "raw_output": result.get("raw_output"),
            "execution_time": execution_time,
        }

    except Exception as e:
        logger.error(f"Call verification crew failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "verified_items": [],
        }


@app.post("/api/crew/call-analysis")
async def run_call_analysis_crew(request: CallAnalysisRequest):
    """
    Run per-call sentiment and engagement analysis on a meeting transcript.

    Analyzes:
    - Customer sentiment (product, company, IC)
    - Engagement metrics (talk time, questions)
    - Action items, blockers, concerns
    - Risk level and coaching recommendations
    """
    start_time = datetime.utcnow()

    try:
        logger.info(f"Running call analysis crew for: {request.meetingSubject}")
        logger.info(f"Project: {request.projectName}, Account: {request.accountName}")
        logger.info(f"Transcript segments: {len(request.transcriptSegments)}, Speakers: {len(request.speakers)}")

        if not request.transcriptSegments:
            return {
                "success": False,
                "error": "No transcript segments provided",
            }

        if not request.speakers:
            return {
                "success": False,
                "error": "No speaker data provided",
            }

        crew = CallAnalysisCrew(user_id=request.userId)
        result = crew.run(
            transcript_segments=request.transcriptSegments,
            speakers=request.speakers,
            project_name=request.projectName,
            account_name=request.accountName,
            meeting_subject=request.meetingSubject,
            meeting_date=request.meetingDate,
            attendees=request.attendees,
            implementation_stage=request.implementationStage,
            project_context=request.projectContext,
        )

        execution_time = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"Call analysis crew completed in {execution_time:.2f}s")
        logger.info(f"Risk level: {result.get('risk_level')}, Overall sentiment: {result.get('overall_sentiment')}")

        return {
            "success": True,
            # Sentiment scores
            "product_sentiment": result.get("product_sentiment"),
            "company_sentiment": result.get("company_sentiment"),
            "ic_sentiment": result.get("ic_sentiment"),
            "overall_sentiment": result.get("overall_sentiment"),
            "sentiment_summary": result.get("sentiment_summary"),
            # Engagement
            "customer_talk_time_pct": result.get("customer_talk_time_pct"),
            "vendor_talk_time_pct": result.get("vendor_talk_time_pct"),
            "customer_questions_count": result.get("customer_questions_count"),
            "vendor_questions_count": result.get("vendor_questions_count"),
            "engagement_level": result.get("engagement_level"),
            # Speakers with classification
            "speakers": result.get("speakers"),
            # Extracted insights
            "key_concerns": result.get("key_concerns"),
            "positive_signals": result.get("positive_signals"),
            "commitments_made": result.get("commitments_made"),
            "blockers_surfaced": result.get("blockers_surfaced"),
            "decision_points": result.get("decision_points"),
            # Risk and coaching
            "implementation_stage": result.get("implementation_stage"),
            "risk_level": result.get("risk_level"),
            "risk_factors": result.get("risk_factors"),
            "coaching_notes": result.get("coaching_notes"),
            "follow_up_actions": result.get("follow_up_actions"),
            # Metadata
            "analyzed_at": result.get("analyzed_at"),
            "analysis_duration_ms": result.get("analysis_duration_ms"),
            "model_version": result.get("model_version"),
            "execution_time": execution_time,
            # For storage - pass through IDs
            "transcription_id": request.transcriptionId,
            "avoma_meeting_uuid": request.avomaMeetingUuid,
            "salesforce_account_id": request.salesforceAccountId,
            "salesforce_project_id": request.salesforceProjectId,
            "meeting_date": request.meetingDate,
            "meeting_subject": request.meetingSubject,
        }

    except Exception as e:
        logger.error(f"Call analysis crew failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
        }


# =============================================================================
# QBR Summary Crew
# =============================================================================

@app.post("/api/crew/qbr-summary")
async def run_qbr_summary_crew(request: Request):
    """Generate a quarterly business review summary for an account."""
    stream = request.query_params.get("stream", "false").lower() == "true"

    try:
        body = await request.json()
        req = QbrSummaryRequest(**body)
        logger.info(f"Running QBR summary crew for account: {req.accountName}")

        crew = QbrSummaryCrew(user_id=req.userId)

        if stream:
            ctx = SimpleStreamingContext()

            async def generate():
                try:
                    yield ctx.init_message("Starting QBR summary generation...")
                    result = crew.run(
                        account_id=req.accountId,
                        account_name=req.accountName,
                        quarter_start=req.quarterStart,
                        quarter_end=req.quarterEnd,
                        user_id=req.userId,
                        step_callback=ctx.step_callback,
                        health_trend_data=req.healthTrendData,
                        usage_data=req.usageData,
                        support_cases_data=req.supportCasesData,
                        renewal_data=req.renewalData,
                    )
                    for msg in ctx.get_progress_messages():
                        yield msg
                    logger.info(f"QBR summary crew completed in {ctx.execution_time:.2f}s")
                    yield ctx.result_message(
                        result.get('result'),
                        account_name=result.get('account_name'),
                        quarter=result.get('quarter'),
                        provider=result.get('provider'),
                        model=result.get('model'),
                    )
                except Exception as e:
                    logger.error(f"QBR summary crew failed: {str(e)}")
                    yield ctx.error_message(str(e))

            return create_streaming_response(generate())
        else:
            start_time = datetime.utcnow()
            result = crew.run(
                account_id=req.accountId,
                account_name=req.accountName,
                quarter_start=req.quarterStart,
                quarter_end=req.quarterEnd,
                user_id=req.userId,
                health_trend_data=req.healthTrendData,
                usage_data=req.usageData,
                support_cases_data=req.supportCasesData,
                renewal_data=req.renewalData,
            )
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"QBR summary crew completed in {execution_time:.2f}s")
            return {
                "success": result.get("success", True),
                "result": result.get("result"),
                "account_name": result.get("account_name"),
                "quarter": result.get("quarter"),
                "provider": result.get("provider"),
                "model": result.get("model"),
                "execution_time": execution_time,
            }

    except Exception as e:
        logger.error(f"QBR summary crew failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Email Draft Crew
# =============================================================================

@app.post("/api/crew/email-draft")
async def run_email_draft_crew(request: Request):
    """Draft a customer email based on template type and account context."""
    stream = request.query_params.get("stream", "false").lower() == "true"

    try:
        body = await request.json()
        req = EmailDraftRequest(**body)
        logger.info(f"Running email draft crew: {req.templateType} for account {req.accountId}")

        crew = EmailDraftCrew(user_id=req.userId)

        if stream:
            ctx = SimpleStreamingContext()

            async def generate():
                try:
                    yield ctx.init_message(f"Drafting {req.templateType} email...")
                    result = crew.run(
                        account_id=req.accountId,
                        template_type=req.templateType,
                        recipient_role=req.recipientRole,
                        additional_context=req.additionalContext,
                        user_id=req.userId,
                        step_callback=ctx.step_callback,
                        account_data=req.accountData,
                        recent_interactions=req.recentInteractions,
                        open_cases=req.openCases,
                        renewal_status=req.renewalStatus,
                    )
                    for msg in ctx.get_progress_messages():
                        yield msg
                    logger.info(f"Email draft crew completed in {ctx.execution_time:.2f}s")
                    yield ctx.result_message(
                        result.get('result'),
                        account_name=result.get('account_name'),
                        template_type=result.get('template_type'),
                        provider=result.get('provider'),
                        model=result.get('model'),
                    )
                except Exception as e:
                    logger.error(f"Email draft crew failed: {str(e)}")
                    yield ctx.error_message(str(e))

            return create_streaming_response(generate())
        else:
            start_time = datetime.utcnow()
            result = crew.run(
                account_id=req.accountId,
                template_type=req.templateType,
                recipient_role=req.recipientRole,
                additional_context=req.additionalContext,
                user_id=req.userId,
                account_data=req.accountData,
                recent_interactions=req.recentInteractions,
                open_cases=req.openCases,
                renewal_status=req.renewalStatus,
            )
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"Email draft crew completed in {execution_time:.2f}s")
            return {
                "success": result.get("success", True),
                "result": result.get("result"),
                "account_name": result.get("account_name"),
                "template_type": result.get("template_type"),
                "provider": result.get("provider"),
                "model": result.get("model"),
                "execution_time": execution_time,
            }

    except Exception as e:
        logger.error(f"Email draft crew failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Renewal Readiness Crew
# =============================================================================

@app.post("/api/crew/renewal-readiness")
async def run_renewal_readiness_crew(request: Request):
    """Assess renewal readiness with risk scoring and strategic recommendations."""
    stream = request.query_params.get("stream", "false").lower() == "true"

    try:
        body = await request.json()
        req = RenewalReadinessRequest(**body)
        logger.info(f"Running renewal readiness crew for account: {req.accountId}")

        crew = RenewalReadinessCrew(user_id=req.userId)

        if stream:
            ctx = SimpleStreamingContext()

            async def generate():
                try:
                    yield ctx.init_message("Starting renewal readiness assessment...")
                    result = crew.run(
                        account_id=req.accountId,
                        contract_end_date=req.contractEndDate,
                        current_arr=req.currentArr,
                        user_id=req.userId,
                        step_callback=ctx.step_callback,
                        health_score_data=req.healthScoreData,
                        usage_data=req.usageData,
                        support_cases_data=req.supportCasesData,
                        engagement_gap_data=req.engagementGapData,
                        stakeholder_map_data=req.stakeholderMapData,
                    )
                    for msg in ctx.get_progress_messages():
                        yield msg
                    logger.info(f"Renewal readiness crew completed in {ctx.execution_time:.2f}s")
                    yield ctx.result_message(
                        result.get('result'),
                        account_name=result.get('account_name'),
                        contract_end_date=result.get('contract_end_date'),
                        current_arr=result.get('current_arr'),
                        provider=result.get('provider'),
                        model=result.get('model'),
                    )
                except Exception as e:
                    logger.error(f"Renewal readiness crew failed: {str(e)}")
                    yield ctx.error_message(str(e))

            return create_streaming_response(generate())
        else:
            start_time = datetime.utcnow()
            result = crew.run(
                account_id=req.accountId,
                contract_end_date=req.contractEndDate,
                current_arr=req.currentArr,
                user_id=req.userId,
                health_score_data=req.healthScoreData,
                usage_data=req.usageData,
                support_cases_data=req.supportCasesData,
                engagement_gap_data=req.engagementGapData,
                stakeholder_map_data=req.stakeholderMapData,
            )
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"Renewal readiness crew completed in {execution_time:.2f}s")
            return {
                "success": result.get("success", True),
                "result": result.get("result"),
                "account_name": result.get("account_name"),
                "contract_end_date": result.get("contract_end_date"),
                "current_arr": result.get("current_arr"),
                "provider": result.get("provider"),
                "model": result.get("model"),
                "execution_time": execution_time,
            }

    except Exception as e:
        logger.error(f"Renewal readiness crew failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Expansion Specialist Crew
# =============================================================================

@app.post("/api/crew/expansion-specialist")
async def run_expansion_specialist_crew(request: Request):
    """Identify and score expansion opportunities for an account."""
    stream = request.query_params.get("stream", "false").lower() == "true"

    try:
        body = await request.json()
        req = ExpansionSpecialistRequest(**body)
        logger.info(f"Running expansion specialist crew for account: {req.accountId}")

        crew = ExpansionSpecialistCrew(user_id=req.userId)

        if stream:
            ctx = SimpleStreamingContext()

            async def generate():
                try:
                    yield ctx.init_message("Starting expansion analysis...")
                    result = crew.run(
                        account_id=req.accountId,
                        current_arr=req.currentArr or 0,
                        user_id=req.userId,
                        step_callback=ctx.step_callback,
                        usage_data=req.usageData,
                        arr_history_data=req.arrHistoryData,
                        health_score_data=req.healthScoreData,
                        engagement_data=req.engagementData,
                        stakeholder_data=req.stakeholderData,
                    )
                    for msg in ctx.get_progress_messages():
                        yield msg
                    logger.info(f"Expansion specialist crew completed in {ctx.execution_time:.2f}s")
                    yield ctx.result_message(
                        result.get('result'),
                        account_name=result.get('account_name'),
                        account_tier=result.get('account_tier'),
                        current_arr=result.get('current_arr'),
                        provider=result.get('provider'),
                        model=result.get('model'),
                    )
                except Exception as e:
                    logger.error(f"Expansion specialist crew failed: {str(e)}")
                    yield ctx.error_message(str(e))

            return create_streaming_response(generate())
        else:
            start_time = datetime.utcnow()
            result = crew.run(
                account_id=req.accountId,
                current_arr=req.currentArr or 0,
                user_id=req.userId,
                usage_data=req.usageData,
                arr_history_data=req.arrHistoryData,
                health_score_data=req.healthScoreData,
                engagement_data=req.engagementData,
                stakeholder_data=req.stakeholderData,
            )
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"Expansion specialist crew completed in {execution_time:.2f}s")
            return {
                "success": result.get("success", True),
                "result": result.get("result"),
                "account_name": result.get("account_name"),
                "account_tier": result.get("account_tier"),
                "current_arr": result.get("current_arr"),
                "contract_end_date": result.get("contract_end_date"),
                "provider": result.get("provider"),
                "model": result.get("model"),
                "execution_time": execution_time,
            }

    except Exception as e:
        logger.error(f"Expansion specialist crew failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Strategic Action Crew
# =============================================================================

@app.post("/api/crew/strategic-action")
async def run_strategic_action_crew(request: Request):
    """Generate executive-ready strategic documents (board summaries, directives, deep dives)."""
    stream = request.query_params.get("stream", "false").lower() == "true"

    try:
        body = await request.json()
        req = StrategicActionRequest(**body)
        logger.info(f"Running strategic action crew: {req.actionType}")

        crew = StrategicActionCrew(user_id=req.userId)

        if stream:
            ctx = ThreadedStreamingContext()

            async def generate():
                yield ctx.init_message(f"Starting {req.actionType.replace('_', ' ')} generation...")

                async for msg in ctx.run_with_progress(
                    lambda step_cb: crew.run(
                        action_type=req.actionType,
                        user_id=req.userId,
                        segment=req.segment,
                        account_id=req.accountId,
                        quarter=req.quarter,
                        step_callback=step_cb,
                    )
                ):
                    yield msg

                if ctx.error:
                    logger.error(f"Strategic action crew failed: {ctx.error}")
                    yield ctx.error_message(ctx.error)
                elif ctx.result:
                    logger.info(f"Strategic action crew completed in {ctx.execution_time:.2f}s")
                    yield ctx.result_message(
                        {"document": ctx.result.get("document")},
                        action_type=ctx.result.get("action_type"),
                        quarter=ctx.result.get("quarter"),
                        segment=ctx.result.get("segment"),
                        provider=ctx.result.get("provider"),
                        model=ctx.result.get("model"),
                    )

            return create_streaming_response(generate())
        else:
            start_time = datetime.utcnow()
            result = crew.run(
                action_type=req.actionType,
                user_id=req.userId,
                segment=req.segment,
                account_id=req.accountId,
                quarter=req.quarter,
            )
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"Strategic action crew completed in {execution_time:.2f}s")
            return {
                "success": result.get("success", True),
                "document": result.get("document"),
                "action_type": result.get("action_type"),
                "quarter": result.get("quarter"),
                "segment": result.get("segment"),
                "provider": result.get("provider"),
                "model": result.get("model"),
                "execution_time": execution_time,
            }

    except Exception as e:
        logger.error(f"Strategic action crew failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Executive Morning Briefing Crew
# =============================================================================

@app.post("/api/crew/executive-briefing")
async def run_executive_briefing_crew(request: Request):
    """Generate executive morning briefing with portfolio synthesis."""
    stream = request.query_params.get("stream", "false").lower() == "true"

    try:
        body = await request.json()
        req = ExecutiveBriefingRequest(**body)
        logger.info("Running executive briefing crew")

        crew = ExecutiveMorningBriefingCrew(user_id=req.userId)

        if stream:
            ctx = ThreadedStreamingContext()

            async def generate():
                yield ctx.init_message("Starting executive briefing generation...")

                async for msg in ctx.run_with_progress(
                    lambda step_cb: crew.run(
                        user_id=req.userId,
                        step_callback=step_cb,
                    )
                ):
                    yield msg

                if ctx.error:
                    logger.error(f"Executive briefing crew failed: {ctx.error}")
                    yield ctx.error_message(ctx.error)
                elif ctx.result:
                    logger.info(f"Executive briefing crew completed in {ctx.execution_time:.2f}s")
                    yield ctx.result_message(
                        {
                            "headline": ctx.result.get("headline"),
                            "narrative": ctx.result.get("narrative"),
                            "key_risks": ctx.result.get("key_risks"),
                            "key_wins": ctx.result.get("key_wins"),
                            "recommended_actions": ctx.result.get("recommended_actions"),
                            "confidence_score": ctx.result.get("confidence_score"),
                            "data_summary": ctx.result.get("data_summary"),
                        },
                        provider=ctx.result.get("provider"),
                        model=ctx.result.get("model"),
                        generated_at=ctx.result.get("generated_at"),
                    )

            return create_streaming_response(generate())
        else:
            start_time = datetime.utcnow()
            result = crew.run(user_id=req.userId)
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"Executive briefing crew completed in {execution_time:.2f}s")
            return {
                "success": result.get("success", True),
                "headline": result.get("headline"),
                "narrative": result.get("narrative"),
                "key_risks": result.get("key_risks"),
                "key_wins": result.get("key_wins"),
                "recommended_actions": result.get("recommended_actions"),
                "confidence_score": result.get("confidence_score"),
                "data_summary": result.get("data_summary"),
                "provider": result.get("provider"),
                "model": result.get("model"),
                "generated_at": result.get("generated_at"),
                "execution_time": execution_time,
            }

    except Exception as e:
        logger.error(f"Executive briefing crew failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Contextual Drilldown Crew
# =============================================================================

@app.post("/api/crew/drilldown")
async def run_drilldown_crew(request: Request):
    """Generate instant drilldown synthesis for an account or metric."""
    stream = request.query_params.get("stream", "false").lower() == "true"

    try:
        body = await request.json()
        req = ContextualDrilldownRequest(**body)
        logger.info(f"Running drilldown crew: {req.entityType}/{req.entityId}")

        crew = ContextualDrilldownCrew(user_id=req.userId)

        if stream:
            ctx = ThreadedStreamingContext()

            async def generate():
                yield ctx.init_message(f"Starting {req.entityType} drilldown...")

                async for msg in ctx.run_with_progress(
                    lambda step_cb: crew.run(
                        entity_type=req.entityType,
                        entity_id=req.entityId,
                        context=req.context or "risk",
                        user_id=req.userId,
                        step_callback=step_cb,
                    )
                ):
                    yield msg

                if ctx.error:
                    logger.error(f"Drilldown crew failed: {ctx.error}")
                    yield ctx.error_message(ctx.error)
                elif ctx.result:
                    logger.info(f"Drilldown crew completed in {ctx.execution_time:.2f}s")
                    yield ctx.result_message(
                        {
                            "synthesis": ctx.result.get("synthesis"),
                            "bullets": ctx.result.get("bullets"),
                            "recommended_actions": ctx.result.get("recommended_actions"),
                            "related_meetings": ctx.result.get("related_meetings"),
                            "related_cases": ctx.result.get("related_cases"),
                        },
                        entity_type=ctx.result.get("entity_type"),
                        entity_id=ctx.result.get("entity_id"),
                        context=ctx.result.get("context"),
                        provider=ctx.result.get("provider"),
                        model=ctx.result.get("model"),
                    )

            return create_streaming_response(generate())
        else:
            start_time = datetime.utcnow()
            result = crew.run(
                entity_type=req.entityType,
                entity_id=req.entityId,
                context=req.context or "risk",
                user_id=req.userId,
            )
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"Drilldown crew completed in {execution_time:.2f}s")
            return {
                "success": result.get("success", True),
                "synthesis": result.get("synthesis"),
                "bullets": result.get("bullets"),
                "recommended_actions": result.get("recommended_actions"),
                "related_meetings": result.get("related_meetings"),
                "related_cases": result.get("related_cases"),
                "contributing_accounts": result.get("contributing_accounts"),
                "related_signals": result.get("related_signals"),
                "entity_type": result.get("entity_type"),
                "entity_id": result.get("entity_id"),
                "context": result.get("context"),
                "provider": result.get("provider"),
                "model": result.get("model"),
                "generated_at": result.get("generated_at"),
                "execution_time": execution_time,
            }

    except Exception as e:
        logger.error(f"Drilldown crew failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Custom Analysis Crew (User-created analyses)
# =============================================================================

@app.post("/api/crew/custom-analysis")
async def run_custom_analysis(request: CustomAnalysisRequest):
    """Run a custom user-created analysis with streaming progress."""
    from crewai import Agent, Task, Crew, Process, LLM

    ctx = ThreadedStreamingContext()

    async def generate():
        try:
            yield ctx.init_message(f"Starting analysis: {request.analysisName}")

            def run_crew(step_callback):
                context_text = _format_custom_context(request.context, request.targetType)
                llm = LLM(
                    model=os.environ.get("OPENAI_MODEL_NAME", "gpt-4o-mini"),
                    api_key=os.environ.get("OPENAI_API_KEY"),
                )
                step_callback("Creating analyst agent...")
                analyst = Agent(
                    role="Custom Analyst",
                    goal="Answer the user's analysis questions thoroughly and actionably",
                    backstory=request.expertise,
                    verbose=True,
                    allow_delegation=False,
                    llm=llm,
                )
                output_guidance = f"\n\nOutput format guidance:\n{request.outputFormat}" if request.outputFormat else ""
                task_description = f"""Analyze the following {request.targetType} data and answer these questions:

{request.questions}

=== CONTEXT DATA ===
{context_text}
{output_guidance}"""

                step_callback("Running analysis...")
                analysis_task = Task(
                    description=task_description,
                    expected_output="A comprehensive analysis answering all the questions with specific, actionable insights based on the provided data.",
                    agent=analyst,
                )
                crew = Crew(agents=[analyst], tasks=[analysis_task], process=Process.sequential, verbose=True)
                result = crew.kickoff()
                result_text = str(result) if result else "No result"
                step_callback(f"Completed in {ctx.execution_time:.1f}s")
                return {
                    "result": result_text,
                    "analysisId": request.analysisId,
                    "analysisName": request.analysisName,
                    "targetType": request.targetType,
                    "targetId": request.targetId,
                    "duration": ctx.execution_time,
                }

            async for msg in ctx.run_with_progress(run_crew):
                yield msg

            if ctx.error:
                logger.error(f"Custom analysis error: {ctx.error}")
                yield ctx.error_message()
            elif ctx.result:
                yield ctx.result_message(
                    ctx.result.get("result"),
                    analysisId=ctx.result.get("analysisId"),
                    analysisName=ctx.result.get("analysisName"),
                    targetType=ctx.result.get("targetType"),
                    targetId=ctx.result.get("targetId"),
                    duration=ctx.result.get("duration"),
                )

        except Exception as e:
            logger.error(f"Custom analysis error: {e}")
            import traceback
            traceback.print_exc()
            yield ctx.error_message(str(e))

    return create_streaming_response(generate())


def _format_custom_context(context: CustomAnalysisContext, target_type: str) -> str:
    """Format context data into a readable string for the LLM."""
    sections = []

    # Target entity
    if context.target:
        sections.append(f"=== TARGET {target_type.upper()} ===")
        sections.append(_format_dict(context.target))

    # Account info
    if context.accounts:
        sections.append("\n=== ACCOUNT INFO ===")
        for acc in context.accounts:
            sections.append(_format_dict(acc))

    # Opportunities
    if context.opportunities:
        sections.append(f"\n=== OPPORTUNITIES ({len(context.opportunities)}) ===")
        for opp in context.opportunities:
            sections.append(f"\n--- {opp.get('name', 'Unnamed')} ---")
            sections.append(_format_dict(opp))

    # Meetings/Transcripts
    if context.meetings:
        sections.append(f"\n=== MEETING TRANSCRIPTS ({len(context.meetings)}) ===")
        for meeting in context.meetings:
            sections.append(f"\n--- {meeting.get('subject', 'Meeting')} ({meeting.get('date', 'Unknown date')}) ---")
            transcript = meeting.get('transcript', meeting.get('text', ''))
            # Truncate very long transcripts
            if len(transcript) > 15000:
                transcript = transcript[:15000] + "\n... [truncated]"
            sections.append(transcript)

    # Support cases
    if context.cases:
        sections.append(f"\n=== SUPPORT CASES ({len(context.cases)}) ===")
        for case in context.cases:
            sections.append(f"\n--- Case: {case.get('subject', 'No subject')} ---")
            sections.append(_format_dict(case))

    # Contacts
    if context.contacts:
        sections.append(f"\n=== CONTACTS ({len(context.contacts)}) ===")
        for contact in context.contacts:
            name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
            title = contact.get('title', 'No title')
            email = contact.get('email', '')
            sections.append(f"- {name} ({title}) - {email}")

    return "\n".join(sections) if sections else "No context data available."


def _format_dict(d: Dict[str, Any], indent: int = 0) -> str:
    """Format a dictionary for readable display, excluding null values."""
    lines = []
    prefix = "  " * indent
    for key, value in d.items():
        if value is None or value == "" or value == []:
            continue
        if isinstance(value, dict):
            lines.append(f"{prefix}{key}:")
            lines.append(_format_dict(value, indent + 1))
        elif isinstance(value, list) and len(value) > 0:
            if isinstance(value[0], dict):
                lines.append(f"{prefix}{key}: [{len(value)} items]")
            else:
                lines.append(f"{prefix}{key}: {value}")
        else:
            lines.append(f"{prefix}{key}: {value}")
    return "\n".join(lines)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
