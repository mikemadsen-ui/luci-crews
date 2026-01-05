"""
LUCI CrewAI Service - FastAPI Application

Provides API endpoints for running CrewAI crews and serves the CrewAI Studio UI.
"""

import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from .crews.sales_pipeline_crew import SalesPipelineCrew
from .crews.account_health_crew import AccountHealthCrew
from .crews.implementation_crew import ImplementationCrew
from .crews.sentiment_crew import SentimentCrew
from .crews.project_sentiment_crew import ProjectSentimentCrew
from .crews.opportunity_strategy_crew import OpportunityStrategyCrew
from .crews.support_coaching_crew import SupportCoachingCrew
from .crews.support_resolution_crew import SupportResolutionCrew
from .crews.sc_prep_crew import SCPrepCrew
from .crews.pm_coaching_crew import PMCoachingCrew
from . import config_store

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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


# =============================================================================
# Request/Response Models
# =============================================================================

class SalesPipelineRequest(BaseModel):
    user_id: str
    user_email: str
    opportunities: list = []
    summary: Optional[dict] = None


class AccountHealthRequest(BaseModel):
    account_id: str
    account_name: str
    account_tier: Optional[str] = None
    arr: Optional[float] = None
    activity_data: Optional[str] = None
    support_data: Optional[str] = None
    engagement_data: Optional[str] = None


class ImplementationRequest(BaseModel):
    project_id: str
    project_name: str
    account_name: str
    project_status: Optional[str] = None
    start_date: Optional[str] = None
    target_go_live: Optional[str] = None
    completion_pct: Optional[float] = None
    hours_used: Optional[float] = None
    hours_budgeted: Optional[float] = None
    budget_used: Optional[float] = None
    budget_total: Optional[float] = None
    milestones_data: Optional[str] = None
    risks_data: Optional[str] = None
    callActivity: Optional[dict] = None  # Past Avoma calls + upcoming calendar events


class SentimentRequest(BaseModel):
    account_id: str
    account_name: str
    communications_data: Optional[str] = None
    support_data: Optional[str] = None
    meeting_notes: Optional[str] = None


class ProjectSentimentRequest(BaseModel):
    userId: str
    salesforceAccountId: str
    salesforceProjectId: str
    transcriptionIds: Optional[List[str]] = None
    forceRefresh: Optional[bool] = False
    userEmail: Optional[str] = None


class OpportunityDataModel(BaseModel):
    """Opportunity data passed from Next.js to avoid refetching."""
    id: Optional[str] = None
    salesforce_id: Optional[str] = None
    name: Optional[str] = None
    amount: Optional[float] = None
    stage_name: Optional[str] = None
    probability: Optional[int] = None
    close_date: Optional[str] = None
    type: Optional[str] = None
    lead_source: Optional[str] = None
    next_step: Optional[str] = None
    description: Optional[str] = None
    is_won: Optional[bool] = None
    is_closed: Optional[bool] = None
    owner_name: Optional[str] = None
    owner_email: Optional[str] = None
    fiscal_quarter: Optional[int] = None
    fiscal_year: Optional[int] = None
    salesforce_account_id: Optional[str] = None
    account_name: Optional[str] = None
    account_industry: Optional[str] = None
    account_tier: Optional[str] = None


class TranscriptionDataModel(BaseModel):
    """Transcription data passed from Next.js."""
    id: str
    subject: Optional[str] = None
    date: Optional[str] = None
    text: Optional[str] = None


class OpportunityStrategyRequest(BaseModel):
    opportunityId: str
    userId: Optional[str] = None
    userEmail: Optional[str] = None
    forceRefresh: Optional[bool] = False
    opportunityData: Optional[OpportunityDataModel] = None
    transcriptionIds: Optional[List[str]] = None
    transcriptionData: Optional[List[TranscriptionDataModel]] = None
    salesforceAccountId: Optional[str] = None


class CaseDataModel(BaseModel):
    """Case data passed from Next.js."""
    case_number: Optional[str] = None
    subject: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    type: Optional[str] = None
    account_name: Optional[str] = None
    created_date: Optional[str] = None
    closed_date: Optional[str] = None
    description: Optional[str] = None


class SupportCoachingRequest(BaseModel):
    agentName: str
    agentEmail: str
    ownerId: str
    casesData: Optional[List[CaseDataModel]] = None
    daysBack: Optional[int] = 90


class PMCoachingRequest(BaseModel):
    """Request model for Implementation Consultant (PM) coaching analysis."""
    pmName: str
    pmEmail: str
    salesforceOwnerId: Optional[str] = None
    projectsData: Optional[List[Dict[str, Any]]] = None
    deliveryMetrics: Optional[Dict[str, Any]] = None
    sentimentData: Optional[List[Dict[str, Any]]] = None
    transcriptionSamples: Optional[List[Dict[str, Any]]] = None
    escalationData: Optional[List[Dict[str, Any]]] = None
    daysBack: Optional[int] = 365


class SupportResolutionRequest(BaseModel):
    caseSubject: str
    caseDescription: Optional[str] = None
    caseType: Optional[str] = None
    casePriority: Optional[str] = None
    accountName: Optional[str] = None
    contactName: Optional[str] = None
    userId: Optional[str] = None
    salesforceUserId: Optional[str] = None
    caseNumber: Optional[str] = None


class SCPrepRequest(BaseModel):
    opportunityId: str
    prepType: Optional[str] = "full"  # "discovery", "demo", "competitive", "full"
    userId: Optional[str] = None
    userEmail: Optional[str] = None
    forceRefresh: Optional[bool] = False
    opportunityData: Optional[OpportunityDataModel] = None
    transcriptionData: Optional[List[TranscriptionDataModel]] = None


class CrewResponse(BaseModel):
    success: bool
    job_id: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None
    execution_time: Optional[float] = None


# =============================================================================
# Health Check
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint for Railway."""
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "0.1.0",
        "supabase_configured": bool(supabase_url and supabase_key),
        "supabase_url": supabase_url[:30] + "..." if supabase_url else None,
    }


@app.get("/")
async def root():
    """Root endpoint with service info."""
    return {
        "service": "LUCI CrewAI Service",
        "version": "0.1.0",
        "endpoints": {
            "health": "/health",
            "config_agents": "/api/config/agents",
            "config_tasks": "/api/config/tasks",
            "sales_pipeline": "/api/crew/sales_pipeline",
            "account_health": "/api/crew/account",
            "implementation": "/api/crew/implementation",
            "sentiment": "/api/crew/sentiment",
            "project_sentiment": "/api/crew/project-sentiment",
            "opportunity": "/api/crew/opportunity",
            "support_coaching": "/api/crew/support-coaching",
            "support_resolution": "/api/crew/support_resolution",
            "support_training": "/api/crew/support_training",
            "sc_prep": "/api/crew/sc-prep",
            "pm_coaching": "/api/crew/pm-coaching",
        },
        "docs": "/docs",
    }


# =============================================================================
# Crew Endpoints
# =============================================================================

@app.post("/api/crew/sales_pipeline", response_model=CrewResponse)
async def run_sales_pipeline_crew(request: SalesPipelineRequest):
    """Run the sales pipeline analysis crew."""
    start_time = datetime.utcnow()

    try:
        logger.info(f"Running sales pipeline crew for user: {request.user_email}")

        crew = SalesPipelineCrew()
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
        logger.info(f"Running account health crew for: {request.account_name}")

        crew = AccountHealthCrew()
        result = crew.run(
            account_name=request.account_name,
            account_tier=request.account_tier,
            arr=request.arr,
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


@app.post("/api/crew/implementation", response_model=CrewResponse)
async def run_implementation_crew(request: ImplementationRequest):
    """Run the implementation project analysis crew."""
    start_time = datetime.utcnow()

    try:
        logger.info(f"Running implementation crew for: {request.project_name}")
        if request.callActivity:
            metrics = request.callActivity.get("metrics", {})
            logger.info(f"Call activity: {metrics.get('totalRecentCalls', 0)} past calls, {metrics.get('upcomingCallsCount', 0)} upcoming")

        crew = ImplementationCrew()
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
    """Run the sentiment analysis crew."""
    start_time = datetime.utcnow()

    try:
        logger.info(f"Running sentiment crew for: {request.account_name}")

        crew = SentimentCrew()
        result = crew.run(
            account_name=request.account_name,
            communications_data=request.communications_data,
            support_data=request.support_data,
            meeting_notes=request.meeting_notes,
        )

        execution_time = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"Sentiment crew completed in {execution_time:.2f}s")

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


@app.post("/api/crew/project-sentiment")
async def run_project_sentiment_crew(request: Request):
    """Run the project sentiment analysis crew with optional streaming."""
    import json
    start_time = datetime.utcnow()

    # Check for streaming parameter
    stream = request.query_params.get("stream", "false").lower() == "true"

    try:
        body = await request.json()
        req = ProjectSentimentRequest(**body)

        logger.info(f"Running project sentiment crew for project: {req.salesforceProjectId}")

        crew = ProjectSentimentCrew()

        if stream:
            # Streaming response
            async def generate():
                progress_messages = []

                def step_callback(message: str):
                    progress_messages.append(message)

                try:
                    # Send initial progress
                    yield f"data: {json.dumps({'type': 'progress', 'stage': 'init', 'message': 'Starting analysis...'})}\n\n"

                    # Run the crew (synchronous, but we'll send progress)
                    result = crew.run(
                        salesforce_project_id=req.salesforceProjectId,
                        salesforce_account_id=req.salesforceAccountId,
                        transcription_ids=req.transcriptionIds or [],
                        force_refresh=req.forceRefresh or False,
                        step_callback=step_callback,
                    )

                    # Send any progress messages
                    for msg in progress_messages:
                        yield f"data: {json.dumps({'type': 'progress', 'stage': 'processing', 'message': msg})}\n\n"

                    execution_time = (datetime.utcnow() - start_time).total_seconds()
                    logger.info(f"Project sentiment crew completed in {execution_time:.2f}s")

                    # Send the final result
                    yield f"data: {json.dumps({'type': 'result', 'result': result, 'input_hash': result.get('input_hash'), 'transcription_count': result.get('transcription_count'), 'transcription_length': result.get('transcription_length'), 'transcription_ids': result.get('transcription_ids'), 'provider': result.get('provider'), 'model': result.get('model')})}\n\n"

                except Exception as e:
                    logger.error(f"Project sentiment crew failed: {str(e)}")
                    yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                }
            )
        else:
            # Non-streaming response
            result = crew.run(
                salesforce_project_id=req.salesforceProjectId,
                salesforce_account_id=req.salesforceAccountId,
                transcription_ids=req.transcriptionIds or [],
                force_refresh=req.forceRefresh or False,
            )

            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"Project sentiment crew completed in {execution_time:.2f}s")

            return {
                "success": True,
                "result": result.get("result"),
                "input_hash": result.get("input_hash"),
                "transcription_count": result.get("transcription_count"),
                "transcription_length": result.get("transcription_length"),
                "transcription_ids": result.get("transcription_ids"),
                "provider": result.get("provider"),
                "model": result.get("model"),
                "execution_time": execution_time,
            }

    except Exception as e:
        logger.error(f"Project sentiment crew failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/crew/opportunity")
async def run_opportunity_strategy_crew(request: Request):
    """Run the opportunity strategy analysis crew with optional streaming."""
    import json
    start_time = datetime.utcnow()

    # Check for streaming parameter
    stream = request.query_params.get("stream", "false").lower() == "true"

    try:
        body = await request.json()
        req = OpportunityStrategyRequest(**body)

        logger.info(f"Running opportunity strategy crew for: {req.opportunityId}")

        crew = OpportunityStrategyCrew()

        if stream:
            async def generate():
                progress_messages = []

                def step_callback(message: str):
                    progress_messages.append(message)

                try:
                    yield f"data: {json.dumps({'type': 'progress', 'stage': 'init', 'message': 'Starting strategic analysis...'})}\n\n"

                    result = crew.run(
                        opportunity_id=req.opportunityId,
                        user_id=req.userId,
                        force_refresh=req.forceRefresh or False,
                        step_callback=step_callback,
                        opportunity_data=req.opportunityData.model_dump() if req.opportunityData else None,
                        transcription_data=[t.model_dump() for t in req.transcriptionData] if req.transcriptionData else None,
                        salesforce_account_id=req.salesforceAccountId,
                    )

                    for msg in progress_messages:
                        yield f"data: {json.dumps({'type': 'progress', 'stage': 'processing', 'message': msg})}\n\n"

                    execution_time = (datetime.utcnow() - start_time).total_seconds()
                    logger.info(f"Opportunity strategy crew completed in {execution_time:.2f}s")

                    yield f"data: {json.dumps({'type': 'result', 'result': result.get('result'), 'input_hash': result.get('input_hash'), 'opportunity_name': result.get('opportunity_name'), 'account_name': result.get('account_name'), 'provider': result.get('provider'), 'model': result.get('model')})}\n\n"

                except Exception as e:
                    logger.error(f"Opportunity strategy crew failed: {str(e)}")
                    yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                }
            )
        else:
            result = crew.run(
                opportunity_id=req.opportunityId,
                user_id=req.userId,
                force_refresh=req.forceRefresh or False,
                opportunity_data=req.opportunityData.model_dump() if req.opportunityData else None,
                transcription_data=[t.model_dump() for t in req.transcriptionData] if req.transcriptionData else None,
                salesforce_account_id=req.salesforceAccountId,
            )

            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"Opportunity strategy crew completed in {execution_time:.2f}s")

            return {
                "success": True,
                "result": result.get("result"),
                "input_hash": result.get("input_hash"),
                "opportunity_name": result.get("opportunity_name"),
                "account_name": result.get("account_name"),
                "provider": result.get("provider"),
                "model": result.get("model"),
                "execution_time": execution_time,
            }

    except Exception as e:
        logger.error(f"Opportunity strategy crew failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/crew/support-coaching")
async def run_support_coaching_crew(request: Request):
    """Run the support agent coaching analysis crew with optional streaming."""
    import json
    start_time = datetime.utcnow()

    # Check for streaming parameter
    stream = request.query_params.get("stream", "false").lower() == "true"

    try:
        body = await request.json()
        req = SupportCoachingRequest(**body)

        logger.info(f"Running support coaching crew for agent: {req.agentName} ({req.agentEmail})")

        crew = SupportCoachingCrew()

        # Convert cases data to dict format if provided
        cases_data = None
        if req.casesData:
            cases_data = [c.model_dump() for c in req.casesData]

        if stream:
            async def generate():
                progress_messages = []

                def step_callback(message: str):
                    progress_messages.append(message)

                try:
                    yield f"data: {json.dumps({'type': 'progress', 'stage': 'init', 'message': 'Starting coaching analysis...'})}\n\n"

                    result = crew.run(
                        agent_name=req.agentName,
                        agent_email=req.agentEmail,
                        owner_id=req.ownerId,
                        cases_data=cases_data,
                        days_back=req.daysBack or 90,
                        step_callback=step_callback,
                    )

                    for msg in progress_messages:
                        yield f"data: {json.dumps({'type': 'progress', 'stage': 'processing', 'message': msg})}\n\n"

                    execution_time = (datetime.utcnow() - start_time).total_seconds()
                    logger.info(f"Support coaching crew completed in {execution_time:.2f}s")

                    yield f"data: {json.dumps({'type': 'result', 'result': result})}\n\n"

                except Exception as e:
                    logger.error(f"Support coaching crew failed: {str(e)}")
                    yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                }
            )
        else:
            result = crew.run(
                agent_name=req.agentName,
                agent_email=req.agentEmail,
                owner_id=req.ownerId,
                cases_data=cases_data,
                days_back=req.daysBack or 90,
            )

            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"Support coaching crew completed in {execution_time:.2f}s")

            return {
                "success": True,
                "result": result.get("analysis"),
                "agent_name": result.get("agent_name"),
                "agent_email": result.get("agent_email"),
                "cases_analyzed": result.get("cases_analyzed"),
                "days_back": result.get("days_back"),
                "execution_time": execution_time,
            }

    except Exception as e:
        logger.error(f"Support coaching crew failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/crew/pm-coaching")
async def run_pm_coaching_crew(request: Request):
    """Run the Implementation Consultant (PM) coaching analysis crew with optional streaming."""
    import json
    start_time = datetime.utcnow()

    stream = request.query_params.get("stream", "false").lower() == "true"

    try:
        body = await request.json()
        req = PMCoachingRequest(**body)

        logger.info(f"Running PM coaching crew for: {req.pmName} ({req.pmEmail})")

        crew = PMCoachingCrew()

        if stream:
            async def generate():
                progress_messages = []

                def step_callback(message: str):
                    progress_messages.append(message)

                try:
                    yield f"data: {json.dumps({'type': 'progress', 'stage': 'init', 'message': 'Starting coaching analysis...'})}\n\n"

                    result = crew.run(
                        pm_name=req.pmName,
                        pm_email=req.pmEmail,
                        salesforce_owner_id=req.salesforceOwnerId,
                        projects_data=req.projectsData,
                        delivery_metrics=req.deliveryMetrics,
                        sentiment_data=req.sentimentData,
                        transcription_samples=req.transcriptionSamples,
                        escalation_data=req.escalationData,
                        days_back=req.daysBack or 365,
                        step_callback=step_callback,
                    )

                    for msg in progress_messages:
                        yield f"data: {json.dumps({'type': 'progress', 'stage': 'processing', 'message': msg})}\n\n"

                    execution_time = (datetime.utcnow() - start_time).total_seconds()
                    logger.info(f"PM coaching crew completed in {execution_time:.2f}s")

                    yield f"data: {json.dumps({'type': 'result', 'result': result.get('result'), 'pm_name': result.get('pm_name'), 'pm_email': result.get('pm_email'), 'projects_analyzed': result.get('projects_analyzed'), 'provider': result.get('provider'), 'model': result.get('model')})}\n\n"

                except Exception as e:
                    logger.error(f"PM coaching crew failed: {str(e)}")
                    yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                }
            )
        else:
            result = crew.run(
                pm_name=req.pmName,
                pm_email=req.pmEmail,
                salesforce_owner_id=req.salesforceOwnerId,
                projects_data=req.projectsData,
                delivery_metrics=req.deliveryMetrics,
                sentiment_data=req.sentimentData,
                transcription_samples=req.transcriptionSamples,
                escalation_data=req.escalationData,
                days_back=req.daysBack or 365,
            )

            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"PM coaching crew completed in {execution_time:.2f}s")

            return {
                "success": True,
                "result": result.get("result"),
                "pm_name": result.get("pm_name"),
                "pm_email": result.get("pm_email"),
                "projects_analyzed": result.get("projects_analyzed"),
                "provider": result.get("provider"),
                "model": result.get("model"),
                "execution_time": execution_time,
            }

    except Exception as e:
        logger.error(f"PM coaching crew failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/crew/support_resolution")
async def run_support_resolution_crew(request: Request):
    """Run the support resolution analysis crew with optional streaming."""
    import json
    start_time = datetime.utcnow()

    stream = request.query_params.get("stream", "false").lower() == "true"

    try:
        body = await request.json()
        req = SupportResolutionRequest(**body)

        logger.info(f"Running support resolution crew for case: {req.caseSubject[:50] if req.caseSubject else 'Unknown'}...")

        crew = SupportResolutionCrew()

        if stream:
            async def generate():
                progress_messages = []

                def step_callback(message: str):
                    progress_messages.append(message)

                try:
                    yield f"data: {json.dumps({'type': 'progress', 'stage': 'init', 'message': 'Analyzing case...'})}\n\n"

                    result = crew.run(
                        case_subject=req.caseSubject,
                        case_description=req.caseDescription,
                        case_type=req.caseType,
                        case_priority=req.casePriority,
                        account_name=req.accountName,
                        contact_name=req.contactName,
                        step_callback=step_callback,
                    )

                    for msg in progress_messages:
                        yield f"data: {json.dumps({'type': 'progress', 'stage': 'processing', 'message': msg})}\n\n"

                    execution_time = (datetime.utcnow() - start_time).total_seconds()
                    logger.info(f"Support resolution crew completed in {execution_time:.2f}s")

                    yield f"data: {json.dumps({'type': 'result', 'result': result.get('result')})}\n\n"

                except Exception as e:
                    logger.error(f"Support resolution crew failed: {str(e)}")
                    yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                }
            )
        else:
            result = crew.run(
                case_subject=req.caseSubject,
                case_description=req.caseDescription,
                case_type=req.caseType,
                case_priority=req.casePriority,
                account_name=req.accountName,
                contact_name=req.contactName,
            )

            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"Support resolution crew completed in {execution_time:.2f}s")

            return {
                "success": True,
                "result": result.get("result"),
                "execution_time": execution_time,
            }

    except Exception as e:
        logger.error(f"Support resolution crew failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/crew/support_training")
async def run_support_training_crew(request: Request):
    """Alias for support_resolution - provides case analysis for training purposes."""
    return await run_support_resolution_crew(request)


@app.post("/api/crew/sc-prep")
async def run_sc_prep_crew(request: Request):
    """Run the SC preparation crew for discovery synthesis, demo prep, and competitive intel."""
    import json
    start_time = datetime.utcnow()

    stream = request.query_params.get("stream", "false").lower() == "true"

    try:
        body = await request.json()
        req = SCPrepRequest(**body)

        logger.info(f"Running SC prep crew for opportunity: {req.opportunityId} (type: {req.prepType})")

        crew = SCPrepCrew()

        if stream:
            async def generate():
                progress_messages = []

                def step_callback(message: str):
                    progress_messages.append(message)

                try:
                    yield f"data: {json.dumps({'type': 'progress', 'stage': 'init', 'message': 'Starting SC preparation...'})}\n\n"

                    result = crew.run(
                        opportunity_id=req.opportunityId,
                        prep_type=req.prepType or "full",
                        user_id=req.userId,
                        force_refresh=req.forceRefresh or False,
                        step_callback=step_callback,
                        opportunity_data=req.opportunityData.model_dump() if req.opportunityData else None,
                        transcription_data=[t.model_dump() for t in req.transcriptionData] if req.transcriptionData else None,
                    )

                    for msg in progress_messages:
                        yield f"data: {json.dumps({'type': 'progress', 'stage': 'processing', 'message': msg})}\n\n"

                    execution_time = (datetime.utcnow() - start_time).total_seconds()
                    logger.info(f"SC prep crew completed in {execution_time:.2f}s")

                    yield f"data: {json.dumps({'type': 'result', 'result': result.get('result'), 'input_hash': result.get('input_hash'), 'opportunity_name': result.get('opportunity_name'), 'account_name': result.get('account_name'), 'prep_type': result.get('prep_type'), 'provider': result.get('provider'), 'model': result.get('model')})}\n\n"

                except Exception as e:
                    logger.error(f"SC prep crew failed: {str(e)}")
                    yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                }
            )
        else:
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
                "success": True,
                "result": result.get("result"),
                "input_hash": result.get("input_hash"),
                "opportunity_name": result.get("opportunity_name"),
                "account_name": result.get("account_name"),
                "prep_type": result.get("prep_type"),
                "provider": result.get("provider"),
                "model": result.get("model"),
                "execution_time": execution_time,
            }

    except Exception as e:
        logger.error(f"SC prep crew failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Configuration Endpoints (Crew Studio Integration)
# Uses Supabase for persistent storage with YAML defaults
# =============================================================================

class ConfigUpdateRequest(BaseModel):
    role: Optional[str] = None
    goal: Optional[str] = None
    backstory: Optional[str] = None
    verbose: Optional[bool] = None
    allow_delegation: Optional[bool] = None
    description: Optional[str] = None
    expected_output: Optional[str] = None
    agent: Optional[str] = None
    context: Optional[str] = None  # Page context for Crew Studio (e.g., 'sales', 'account', 'implementation')


@app.get("/api/config/agents")
async def get_agents_config():
    """Get all agent configurations (YAML defaults + DB overrides)."""
    try:
        agents = config_store.get_agents()
        return {"agents": agents}
    except Exception as e:
        logger.error(f"Error getting agents config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/config/agents/{agent_name}")
async def get_agent_config(agent_name: str):
    """Get a specific agent configuration."""
    try:
        agent = config_store.get_agent(agent_name)
        if agent is None:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
        return {"agent": agent, "name": agent_name}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting agent '{agent_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/config/agents/{agent_name}")
async def update_agent_config(agent_name: str, config: ConfigUpdateRequest):
    """Update an agent configuration (persists to Supabase)."""
    try:
        # Convert to dict, removing None values
        config_dict = {k: v for k, v in config.dict().items() if v is not None}

        if not config_dict:
            raise HTTPException(status_code=400, detail="No configuration provided")

        result = config_store.update_agent(agent_name, config_dict)

        if result.get("success"):
            logger.info(f"Updated agent '{agent_name}'")
            return {"success": True, "agent": result.get("agent"), "name": agent_name}
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to update"))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating agent '{agent_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/config/agents/{agent_name}")
async def reset_agent_config(agent_name: str):
    """Reset an agent to its YAML defaults (removes DB overrides)."""
    try:
        result = config_store.reset_agent(agent_name)

        if result.get("success"):
            logger.info(f"Reset agent '{agent_name}' to defaults")
            return {"success": True, "agent": result.get("agent"), "name": agent_name}
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to reset"))

    except Exception as e:
        logger.error(f"Error resetting agent '{agent_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/config/tasks")
async def get_tasks_config():
    """Get all task configurations (YAML defaults + DB overrides)."""
    try:
        tasks = config_store.get_tasks()
        return {"tasks": tasks}
    except Exception as e:
        logger.error(f"Error getting tasks config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/config/tasks/{task_name}")
async def get_task_config(task_name: str):
    """Get a specific task configuration."""
    try:
        task = config_store.get_task(task_name)
        if task is None:
            raise HTTPException(status_code=404, detail=f"Task '{task_name}' not found")
        return {"task": task, "name": task_name}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting task '{task_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/config/tasks/{task_name}")
async def update_task_config(task_name: str, config: ConfigUpdateRequest):
    """Update a task configuration (persists to Supabase)."""
    try:
        # Convert to dict, removing None values
        config_dict = {k: v for k, v in config.dict().items() if v is not None}

        if not config_dict:
            raise HTTPException(status_code=400, detail="No configuration provided")

        result = config_store.update_task(task_name, config_dict)

        if result.get("success"):
            logger.info(f"Updated task '{task_name}'")
            return {"success": True, "task": result.get("task"), "name": task_name}
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to update"))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating task '{task_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/config/tasks/{task_name}")
async def reset_task_config(task_name: str):
    """Reset a task to its YAML defaults (removes DB overrides)."""
    try:
        result = config_store.reset_task(task_name)

        if result.get("success"):
            logger.info(f"Reset task '{task_name}' to defaults")
            return {"success": True, "task": result.get("task"), "name": task_name}
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to reset"))

    except Exception as e:
        logger.error(f"Error resetting task '{task_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
