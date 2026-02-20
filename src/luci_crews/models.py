"""
Pydantic models for LUCI CrewAI Service API requests and responses.

This module contains all the data models used for API request/response validation.
Extracted from main.py for better modularity.
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel


# =============================================================================
# Core Models
# =============================================================================

class CrewResponse(BaseModel):
    """Standard response model for all crew endpoints."""
    success: bool
    job_id: Optional[str] = None
    result: Optional[Any] = None  # Supports structured results
    error: Optional[str] = None
    execution_time: Optional[float] = None
    data_freshness: Optional[Dict[str, Any]] = None  # Metadata about underlying data freshness


# =============================================================================
# Sales & Pipeline Models
# =============================================================================

class SalesPipelineRequest(BaseModel):
    """Request model for sales pipeline analysis."""
    user_id: str
    user_email: str
    opportunities: list = []
    summary: Optional[dict] = None


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
    """Request model for opportunity strategy analysis."""
    opportunityId: str
    userId: Optional[str] = None
    userEmail: Optional[str] = None
    forceRefresh: Optional[bool] = False
    opportunityData: Optional[OpportunityDataModel] = None
    transcriptionIds: Optional[List[str]] = None
    transcriptionData: Optional[List[TranscriptionDataModel]] = None
    salesforceAccountId: Optional[str] = None
    presalesContext: Optional[PresalesContextModel] = None  # Context about presales calls


class MeddpiccGapActionsRequest(BaseModel):
    """Request model for MEDDPICC gap-specific action recommendations."""
    opportunityId: str
    gapField: str  # e.g. 'economic_buyer', 'metrics', 'decision_criteria', etc.
    userId: Optional[str] = None
    userEmail: Optional[str] = None
    opportunityData: Optional[OpportunityDataModel] = None
    transcriptionData: Optional[List[TranscriptionDataModel]] = None
    salesforceAccountId: Optional[str] = None
    contactsData: Optional[List[Dict[str, Any]]] = None  # Account contacts for personalization


# =============================================================================
# Account Models
# =============================================================================

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


class SentimentRequest(BaseModel):
    """Request model for account sentiment analysis."""
    userId: Optional[str] = None
    accountId: Optional[str] = None
    salesforceAccountId: Optional[str] = None
    userEmail: Optional[str] = None
    transcription: Optional[str] = None
    salesforceContext: Optional[Dict[str, Any]] = None
    customerIdentifier: Optional[str] = None


# =============================================================================
# Implementation / Project Models
# =============================================================================

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
    """Request model for implementation analysis."""
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
    dataAvailabilityWarnings: Optional[List[str]] = None  # Warnings about missing data to include in analysis


class ProjectSentimentRequest(BaseModel):
    """Request model for project sentiment analysis."""
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


# =============================================================================
# Support Models
# =============================================================================

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
    """Request model for support agent coaching analysis."""
    agentName: str
    agentEmail: str
    ownerId: Optional[str] = None  # Optional - needed to fetch cases from DB, but not if casesData provided
    userId: Optional[str] = None  # For management-level AI settings
    casesData: Optional[List[CaseDataModel]] = None
    daysBack: Optional[int] = 90


class SupportResolutionRequest(BaseModel):
    """Request model for support case resolution assistance."""
    caseSubject: str
    caseDescription: Optional[str] = None
    caseType: Optional[str] = None
    casePriority: Optional[str] = None
    accountName: Optional[str] = None
    contactName: Optional[str] = None
    userId: Optional[str] = None
    salesforceUserId: Optional[str] = None
    caseNumber: Optional[str] = None


# =============================================================================
# Coaching Models
# =============================================================================

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
    semanticInsights: Optional[Dict[str, List[Dict[str, Any]]]] = None  # Structured signals from vector search
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


# =============================================================================
# SC Prep & Competitive Models
# =============================================================================

class SCPrepRequest(BaseModel):
    """Request model for SC (Solutions Consultant) preparation."""
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


# =============================================================================
# Feature Extraction & Agenda Models
# =============================================================================

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


# =============================================================================
# Call Analysis Models
# =============================================================================

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


# =============================================================================
# Configuration & Sandbox Models
# =============================================================================

class ConfigUpdateRequest(BaseModel):
    """Request model for updating agent/task configurations."""
    role: Optional[str] = None
    goal: Optional[str] = None
    backstory: Optional[str] = None
    verbose: Optional[bool] = None
    allow_delegation: Optional[bool] = None
    description: Optional[str] = None
    expected_output: Optional[str] = None
    agent: Optional[str] = None
    context: Optional[str] = None  # Page context for Crew Studio (e.g., 'sales', 'account', 'implementation')


class SandboxTestRequest(BaseModel):
    """Request to run a sandbox test with custom agent/task configurations."""
    agent: Dict[str, Any]  # Agent configuration
    task: Dict[str, Any]   # Task configuration
    sampleData: Optional[Dict[str, Any]] = {}  # Sample data for testing
    userId: Optional[str] = None


# =============================================================================
# Custom Analysis Models
# =============================================================================

class CustomAnalysisContext(BaseModel):
    """Context data for custom analysis."""
    target: Optional[Dict[str, Any]] = None
    accounts: Optional[List[Dict[str, Any]]] = None
    opportunities: Optional[List[Dict[str, Any]]] = None
    meetings: Optional[List[Dict[str, Any]]] = None
    cases: Optional[List[Dict[str, Any]]] = None
    contacts: Optional[List[Dict[str, Any]]] = None


class CustomAnalysisRequest(BaseModel):
    """Request to run a custom user-created analysis."""
    analysisId: str
    analysisName: str
    expertise: str  # AI persona/backstory
    questions: str  # What questions to answer
    outputFormat: Optional[str] = None
    targetType: str  # account, opportunity, project
    targetId: str
    context: CustomAnalysisContext


# =============================================================================
# QBR Summary Models
# =============================================================================

class QbrSummaryRequest(BaseModel):
    """Request model for QBR summary generation."""
    userId: Optional[str] = None
    accountId: str
    accountName: str
    quarterStart: str  # YYYY-MM-DD
    quarterEnd: str  # YYYY-MM-DD
    # Optional pre-fetched data
    healthTrendData: Optional[List[Dict[str, Any]]] = None
    usageData: Optional[Dict[str, Any]] = None
    supportCasesData: Optional[List[Dict[str, Any]]] = None
    renewalData: Optional[Dict[str, Any]] = None


# =============================================================================
# Email Draft Models
# =============================================================================

class EmailDraftRequest(BaseModel):
    """Request model for email drafting."""
    userId: Optional[str] = None
    accountId: str
    templateType: str  # executive_checkin, renewal_kickoff, risk_mitigation, qbr_followup, expansion_proposal
    recipientRole: Optional[str] = None  # e.g., "VP of Operations", "CFO"
    additionalContext: Optional[str] = None
    # Optional pre-fetched data
    accountData: Optional[Dict[str, Any]] = None
    recentInteractions: Optional[List[Dict[str, Any]]] = None
    openCases: Optional[List[Dict[str, Any]]] = None
    renewalStatus: Optional[Dict[str, Any]] = None


# =============================================================================
# Expansion Specialist Models
# =============================================================================

class ExpansionSpecialistRequest(BaseModel):
    """Request model for expansion opportunity analysis."""
    userId: Optional[str] = None
    accountId: str
    currentArr: Optional[float] = 0
    # Optional pre-fetched data
    usageData: Optional[Dict[str, Any]] = None
    arrHistoryData: Optional[List[Dict[str, Any]]] = None
    healthScoreData: Optional[Dict[str, Any]] = None
    engagementData: Optional[Dict[str, Any]] = None
    stakeholderData: Optional[List[Dict[str, Any]]] = None


# =============================================================================
# Renewal Readiness Models
# =============================================================================

class RenewalReadinessRequest(BaseModel):
    """Request model for renewal readiness assessment."""
    userId: Optional[str] = None
    accountId: str
    contractEndDate: str  # YYYY-MM-DD
    currentArr: float
    # Optional pre-fetched data
    healthScoreData: Optional[Dict[str, Any]] = None
    usageData: Optional[Dict[str, Any]] = None
    supportCasesData: Optional[List[Dict[str, Any]]] = None
    engagementGapData: Optional[Dict[str, Any]] = None
    stakeholderMapData: Optional[List[Dict[str, Any]]] = None


# =============================================================================
# Strategic Action Models
# =============================================================================

class StrategicActionRequest(BaseModel):
    """Request model for strategic action document generation."""
    userId: Optional[str] = None
    actionType: str  # board_summary, pipeline_directive, segment_deep_dive, churn_prevention_plan, competitive_response
    segment: Optional[str] = None  # For segment_deep_dive (e.g., "Enterprise")
    accountId: Optional[str] = None  # For churn_prevention_plan
    quarter: Optional[str] = None  # e.g., "Q1 2026"


# =============================================================================
# Executive Briefing Models
# =============================================================================

class ExecutiveBriefingRequest(BaseModel):
    """Request model for executive morning briefing generation."""
    userId: Optional[str] = None


# =============================================================================
# Contextual Drilldown Models
# =============================================================================

class ContextualDrilldownRequest(BaseModel):
    """Request model for contextual drilldown synthesis."""
    userId: Optional[str] = None
    entityType: str  # account, metric, renewal
    entityId: str  # Account UUID or metric name
    context: Optional[str] = "risk"  # risk, renewal, expansion, engagement
