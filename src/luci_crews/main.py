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
from .crews.ae_coaching_crew import AECoachingCrew
from .crews.csm_coaching_crew import CSMCoachingCrew
from .crews.sc_coaching_crew import SCCoachingCrew
from .crews.competitive_crew import CompetitiveCrew
from .crews.feature_extraction_crew import FeatureExtractionCrew
from .crews.project_analysis_crew import ProjectAnalysisCrew
from .crews.agenda_generation_crew import AgendaGenerationCrew
from .crews.call_verification_crew import CallVerificationCrew
from .crews.call_analysis_crew import CallAnalysisCrew
from .crews.account_analysis_crew import AccountAnalysisCrew
from . import config_store
from .batch_router import router as batch_router

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

# Register batch processing router for overnight sync jobs
app.include_router(batch_router)


# =============================================================================
# Request/Response Models
# =============================================================================

class SalesPipelineRequest(BaseModel):
    user_id: str
    user_email: str
    opportunities: list = []
    summary: Optional[dict] = None


class AccountHealthRequest(BaseModel):
    """Request model for account health analysis."""
    accountId: Optional[str] = None
    salesforceAccountId: Optional[str] = None
    userId: Optional[str] = None
    userEmail: Optional[str] = None
    # Legacy fields for backwards compatibility
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    account_tier: Optional[str] = None
    arr: Optional[float] = None
    activity_data: Optional[str] = None
    support_data: Optional[str] = None
    engagement_data: Optional[str] = None


class AccountAnalysisRequest(BaseModel):
    """Request model for unified account analysis (sentiment + health)."""
    accountId: Optional[str] = None
    salesforceAccountId: Optional[str] = None
    userId: Optional[str] = None
    userEmail: Optional[str] = None
    accountName: Optional[str] = None
    accountTier: Optional[str] = None
    arr: Optional[float] = None
    transcription: Optional[str] = None
    salesforceContext: Optional[Dict[str, Any]] = None
    engagementData: Optional[Dict[str, Any]] = None


class MavenlinkTaskModel(BaseModel):
    """Model for Mavenlink story/task data."""
    id: str
    title: Optional[str] = None
    description: Optional[str] = None
    story_type: Optional[str] = None  # task, deliverable, milestone, or issue
    status: Optional[str] = None
    start_date: Optional[str] = None
    due_date: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    position: Optional[int] = None
    assignee_ids: Optional[List[str]] = []
    assignee_names: Optional[List[str]] = []
    has_assignee: Optional[bool] = False
    is_client_task: Optional[bool] = False
    tags: Optional[List[str]] = []


class ImplementationRequest(BaseModel):
    project_id: str
    project_name: str
    account_name: str
    userId: Optional[str] = None  # For management-level AI settings
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
    mavenlinkTasks: Optional[List[dict]] = None  # Mavenlink stories/tasks with assignee info


class SentimentRequest(BaseModel):
    """Request model for account sentiment analysis."""
    userId: Optional[str] = None
    accountId: Optional[str] = None
    salesforceAccountId: Optional[str] = None
    userEmail: Optional[str] = None
    transcription: Optional[str] = None
    salesforceContext: Optional[Dict[str, Any]] = None
    customerIdentifier: Optional[str] = None


class ProjectSentimentRequest(BaseModel):
    userId: str
    salesforceAccountId: str
    salesforceProjectId: str
    transcriptionIds: Optional[List[str]] = None
    forceRefresh: Optional[bool] = False
    userEmail: Optional[str] = None


class ProjectAnalysisRequest(BaseModel):
    """Request model for unified project analysis crew."""
    salesforceProjectId: str
    userId: Optional[str] = None
    userEmail: Optional[str] = None
    forceRefresh: Optional[bool] = False
    # All data is passed from Next.js to avoid refetching
    project: Optional[Dict[str, Any]] = None
    projectOwner: Optional[Dict[str, Any]] = None
    mavenlinkTasks: Optional[List[Dict[str, Any]]] = None
    mavenlinkTimeEntries: Optional[List[Dict[str, Any]]] = None
    transcripts: Optional[List[Dict[str, Any]]] = None
    callActivity: Optional[Dict[str, Any]] = None
    emailActivity: Optional[Dict[str, Any]] = None


class OpportunityDataModel(BaseModel):
    """Opportunity data passed from Next.js to avoid refetching."""
    id: Optional[str] = None
    salesforce_id: Optional[str] = None
    name: Optional[str] = None
    amount: Optional[float] = None
    stage_name: Optional[str] = None
    probability: Optional[int] = None
    close_date: Optional[str] = None
    created_date: Optional[str] = None  # When the opportunity was created
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
    customer_start_date: Optional[str] = None  # When the account became a customer


class TranscriptionDataModel(BaseModel):
    """Transcription data passed from Next.js."""
    id: str
    subject: Optional[str] = None
    date: Optional[str] = None
    text: Optional[str] = None
    is_presales: Optional[bool] = None  # True if this call was before the customer start date


class PresalesContextModel(BaseModel):
    """Context about the presales nature of the opportunity."""
    presalesCount: Optional[int] = 0  # Number of presales calls found
    postsaleCount: Optional[int] = 0  # Number of post-sale calls found
    customerStartDate: Optional[str] = None  # When the account became a customer
    isExistingCustomer: Optional[bool] = False  # Whether the account is already a customer


class OpportunityStrategyRequest(BaseModel):
    opportunityId: str
    userId: Optional[str] = None
    userEmail: Optional[str] = None
    forceRefresh: Optional[bool] = False
    opportunityData: Optional[OpportunityDataModel] = None
    transcriptionIds: Optional[List[str]] = None
    transcriptionData: Optional[List[TranscriptionDataModel]] = None
    salesforceAccountId: Optional[str] = None
    presalesContext: Optional[PresalesContextModel] = None  # Context about presales calls


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
    ownerId: Optional[str] = None  # Optional - needed to fetch cases from DB, but not if casesData provided
    userId: Optional[str] = None  # For management-level AI settings
    casesData: Optional[List[CaseDataModel]] = None
    daysBack: Optional[int] = 90


class PMCoachingRequest(BaseModel):
    """Request model for Implementation Consultant (PM) coaching analysis."""
    pmName: str
    pmEmail: str
    salesforceOwnerId: Optional[str] = None
    userId: Optional[str] = None  # For management-level AI settings
    projectsData: Optional[List[Dict[str, Any]]] = None
    deliveryMetrics: Optional[Dict[str, Any]] = None
    sentimentData: Optional[List[Dict[str, Any]]] = None
    transcriptionSamples: Optional[List[Dict[str, Any]]] = None
    escalationData: Optional[List[Dict[str, Any]]] = None
    agendaMetrics: Optional[Dict[str, Any]] = None  # Call agenda completion patterns
    daysBack: Optional[int] = 365


class AECoachingRequest(BaseModel):
    """Request model for Account Executive coaching analysis."""
    aeName: str
    aeEmail: str
    salesforceOwnerId: Optional[str] = None
    userId: Optional[str] = None  # For management-level AI settings
    opportunitiesData: Optional[List[Dict[str, Any]]] = None
    transcriptionSamples: Optional[List[Dict[str, Any]]] = None
    daysBack: Optional[int] = 180


class CSMCoachingRequest(BaseModel):
    """Request model for Customer Success Manager coaching analysis."""
    csmName: str
    csmEmail: str
    salesforceOwnerId: Optional[str] = None
    userId: Optional[str] = None  # For management-level AI settings
    accountsData: Optional[List[Dict[str, Any]]] = None
    accountEngagementData: Optional[List[Dict[str, Any]]] = None
    transcriptionSamples: Optional[List[Dict[str, Any]]] = None
    semanticInsights: Optional[Dict[str, List[Dict[str, Any]]]] = None  # NEW: Structured signals from vector search
    daysBack: Optional[int] = 180
    calendarConnected: Optional[bool] = False


class SCCoachingRequest(BaseModel):
    """Request model for Solutions Consultant coaching analysis."""
    scName: str
    scEmail: str
    salesforceUserId: Optional[str] = None
    userId: Optional[str] = None  # For management-level AI settings
    opportunitiesData: Optional[List[Dict[str, Any]]] = None
    demoTranscripts: Optional[List[Dict[str, Any]]] = None
    discoveryTranscripts: Optional[List[Dict[str, Any]]] = None
    dealOutcomes: Optional[Dict[str, Any]] = None
    daysBack: Optional[int] = 180


class SDRCoachingRequest(BaseModel):
    """Request model for SDR (Sales Development Representative) coaching analysis."""
    sdrName: str
    sdrEmail: str
    salesforceUserId: Optional[str] = None
    userId: Optional[str] = None  # For management-level AI settings
    performanceMetrics: Dict[str, Any]
    leadPipelineAnalysis: Dict[str, Any]
    opportunityAnalysis: Dict[str, Any]
    sequenceData: Optional[List[Dict[str, Any]]] = None
    intentMetrics: Optional[Dict[str, Any]] = None  # 6Sense, UserGems, campaign data
    teamView: Optional[bool] = False
    daysBack: Optional[int] = 30


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


class CompetitiveCompanyModel(BaseModel):
    """Model for company data in competitive analysis."""
    id: Optional[str] = None
    name: Optional[str] = None
    domain: Optional[str] = None
    properties: Optional[Dict[str, Any]] = None


class CompetitiveRequest(BaseModel):
    """Request model for competitive analysis."""
    userId: Optional[str] = None
    userEmail: Optional[str] = None
    companies: List[CompetitiveCompanyModel]
    analysisType: Optional[str] = "comparative"  # "single" or "comparative"
    forceRefresh: Optional[bool] = False


class TranscriptChunkModel(BaseModel):
    """Model for transcript chunk in feature extraction."""
    content: str
    accountId: Optional[str] = None
    accountName: Optional[str] = None
    meetingSubject: Optional[str] = None
    meetingDate: Optional[str] = None
    meetingUrl: Optional[str] = None
    transcriptionId: Optional[str] = None


class FeatureExtractionRequest(BaseModel):
    """Request model for feature request extraction from transcripts."""
    userId: Optional[str] = None
    transcriptChunks: List[TranscriptChunkModel]


class AgendaGenerationRequest(BaseModel):
    """Request model for call agenda generation."""
    userId: Optional[str] = None
    projectName: str
    accountName: str
    projectStatus: str
    callSubject: str
    callScheduledAt: str  # ISO datetime string
    targetGoLive: Optional[str] = None  # YYYY-MM-DD
    completionPct: Optional[float] = None
    mavenlinkTasks: Optional[List[Dict[str, Any]]] = None
    incompleteItems: Optional[List[Dict[str, Any]]] = None  # Previous agenda items
    recentCalls: Optional[List[Dict[str, Any]]] = None  # Call summaries
    attendees: Optional[List[str]] = None


class CallVerificationRequest(BaseModel):
    """Request model for call transcript verification."""
    userId: Optional[str] = None
    projectName: str
    accountName: str
    callDate: str  # ISO datetime string
    agendaItems: List[Dict[str, Any]]  # Items to verify
    transcript: str  # Full transcript text
    speakers: Optional[List[Dict[str, Any]]] = None  # Speaker info


class CallAnalysisRequest(BaseModel):
    """Request model for per-call sentiment and engagement analysis."""
    userId: Optional[str] = None
    transcriptionId: Optional[str] = None  # Supabase transcription ID
    avomaMeetingUuid: Optional[str] = None  # Avoma meeting UUID
    projectName: str
    accountName: str
    meetingSubject: str
    meetingDate: str  # ISO datetime string
    # Transcript segments with speaker attribution
    transcriptSegments: List[Dict[str, Any]]  # [{speaker_id, transcript/text}]
    speakers: List[Dict[str, Any]]  # [{id, name}]
    attendees: Optional[List[Dict[str, Any]]] = None  # [{name, email}] for speaker classification
    implementationStage: Optional[str] = None  # discovery, configuration, testing, etc.
    projectContext: Optional[Dict[str, Any]] = None  # {target_go_live, completion_pct, etc.}
    # For linking results
    salesforceAccountId: Optional[str] = None
    salesforceProjectId: Optional[str] = None


class CrewResponse(BaseModel):
    success: bool
    job_id: Optional[str] = None
    result: Optional[Any] = None  # Changed from str to Any to support structured results
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


@app.get("/api/capabilities")
async def get_capabilities():
    """
    Report which AI providers and models are available.

    Checks:
    1. Whether the provider's optional dependency is installed
    2. Whether the required API key environment variable is set

    The frontend uses this to validate which models can be enabled.
    """
    capabilities = {
        "providers": {},
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Check OpenAI - always available via litellm, just needs API key
    openai_key = os.environ.get("OPENAI_API_KEY")
    capabilities["providers"]["openai"] = {
        "installed": True,  # OpenAI support included via litellm in crewai
        "api_key_set": bool(openai_key),
        "available": bool(openai_key),
        "env_var": "OPENAI_API_KEY",
    }

    # Check Anthropic - available via litellm, just needs API key
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    capabilities["providers"]["anthropic"] = {
        "installed": True,  # Anthropic support included via litellm in crewai
        "api_key_set": bool(anthropic_key),
        "available": bool(anthropic_key),
        "env_var": "ANTHROPIC_API_KEY",
    }

    # Check Google (Gemini) - requires optional crewai[google-genai] extra
    google_installed = False
    google_key = os.environ.get("GOOGLE_API_KEY")
    try:
        import google.genai
        google_installed = True
    except ImportError:
        pass
    capabilities["providers"]["google"] = {
        "installed": google_installed,
        "api_key_set": bool(google_key),
        "available": google_installed and bool(google_key),
        "env_var": "GOOGLE_API_KEY",
        "install_hint": 'uv add "crewai[google-genai]"' if not google_installed else None,
    }

    return capabilities


@app.get("/")
async def root():
    """Root endpoint with service info."""
    return {
        "service": "LUCI CrewAI Service",
        "version": "0.1.0",
        "endpoints": {
            "health": "/health",
            "capabilities": "/api/capabilities",
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
            "ae_coaching": "/api/crew/ae-coaching",
            "csm_coaching": "/api/crew/csm-coaching",
            "sc_coaching": "/api/crew/sc-coaching",
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
            supabase_url = os.getenv("SUPABASE_URL")
            supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")

            if supabase_url and supabase_key:
                from supabase import create_client
                supabase = create_client(supabase_url, supabase_key)

                # Try to fetch account by ID or salesforce ID
                query = supabase.table("accounts").select("name, account_tier, contract_value")
                if request.accountId:
                    query = query.eq("id", request.accountId)
                elif request.salesforceAccountId:
                    query = query.eq("salesforce_id", request.salesforceAccountId)

                result = query.limit(1).execute()
                if result.data and len(result.data) > 0:
                    account_data = result.data[0]
                    account_name = account_data.get("name")
                    account_tier = account_tier or account_data.get("account_tier")
                    arr = arr or account_data.get("contract_value")
                    logger.info(f"Fetched account from Supabase: {account_name}")

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
            supabase_url = os.getenv("SUPABASE_URL")
            supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")

            if supabase_url and supabase_key:
                from supabase import create_client
                supabase = create_client(supabase_url, supabase_key)

                query = supabase.table("accounts").select("name, account_tier, contract_value")
                if request.accountId:
                    query = query.eq("id", request.accountId)
                elif request.salesforceAccountId:
                    query = query.eq("salesforce_id", request.salesforceAccountId)

                result = query.limit(1).execute()
                if result.data and len(result.data) > 0:
                    account_data = result.data[0]
                    account_name = account_data.get("name")
                    if not request.accountTier:
                        request.accountTier = account_data.get("account_tier")
                    if not request.arr:
                        request.arr = account_data.get("contract_value")
                    logger.info(f"Fetched account from Supabase: {account_name}")

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

        crew = AccountAnalysisCrew(user_id=request.userId)
        result = crew.run(
            account_name=account_name,
            account_tier=request.accountTier,
            arr=request.arr,
            transcription=request.transcription,
            support_data=support_data,
            engagement_data=request.engagementData,
        )

        execution_time = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"Unified account analysis completed in {execution_time:.2f}s")
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

        crew = SentimentCrew(user_id=request.userId)
        result = crew.run(
            account_name=account_name or "Unknown Account",
            communications_data=request.transcription,  # Use transcription as communications data
            support_data=support_data,
            meeting_notes=None,  # No separate meeting notes - transcription contains this
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

        crew = ProjectSentimentCrew(user_id=req.userId)

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


@app.post("/api/crew/project-analysis")
async def run_project_analysis_crew(request: Request):
    """Run the unified project analysis crew.

    This crew consolidates implementation and sentiment analysis into a single
    comprehensive project health assessment.
    """
    import json
    start_time = datetime.utcnow()

    # Check for streaming parameter
    stream = request.query_params.get("stream", "false").lower() == "true"

    try:
        body = await request.json()
        req = ProjectAnalysisRequest(**body)

        project_name = req.project.get("project_name", "Unknown") if req.project else "Unknown"
        logger.info(f"Running project analysis crew for: {project_name}")

        crew = ProjectAnalysisCrew()

        if stream:
            # Streaming response
            async def generate():
                progress_messages = []

                def send_progress(stage: str, message: str):
                    progress_messages.append({"stage": stage, "message": message})

                try:
                    # Send initial progress
                    yield f"data: {json.dumps({'type': 'progress', 'stage': 'init', 'message': 'Starting project analysis...'})}\n\n"

                    # Run the crew
                    result = crew.run(
                        project=req.project or {},
                        project_owner=req.projectOwner or {"type": "unknown"},
                        mavenlink_tasks=req.mavenlinkTasks or [],
                        mavenlink_time_entries=req.mavenlinkTimeEntries or [],
                        transcripts=req.transcripts or [],
                        call_activity=req.callActivity or {},
                        email_activity=req.emailActivity,
                        send_progress=send_progress,
                    )

                    # Send any progress messages
                    for msg in progress_messages:
                        yield f"data: {json.dumps({'type': 'progress', 'stage': msg['stage'], 'message': msg['message']})}\n\n"

                    execution_time = (datetime.utcnow() - start_time).total_seconds()
                    logger.info(f"Project analysis crew completed in {execution_time:.2f}s")

                    # Send the final result
                    yield f"data: {json.dumps({'type': 'result', 'result': result})}\n\n"

                except Exception as e:
                    logger.error(f"Project analysis crew failed: {str(e)}")
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
                project=req.project or {},
                project_owner=req.projectOwner or {"type": "unknown"},
                mavenlink_tasks=req.mavenlinkTasks or [],
                mavenlink_time_entries=req.mavenlinkTimeEntries or [],
                transcripts=req.transcripts or [],
                call_activity=req.callActivity or {},
                email_activity=req.emailActivity,
            )

            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"Project analysis crew completed in {execution_time:.2f}s")

            return {
                "success": True,
                "result": result,
                "execution_time": execution_time,
            }

    except Exception as e:
        logger.error(f"Project analysis crew failed: {str(e)}")
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

        crew = OpportunityStrategyCrew(user_id=req.userId)

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
                        presales_context=req.presalesContext.model_dump() if req.presalesContext else None,
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
                presales_context=req.presalesContext.model_dump() if req.presalesContext else None,
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

        crew = SupportCoachingCrew(user_id=req.userId)

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

                    # Extract the analysis part for the frontend - it expects the analysis object directly
                    analysis_result = result.get("analysis") if isinstance(result, dict) else result
                    yield f"data: {json.dumps({'type': 'result', 'result': analysis_result})}\n\n"

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

        # Detailed logging for debugging data flow
        logger.info(f"=== PM Coaching Request Data ===")
        logger.info(f"Projects received: {len(req.projectsData) if req.projectsData else 0}")
        logger.info(f"Delivery metrics: {req.deliveryMetrics}")
        logger.info(f"Sentiment data items: {len(req.sentimentData) if req.sentimentData else 0}")
        logger.info(f"Transcription samples: {len(req.transcriptionSamples) if req.transcriptionSamples else 0}")
        logger.info(f"Escalation data items: {len(req.escalationData) if req.escalationData else 0}")
        if req.projectsData and len(req.projectsData) > 0:
            # Handle both camelCase and snake_case field names
            def get_field(p, camel, snake):
                return p.get(camel) if p.get(camel) is not None else p.get(snake)
            statuses = [get_field(p, 'projectStatus', 'project_status') or 'None' for p in req.projectsData[:10]]
            logger.info(f"Sample project statuses: {statuses}")
            with_ps_forecasted = sum(1 for p in req.projectsData if get_field(p, 'psForecastedLiveDate', 'ps_forecasted_live_date'))
            with_target = sum(1 for p in req.projectsData if get_field(p, 'targetGoLiveDate', 'target_go_live_date'))
            with_actual = sum(1 for p in req.projectsData if get_field(p, 'actualGoLiveDate', 'actual_go_live_date'))
            logger.info(f"Projects with ps_forecasted_live_date: {with_ps_forecasted}")
            logger.info(f"Projects with target_go_live_date: {with_target}")
            logger.info(f"Projects with actual_go_live_date: {with_actual}")
            # Log first project keys to understand the data format
            logger.info(f"First project keys: {list(req.projectsData[0].keys())}")
        logger.info(f"================================")

        crew = PMCoachingCrew(user_id=req.userId)

        if stream:
            import asyncio
            import concurrent.futures
            import queue

            async def generate():
                # Use a thread-safe queue instead of asyncio.Queue
                progress_queue = queue.Queue()
                result_holder = {"result": None, "error": None, "done": False}

                def step_callback(message: str):
                    # Thread-safe put to regular queue
                    progress_queue.put({"type": "progress", "message": message})

                def run_crew():
                    try:
                        result_holder["result"] = crew.run(
                            pm_name=req.pmName,
                            pm_email=req.pmEmail,
                            salesforce_owner_id=req.salesforceOwnerId,
                            projects_data=req.projectsData,
                            delivery_metrics=req.deliveryMetrics,
                            sentiment_data=req.sentimentData,
                            transcription_samples=req.transcriptionSamples,
                            escalation_data=req.escalationData,
                            agenda_metrics=req.agendaMetrics,
                            days_back=req.daysBack or 365,
                            step_callback=step_callback,
                        )
                    except Exception as e:
                        logger.error(f"Crew execution error: {str(e)}")
                        result_holder["error"] = str(e)
                    finally:
                        result_holder["done"] = True

                try:
                    yield f"data: {json.dumps({'type': 'progress', 'stage': 'init', 'message': 'Starting coaching analysis...'})}\n\n"

                    # Run crew in thread pool
                    loop = asyncio.get_running_loop()
                    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                    crew_future = executor.submit(run_crew)

                    # Stream progress messages as they arrive
                    while not result_holder["done"]:
                        try:
                            msg = progress_queue.get(timeout=0.5)
                            if msg["type"] == "progress":
                                yield f"data: {json.dumps({'type': 'progress', 'stage': 'processing', 'message': msg['message']})}\n\n"
                        except queue.Empty:
                            # Send keepalive comment to prevent connection timeout
                            yield f": keepalive\n\n"
                            continue

                    # Drain any remaining messages
                    while not progress_queue.empty():
                        try:
                            msg = progress_queue.get_nowait()
                            if msg["type"] == "progress":
                                yield f"data: {json.dumps({'type': 'progress', 'stage': 'processing', 'message': msg['message']})}\n\n"
                        except queue.Empty:
                            break

                    # Wait for thread to complete
                    crew_future.result(timeout=5)
                    executor.shutdown(wait=False)

                    if result_holder["error"]:
                        raise Exception(result_holder["error"])

                    result = result_holder["result"]
                    execution_time = (datetime.utcnow() - start_time).total_seconds()
                    logger.info(f"PM coaching crew completed in {execution_time:.2f}s")

                    # Check if crew returned an error (success: False)
                    if result and result.get('success') == False:
                        error_msg = result.get('error', 'Analysis failed - no result returned')
                        logger.error(f"PM coaching crew returned error: {error_msg}")
                        yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
                    elif result and result.get('result'):
                        yield f"data: {json.dumps({'type': 'result', 'result': result.get('result'), 'pm_name': result.get('pm_name'), 'pm_email': result.get('pm_email'), 'projects_analyzed': result.get('projects_analyzed'), 'provider': result.get('provider'), 'model': result.get('model')})}\n\n"
                    else:
                        # No result - this shouldn't happen but handle gracefully
                        logger.error(f"PM coaching crew returned empty result: {result}")
                        yield f"data: {json.dumps({'type': 'error', 'message': 'Analysis completed but no result was returned'})}\n\n"

                except Exception as e:
                    logger.error(f"PM coaching crew failed: {str(e)}")
                    import traceback
                    logger.error(traceback.format_exc())
                    yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
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
                agenda_metrics=req.agendaMetrics,
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


@app.post("/api/crew/ae-coaching")
async def run_ae_coaching_crew(request: Request):
    """Run the Account Executive coaching analysis crew with optional streaming."""
    import json
    start_time = datetime.utcnow()

    stream = request.query_params.get("stream", "false").lower() == "true"

    try:
        body = await request.json()
        req = AECoachingRequest(**body)

        logger.info(f"Running AE coaching crew for: {req.aeName} ({req.aeEmail})")

        crew = AECoachingCrew(user_id=req.userId)

        if stream:
            async def generate():
                progress_messages = []

                def step_callback(message: str):
                    progress_messages.append(message)

                try:
                    yield f"data: {json.dumps({'type': 'progress', 'stage': 'init', 'message': 'Starting coaching analysis...'})}\n\n"

                    result = crew.run(
                        ae_name=req.aeName,
                        ae_email=req.aeEmail,
                        opportunities_data=req.opportunitiesData,
                        transcription_samples=req.transcriptionSamples,
                        days_back=req.daysBack or 180,
                        step_callback=step_callback,
                    )

                    for msg in progress_messages:
                        yield f"data: {json.dumps({'type': 'progress', 'stage': 'processing', 'message': msg})}\n\n"

                    execution_time = (datetime.utcnow() - start_time).total_seconds()
                    logger.info(f"AE coaching crew completed in {execution_time:.2f}s")

                    # Check if crew returned an error (success: False)
                    if result and result.get('success') == False:
                        error_msg = result.get('error', 'Analysis failed - no result returned')
                        logger.error(f"AE coaching crew returned error: {error_msg}")
                        yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
                    elif result and result.get('result'):
                        yield f"data: {json.dumps({'type': 'result', 'result': result.get('result'), 'ae_name': result.get('ae_name'), 'ae_email': result.get('ae_email'), 'opportunities_analyzed': result.get('opportunities_analyzed'), 'provider': result.get('provider'), 'model': result.get('model')})}\n\n"
                    else:
                        logger.error(f"AE coaching crew returned empty result: {result}")
                        yield f"data: {json.dumps({'type': 'error', 'message': 'Analysis completed but no result was returned'})}\n\n"

                except Exception as e:
                    logger.error(f"AE coaching crew failed: {str(e)}")
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
                ae_name=req.aeName,
                ae_email=req.aeEmail,
                opportunities_data=req.opportunitiesData,
                transcription_samples=req.transcriptionSamples,
                days_back=req.daysBack or 180,
            )

            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"AE coaching crew completed in {execution_time:.2f}s")

            return {
                "success": True,
                "result": result.get("result"),
                "ae_name": result.get("ae_name"),
                "ae_email": result.get("ae_email"),
                "opportunities_analyzed": result.get("opportunities_analyzed"),
                "provider": result.get("provider"),
                "model": result.get("model"),
                "execution_time": execution_time,
            }

    except Exception as e:
        logger.error(f"AE coaching crew failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/crew/csm-coaching")
async def run_csm_coaching_crew(request: Request):
    """Run the Customer Success Manager coaching analysis crew with optional streaming."""
    import json
    start_time = datetime.utcnow()

    stream = request.query_params.get("stream", "false").lower() == "true"

    try:
        body = await request.json()
        req = CSMCoachingRequest(**body)

        logger.info(f"Running CSM coaching crew for: {req.csmName} ({req.csmEmail})")

        crew = CSMCoachingCrew(user_id=req.userId)

        if stream:
            async def generate():
                progress_messages = []

                def step_callback(message: str):
                    progress_messages.append(message)

                try:
                    yield f"data: {json.dumps({'type': 'progress', 'stage': 'init', 'message': 'Starting coaching analysis...'})}\n\n"

                    result = crew.run(
                        csm_name=req.csmName,
                        csm_email=req.csmEmail,
                        accounts_data=req.accountsData,
                        engagement_data=req.accountEngagementData,
                        transcription_samples=req.transcriptionSamples,
                        semantic_insights=req.semanticInsights,  # NEW: Structured signals from vector search
                        days_back=req.daysBack or 180,
                        calendar_connected=req.calendarConnected or False,
                        step_callback=step_callback,
                    )

                    for msg in progress_messages:
                        yield f"data: {json.dumps({'type': 'progress', 'stage': 'processing', 'message': msg})}\n\n"

                    execution_time = (datetime.utcnow() - start_time).total_seconds()
                    logger.info(f"CSM coaching crew completed in {execution_time:.2f}s")

                    # Check if crew returned an error (success: False)
                    if result and result.get('success') == False:
                        error_msg = result.get('error', 'Analysis failed - no result returned')
                        logger.error(f"CSM coaching crew returned error: {error_msg}")
                        yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
                    elif result and result.get('result'):
                        yield f"data: {json.dumps({'type': 'result', 'result': result.get('result'), 'csm_name': result.get('csm_name'), 'csm_email': result.get('csm_email'), 'accounts_analyzed': result.get('accounts_analyzed'), 'provider': result.get('provider'), 'model': result.get('model')})}\n\n"
                    else:
                        logger.error(f"CSM coaching crew returned empty result: {result}")
                        yield f"data: {json.dumps({'type': 'error', 'message': 'Analysis completed but no result was returned'})}\n\n"

                except Exception as e:
                    logger.error(f"CSM coaching crew failed: {str(e)}")
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
                csm_name=req.csmName,
                csm_email=req.csmEmail,
                accounts_data=req.accountsData,
                engagement_data=req.accountEngagementData,
                transcription_samples=req.transcriptionSamples,
                semantic_insights=req.semanticInsights,  # NEW: Structured signals from vector search
                days_back=req.daysBack or 180,
                calendar_connected=req.calendarConnected or False,
            )

            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"CSM coaching crew completed in {execution_time:.2f}s")

            return {
                "success": True,
                "result": result.get("result"),
                "csm_name": result.get("csm_name"),
                "csm_email": result.get("csm_email"),
                "accounts_analyzed": result.get("accounts_analyzed"),
                "provider": result.get("provider"),
                "model": result.get("model"),
                "execution_time": execution_time,
            }

    except Exception as e:
        logger.error(f"CSM coaching crew failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/crew/sc-coaching")
async def run_sc_coaching_crew(request: Request):
    """Run the Solutions Consultant coaching analysis crew with optional streaming."""
    import json
    start_time = datetime.utcnow()

    stream = request.query_params.get("stream", "false").lower() == "true"

    try:
        body = await request.json()
        req = SCCoachingRequest(**body)

        logger.info(f"Running SC coaching crew for: {req.scName} ({req.scEmail})")

        crew = SCCoachingCrew(user_id=req.userId)

        if stream:
            async def generate():
                progress_messages = []

                def step_callback(message: str):
                    progress_messages.append(message)

                try:
                    yield f"data: {json.dumps({'type': 'progress', 'stage': 'init', 'message': 'Starting coaching analysis...'})}\n\n"

                    result = crew.run(
                        sc_name=req.scName,
                        sc_email=req.scEmail,
                        opportunities_data=req.opportunitiesData,
                        demo_transcripts=req.demoTranscripts,
                        discovery_transcripts=req.discoveryTranscripts,
                        deal_outcomes=req.dealOutcomes,
                        days_back=req.daysBack or 180,
                        step_callback=step_callback,
                    )

                    for msg in progress_messages:
                        yield f"data: {json.dumps({'type': 'progress', 'stage': 'processing', 'message': msg})}\n\n"

                    execution_time = (datetime.utcnow() - start_time).total_seconds()
                    logger.info(f"SC coaching crew completed in {execution_time:.2f}s")

                    # Check if crew returned an error (success: False)
                    if result and result.get('success') == False:
                        error_msg = result.get('error', 'Analysis failed - no result returned')
                        logger.error(f"SC coaching crew returned error: {error_msg}")
                        yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
                    elif result and result.get('result'):
                        yield f"data: {json.dumps({'type': 'result', 'result': result.get('result'), 'sc_name': result.get('sc_name'), 'sc_email': result.get('sc_email'), 'opportunities_analyzed': result.get('opportunities_analyzed'), 'provider': result.get('provider'), 'model': result.get('model')})}\n\n"
                    else:
                        logger.error(f"SC coaching crew returned empty result: {result}")
                        yield f"data: {json.dumps({'type': 'error', 'message': 'Analysis completed but no result was returned'})}\n\n"

                except Exception as e:
                    logger.error(f"SC coaching crew failed: {str(e)}")
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
                sc_name=req.scName,
                sc_email=req.scEmail,
                opportunities_data=req.opportunitiesData,
                demo_transcripts=req.demoTranscripts,
                discovery_transcripts=req.discoveryTranscripts,
                deal_outcomes=req.dealOutcomes,
                days_back=req.daysBack or 180,
            )

            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"SC coaching crew completed in {execution_time:.2f}s")

            return {
                "success": True,
                "result": result.get("result"),
                "sc_name": result.get("sc_name"),
                "sc_email": result.get("sc_email"),
                "opportunities_analyzed": result.get("opportunities_analyzed"),
                "provider": result.get("provider"),
                "model": result.get("model"),
                "execution_time": execution_time,
            }

    except Exception as e:
        logger.error(f"SC coaching crew failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/crew/sdr-coaching")
async def run_sdr_coaching_crew(request: Request):
    """Run the SDR (Sales Development Representative) coaching analysis crew with optional streaming."""
    import json
    start_time = datetime.utcnow()

    stream = request.query_params.get("stream", "false").lower() == "true"

    try:
        body = await request.json()
        req = SDRCoachingRequest(**body)

        logger.info(f"Running SDR coaching crew for: {req.sdrName} ({req.sdrEmail})")

        from .crews.sdr_coaching_crew import SDRCoachingCrew
        crew = SDRCoachingCrew(user_id=req.userId)

        if stream:
            async def generate():
                progress_messages = []

                def step_callback(message: str):
                    progress_messages.append(message)

                try:
                    yield f"data: {json.dumps({'type': 'progress', 'stage': 'init', 'message': 'Starting coaching analysis...'})}\n\n"

                    result = crew.run(
                        sdr_name=req.sdrName,
                        sdr_email=req.sdrEmail,
                        performance_metrics=req.performanceMetrics,
                        lead_pipeline_analysis=req.leadPipelineAnalysis,
                        opportunity_analysis=req.opportunityAnalysis,
                        sequence_data=req.sequenceData,
                        intent_metrics=req.intentMetrics,
                        days_back=req.daysBack or 30,
                        step_callback=step_callback,
                    )

                    for msg in progress_messages:
                        yield f"data: {json.dumps({'type': 'progress', 'stage': 'processing', 'message': msg})}\n\n"

                    execution_time = (datetime.utcnow() - start_time).total_seconds()
                    logger.info(f"SDR coaching crew completed in {execution_time:.2f}s")

                    # Check if crew returned an error (success: False)
                    if result and result.get('success') == False:
                        error_msg = result.get('error', 'Analysis failed - no result returned')
                        logger.error(f"SDR coaching crew returned error: {error_msg}")
                        yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
                    elif result and result.get('result'):
                        yield f"data: {json.dumps({'type': 'result', 'result': result.get('result'), 'sdr_name': result.get('sdr_name'), 'sdr_email': result.get('sdr_email'), 'provider': result.get('provider'), 'model': result.get('model')})}\n\n"
                    else:
                        logger.error(f"SDR coaching crew returned empty result: {result}")
                        yield f"data: {json.dumps({'type': 'error', 'message': 'Analysis completed but no result was returned'})}\n\n"

                except Exception as e:
                    logger.error(f"SDR coaching crew failed: {str(e)}")
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
                sdr_name=req.sdrName,
                sdr_email=req.sdrEmail,
                performance_metrics=req.performanceMetrics,
                lead_pipeline_analysis=req.leadPipelineAnalysis,
                opportunity_analysis=req.opportunityAnalysis,
                sequence_data=req.sequenceData,
                intent_metrics=req.intentMetrics,
                days_back=req.daysBack or 30,
            )

            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"SDR coaching crew completed in {execution_time:.2f}s")

            return {
                "success": True,
                "result": result.get("result"),
                "sdr_name": result.get("sdr_name"),
                "sdr_email": result.get("sdr_email"),
                "provider": result.get("provider"),
                "model": result.get("model"),
                "execution_time": execution_time,
            }

    except Exception as e:
        logger.error(f"SDR coaching crew failed: {str(e)}")
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

        crew = SupportResolutionCrew(user_id=req.userId)

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

        crew = SCPrepCrew(user_id=req.userId)

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


@app.post("/api/crew/competitive")
async def run_competitive_crew(request: Request):
    """Run the competitive intelligence analysis crew."""
    import json
    start_time = datetime.utcnow()

    stream = request.query_params.get("stream", "false").lower() == "true"

    try:
        body = await request.json()
        req = CompetitiveRequest(**body)

        logger.info(f"Running competitive crew for {len(req.companies)} companies (type: {req.analysisType})")

        crew = CompetitiveCrew(user_id=req.userId)

        # Convert Pydantic models to dicts for the crew
        companies_data = [c.model_dump() for c in req.companies]

        if stream:
            async def generate():
                progress_messages = []

                try:
                    yield f"data: {json.dumps({'type': 'progress', 'stage': 'init', 'message': 'Starting competitive analysis...'})}\n\n"

                    result = crew.run(
                        companies=companies_data,
                        analysis_type=req.analysisType or "comparative",
                    )

                    for msg in progress_messages:
                        yield f"data: {json.dumps({'type': 'progress', 'stage': 'processing', 'message': msg})}\n\n"

                    execution_time = (datetime.utcnow() - start_time).total_seconds()
                    logger.info(f"Competitive crew completed in {execution_time:.2f}s")

                    yield f"data: {json.dumps({'type': 'result', 'result': result.get('result'), 'analysis': result.get('analysis'), 'analysisType': result.get('analysisType'), 'provider': result.get('provider'), 'model': result.get('model')})}\n\n"

                except Exception as e:
                    logger.error(f"Competitive crew failed: {str(e)}")
                    yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                }
            )
        else:
            result = crew.run(
                companies=companies_data,
                analysis_type=req.analysisType or "comparative",
            )

            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"Competitive crew completed in {execution_time:.2f}s")

            return {
                "success": True,
                "result": result.get("result"),
                "analysis": result.get("analysis"),
                "analysisType": result.get("analysisType"),
                "provider": result.get("provider"),
                "model": result.get("model"),
                "execution_time": execution_time,
            }

    except Exception as e:
        logger.error(f"Competitive crew failed: {str(e)}")
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


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
