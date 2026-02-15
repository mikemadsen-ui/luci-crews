"""Coaching crew endpoints for role-specific performance analysis.

This module contains endpoints for:
- Support agent coaching
- PM (Implementation Consultant) coaching
- AE (Account Executive) coaching
- CSM (Customer Success Manager) coaching
- SC (Solutions Consultant) coaching
- SDR (Sales Development Representative) coaching

All endpoints use a factory function to reduce code duplication while maintaining
identical response formats for streaming and non-streaming modes.
"""

import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..models import (
    SupportCoachingRequest,
    PMCoachingRequest,
    AECoachingRequest,
    CSMCoachingRequest,
    SCCoachingRequest,
    SDRCoachingRequest,
)
from ..crews.support_coaching_crew import SupportCoachingCrew
from ..crews.pm_coaching_crew import PMCoachingCrew
from ..crews.ae_coaching_crew import AECoachingCrew
from ..crews.csm_coaching_crew import CSMCoachingCrew
from ..crews.sc_coaching_crew import SCCoachingCrew
from ..crews.sdr_coaching_crew import SDRCoachingCrew
from ..utils.streaming import (
    SimpleStreamingContext,
    ThreadedStreamingContext,
    create_streaming_response,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/crew", tags=["coaching"])


# Type variable for request models
T = TypeVar("T", bound=BaseModel)


class CoachingEndpointConfig:
    """Configuration for a coaching endpoint.

    Attributes:
        crew_class: The crew class to instantiate
        request_model: The Pydantic model for request validation
        role_name: Human-readable role name (e.g., "support", "PM", "AE")
        person_name_field: Field name in request for person's name (e.g., "agentName", "pmName")
        person_email_field: Field name in request for person's email (e.g., "agentEmail", "pmEmail")
        use_threaded_streaming: Whether to use ThreadedStreamingContext (for long-running crews)
        run_params_builder: Function to build the params dict for crew.run() from the request
        response_fields_builder: Function to build extra response fields from the result
        debug_logging: Optional function for additional debug logging
    """
    def __init__(
        self,
        crew_class: Type,
        request_model: Type[T],
        role_name: str,
        person_name_field: str,
        person_email_field: str,
        run_params_builder: Callable[[T], Dict[str, Any]],
        response_fields_builder: Callable[[Dict[str, Any]], Dict[str, Any]],
        use_threaded_streaming: bool = False,
        debug_logging: Optional[Callable[[T], None]] = None,
    ):
        self.crew_class = crew_class
        self.request_model = request_model
        self.role_name = role_name
        self.person_name_field = person_name_field
        self.person_email_field = person_email_field
        self.run_params_builder = run_params_builder
        self.response_fields_builder = response_fields_builder
        self.use_threaded_streaming = use_threaded_streaming
        self.debug_logging = debug_logging


def create_coaching_endpoint(config: CoachingEndpointConfig):
    """Factory function that creates a coaching endpoint handler.

    Creates a FastAPI route handler with standardized streaming/non-streaming logic.
    The returned handler processes requests using the provided configuration.

    Args:
        config: Configuration object defining crew class, request model, and field mappings

    Returns:
        An async function suitable for use as a FastAPI route handler
    """

    async def coaching_endpoint(request: Request):
        """Run the coaching analysis crew with optional streaming."""
        start_time = datetime.utcnow()
        stream = request.query_params.get("stream", "false").lower() == "true"

        try:
            body = await request.json()
            req = config.request_model(**body)

            person_name = getattr(req, config.person_name_field)
            person_email = getattr(req, config.person_email_field)

            logger.info(f"Running {config.role_name} coaching crew for: {person_name} ({person_email})")

            # Optional debug logging (used by PM coaching)
            if config.debug_logging:
                config.debug_logging(req)

            crew = config.crew_class(user_id=req.userId)
            run_params = config.run_params_builder(req)

            if stream:
                if config.use_threaded_streaming:
                    return await _handle_threaded_streaming(
                        crew, run_params, config, person_name, person_email
                    )
                else:
                    return await _handle_simple_streaming(
                        crew, run_params, config, person_name, person_email
                    )
            else:
                result = crew.run(**run_params)

                execution_time = (datetime.utcnow() - start_time).total_seconds()
                logger.info(f"{config.role_name} coaching crew completed in {execution_time:.2f}s")

                response = {
                    "success": True,
                    "result": result.get("result") if "result" in result else result.get("analysis"),
                    "execution_time": execution_time,
                }
                response.update(config.response_fields_builder(result))
                return response

        except Exception as e:
            logger.error(f"{config.role_name} coaching crew failed: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    return coaching_endpoint


async def _handle_simple_streaming(
    crew,
    run_params: Dict[str, Any],
    config: CoachingEndpointConfig,
    person_name: str,
    person_email: str,
):
    """Handle streaming response using SimpleStreamingContext."""
    ctx = SimpleStreamingContext()

    async def generate():
        try:
            yield ctx.init_message("Starting coaching analysis...")

            result = crew.run(**run_params, step_callback=ctx.step_callback)

            for msg in ctx.get_progress_messages():
                yield msg

            logger.info(f"{config.role_name} coaching crew completed in {ctx.execution_time:.2f}s")

            # Check if crew returned an error (success: False)
            if result and result.get('success') == False:
                error_msg = result.get('error', 'Analysis failed - no result returned')
                logger.error(f"{config.role_name} coaching crew returned error: {error_msg}")
                yield ctx.error_message(error_msg)
            elif result and (result.get('result') or result.get('analysis')):
                # Extract the analysis part - supports both 'result' and 'analysis' keys
                analysis_result = result.get('result') or result.get('analysis')
                extra_fields = config.response_fields_builder(result)
                yield ctx.result_message(analysis_result, **extra_fields)
            else:
                logger.error(f"{config.role_name} coaching crew returned empty result: {result}")
                yield ctx.error_message('Analysis completed but no result was returned')

        except Exception as e:
            logger.error(f"{config.role_name} coaching crew failed: {str(e)}")
            yield ctx.error_message(str(e))

    return create_streaming_response(generate())


async def _handle_threaded_streaming(
    crew,
    run_params: Dict[str, Any],
    config: CoachingEndpointConfig,
    person_name: str,
    person_email: str,
):
    """Handle streaming response using ThreadedStreamingContext."""
    ctx = ThreadedStreamingContext()

    async def generate():
        try:
            yield ctx.init_message("Starting coaching analysis...")

            def run_crew(step_callback):
                return crew.run(**run_params, step_callback=step_callback)

            async for msg in ctx.run_with_progress(run_crew):
                yield msg

            logger.info(f"{config.role_name} coaching crew completed in {ctx.execution_time:.2f}s")

            if ctx.error:
                logger.error(f"{config.role_name} coaching crew failed: {ctx.error}")
                yield ctx.error_message()
            elif ctx.result:
                # Check if crew returned an error (success: False)
                if ctx.result.get('success') == False:
                    error_msg = ctx.result.get('error', 'Analysis failed - no result returned')
                    logger.error(f"{config.role_name} coaching crew returned error: {error_msg}")
                    yield ctx.error_message(error_msg)
                elif ctx.result.get('result') or ctx.result.get('analysis'):
                    analysis_result = ctx.result.get('result') or ctx.result.get('analysis')
                    extra_fields = config.response_fields_builder(ctx.result)
                    yield ctx.result_message(analysis_result, **extra_fields)
                else:
                    logger.error(f"{config.role_name} coaching crew returned empty result: {ctx.result}")
                    yield ctx.error_message('Analysis completed but no result was returned')
            else:
                yield ctx.error_message('Analysis completed but no result was returned')

        except Exception as e:
            logger.error(f"{config.role_name} coaching crew failed: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            yield ctx.error_message(str(e))

    return create_streaming_response(generate())


# =============================================================================
# Endpoint Configurations
# =============================================================================

def _support_run_params(req: SupportCoachingRequest) -> Dict[str, Any]:
    """Build run params for support coaching crew."""
    cases_data = None
    if req.casesData:
        cases_data = [c.model_dump() for c in req.casesData]
    return {
        "agent_name": req.agentName,
        "agent_email": req.agentEmail,
        "owner_id": req.ownerId,
        "cases_data": cases_data,
        "days_back": req.daysBack or 90,
    }


def _support_response_fields(result: Dict[str, Any]) -> Dict[str, Any]:
    """Build response fields for support coaching crew."""
    return {
        "agent_name": result.get("agent_name"),
        "agent_email": result.get("agent_email"),
        "cases_analyzed": result.get("cases_analyzed"),
        "days_back": result.get("days_back"),
    }


def _pm_debug_logging(req: PMCoachingRequest) -> None:
    """Debug logging for PM coaching requests."""
    logger.info("=== PM Coaching Request Data ===")
    logger.info(f"Projects received: {len(req.projectsData) if req.projectsData else 0}")
    logger.info(f"Delivery metrics: {req.deliveryMetrics}")
    logger.info(f"Sentiment data items: {len(req.sentimentData) if req.sentimentData else 0}")
    logger.info(f"Transcription samples: {len(req.transcriptionSamples) if req.transcriptionSamples else 0}")
    logger.info(f"Escalation data items: {len(req.escalationData) if req.escalationData else 0}")
    if req.projectsData and len(req.projectsData) > 0:
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
        logger.info(f"First project keys: {list(req.projectsData[0].keys())}")
    logger.info("================================")


def _pm_run_params(req: PMCoachingRequest) -> Dict[str, Any]:
    """Build run params for PM coaching crew."""
    return {
        "pm_name": req.pmName,
        "pm_email": req.pmEmail,
        "salesforce_owner_id": req.salesforceOwnerId,
        "projects_data": req.projectsData,
        "delivery_metrics": req.deliveryMetrics,
        "sentiment_data": req.sentimentData,
        "transcription_samples": req.transcriptionSamples,
        "escalation_data": req.escalationData,
        "agenda_metrics": req.agendaMetrics,
        "days_back": req.daysBack or 365,
    }


def _pm_response_fields(result: Dict[str, Any]) -> Dict[str, Any]:
    """Build response fields for PM coaching crew."""
    return {
        "pm_name": result.get("pm_name"),
        "pm_email": result.get("pm_email"),
        "projects_analyzed": result.get("projects_analyzed"),
        "provider": result.get("provider"),
        "model": result.get("model"),
    }


def _ae_run_params(req: AECoachingRequest) -> Dict[str, Any]:
    """Build run params for AE coaching crew."""
    return {
        "ae_name": req.aeName,
        "ae_email": req.aeEmail,
        "opportunities_data": req.opportunitiesData,
        "transcription_samples": req.transcriptionSamples,
        "days_back": req.daysBack or 180,
    }


def _ae_response_fields(result: Dict[str, Any]) -> Dict[str, Any]:
    """Build response fields for AE coaching crew."""
    return {
        "ae_name": result.get("ae_name"),
        "ae_email": result.get("ae_email"),
        "opportunities_analyzed": result.get("opportunities_analyzed"),
        "provider": result.get("provider"),
        "model": result.get("model"),
    }


def _csm_run_params(req: CSMCoachingRequest) -> Dict[str, Any]:
    """Build run params for CSM coaching crew."""
    return {
        "csm_name": req.csmName,
        "csm_email": req.csmEmail,
        "accounts_data": req.accountsData,
        "engagement_data": req.accountEngagementData,
        "transcription_samples": req.transcriptionSamples,
        "semantic_insights": req.semanticInsights,
        "days_back": req.daysBack or 180,
        "calendar_connected": req.calendarConnected or False,
    }


def _csm_response_fields(result: Dict[str, Any]) -> Dict[str, Any]:
    """Build response fields for CSM coaching crew."""
    return {
        "csm_name": result.get("csm_name"),
        "csm_email": result.get("csm_email"),
        "accounts_analyzed": result.get("accounts_analyzed"),
        "provider": result.get("provider"),
        "model": result.get("model"),
    }


def _sc_run_params(req: SCCoachingRequest) -> Dict[str, Any]:
    """Build run params for SC coaching crew."""
    return {
        "sc_name": req.scName,
        "sc_email": req.scEmail,
        "opportunities_data": req.opportunitiesData,
        "demo_transcripts": req.demoTranscripts,
        "discovery_transcripts": req.discoveryTranscripts,
        "deal_outcomes": req.dealOutcomes,
        "days_back": req.daysBack or 180,
    }


def _sc_response_fields(result: Dict[str, Any]) -> Dict[str, Any]:
    """Build response fields for SC coaching crew."""
    return {
        "sc_name": result.get("sc_name"),
        "sc_email": result.get("sc_email"),
        "opportunities_analyzed": result.get("opportunities_analyzed"),
        "provider": result.get("provider"),
        "model": result.get("model"),
    }


def _sdr_run_params(req: SDRCoachingRequest) -> Dict[str, Any]:
    """Build run params for SDR coaching crew."""
    return {
        "sdr_name": req.sdrName,
        "sdr_email": req.sdrEmail,
        "performance_metrics": req.performanceMetrics,
        "lead_pipeline_analysis": req.leadPipelineAnalysis,
        "opportunity_analysis": req.opportunityAnalysis,
        "sequence_data": req.sequenceData,
        "intent_metrics": req.intentMetrics,
        "days_back": req.daysBack or 30,
    }


def _sdr_response_fields(result: Dict[str, Any]) -> Dict[str, Any]:
    """Build response fields for SDR coaching crew."""
    return {
        "sdr_name": result.get("sdr_name"),
        "sdr_email": result.get("sdr_email"),
        "provider": result.get("provider"),
        "model": result.get("model"),
    }


# =============================================================================
# Endpoint Registration
# =============================================================================

SUPPORT_CONFIG = CoachingEndpointConfig(
    crew_class=SupportCoachingCrew,
    request_model=SupportCoachingRequest,
    role_name="support",
    person_name_field="agentName",
    person_email_field="agentEmail",
    run_params_builder=_support_run_params,
    response_fields_builder=_support_response_fields,
)

PM_CONFIG = CoachingEndpointConfig(
    crew_class=PMCoachingCrew,
    request_model=PMCoachingRequest,
    role_name="PM",
    person_name_field="pmName",
    person_email_field="pmEmail",
    run_params_builder=_pm_run_params,
    response_fields_builder=_pm_response_fields,
    use_threaded_streaming=True,
    debug_logging=_pm_debug_logging,
)

AE_CONFIG = CoachingEndpointConfig(
    crew_class=AECoachingCrew,
    request_model=AECoachingRequest,
    role_name="AE",
    person_name_field="aeName",
    person_email_field="aeEmail",
    run_params_builder=_ae_run_params,
    response_fields_builder=_ae_response_fields,
)

CSM_CONFIG = CoachingEndpointConfig(
    crew_class=CSMCoachingCrew,
    request_model=CSMCoachingRequest,
    role_name="CSM",
    person_name_field="csmName",
    person_email_field="csmEmail",
    run_params_builder=_csm_run_params,
    response_fields_builder=_csm_response_fields,
)

SC_CONFIG = CoachingEndpointConfig(
    crew_class=SCCoachingCrew,
    request_model=SCCoachingRequest,
    role_name="SC",
    person_name_field="scName",
    person_email_field="scEmail",
    run_params_builder=_sc_run_params,
    response_fields_builder=_sc_response_fields,
)

SDR_CONFIG = CoachingEndpointConfig(
    crew_class=SDRCoachingCrew,
    request_model=SDRCoachingRequest,
    role_name="SDR",
    person_name_field="sdrName",
    person_email_field="sdrEmail",
    run_params_builder=_sdr_run_params,
    response_fields_builder=_sdr_response_fields,
)


# Register endpoints with router
@router.post("/support-coaching")
async def run_support_coaching_crew(request: Request):
    """Run the support agent coaching analysis crew with optional streaming."""
    handler = create_coaching_endpoint(SUPPORT_CONFIG)
    return await handler(request)


@router.post("/pm-coaching")
async def run_pm_coaching_crew(request: Request):
    """Run the Implementation Consultant (PM) coaching analysis crew with optional streaming."""
    handler = create_coaching_endpoint(PM_CONFIG)
    return await handler(request)


@router.post("/ae-coaching")
async def run_ae_coaching_crew(request: Request):
    """Run the Account Executive coaching analysis crew with optional streaming."""
    handler = create_coaching_endpoint(AE_CONFIG)
    return await handler(request)


@router.post("/csm-coaching")
async def run_csm_coaching_crew(request: Request):
    """Run the Customer Success Manager coaching analysis crew with optional streaming."""
    handler = create_coaching_endpoint(CSM_CONFIG)
    return await handler(request)


@router.post("/sc-coaching")
async def run_sc_coaching_crew(request: Request):
    """Run the Solutions Consultant coaching analysis crew with optional streaming."""
    handler = create_coaching_endpoint(SC_CONFIG)
    return await handler(request)


@router.post("/sdr-coaching")
async def run_sdr_coaching_crew(request: Request):
    """Run the SDR (Sales Development Representative) coaching analysis crew with optional streaming."""
    handler = create_coaching_endpoint(SDR_CONFIG)
    return await handler(request)
