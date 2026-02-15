"""Analysis crew endpoints for project, opportunity, and support analysis.

This module contains endpoints for:
- Project sentiment analysis
- Unified project analysis (implementation + sentiment)
- Opportunity strategy analysis
- Competitive intelligence analysis
- Support resolution analysis
"""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request

from ..models import (
    ProjectSentimentRequest,
    ProjectAnalysisRequest,
    OpportunityStrategyRequest,
    CompetitiveRequest,
    SupportResolutionRequest,
)
from ..crews.project_sentiment_crew import ProjectSentimentCrew
from ..crews.project_analysis_crew import ProjectAnalysisCrew
from ..crews.opportunity_strategy_crew import OpportunityStrategyCrew
from ..crews.competitive_crew import CompetitiveCrew
from ..crews.support_resolution_crew import SupportResolutionCrew
from ..utils.streaming import (
    SimpleStreamingContext,
    create_streaming_response,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/crew", tags=["analysis"])


@router.post("/project-sentiment")
async def run_project_sentiment_crew(request: Request):
    """Run the project sentiment analysis crew with optional streaming."""
    stream = request.query_params.get("stream", "false").lower() == "true"

    try:
        body = await request.json()
        req = ProjectSentimentRequest(**body)
        logger.info(f"Running project sentiment crew for project: {req.salesforceProjectId}")

        crew = ProjectSentimentCrew(user_id=req.userId)

        if stream:
            ctx = SimpleStreamingContext()

            async def generate():
                try:
                    yield ctx.init_message("Starting analysis...")
                    result = crew.run(
                        salesforce_project_id=req.salesforceProjectId,
                        salesforce_account_id=req.salesforceAccountId,
                        transcription_ids=req.transcriptionIds or [],
                        force_refresh=req.forceRefresh or False,
                        step_callback=ctx.step_callback,
                    )
                    for msg in ctx.get_progress_messages():
                        yield msg
                    logger.info(f"Project sentiment crew completed in {ctx.execution_time:.2f}s")
                    yield ctx.result_message(result, input_hash=result.get('input_hash'),
                        transcription_count=result.get('transcription_count'),
                        transcription_length=result.get('transcription_length'),
                        transcription_ids=result.get('transcription_ids'),
                        provider=result.get('provider'), model=result.get('model'))
                except Exception as e:
                    logger.error(f"Project sentiment crew failed: {str(e)}")
                    yield ctx.error_message(str(e))

            return create_streaming_response(generate())
        else:
            start_time = datetime.utcnow()
            result = crew.run(
                salesforce_project_id=req.salesforceProjectId,
                salesforce_account_id=req.salesforceAccountId,
                transcription_ids=req.transcriptionIds or [],
                force_refresh=req.forceRefresh or False,
            )
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"Project sentiment crew completed in {execution_time:.2f}s")
            return {
                "success": True, "result": result.get("result"),
                "input_hash": result.get("input_hash"),
                "transcription_count": result.get("transcription_count"),
                "transcription_length": result.get("transcription_length"),
                "transcription_ids": result.get("transcription_ids"),
                "provider": result.get("provider"), "model": result.get("model"),
                "execution_time": execution_time,
            }

    except Exception as e:
        logger.error(f"Project sentiment crew failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/project-analysis")
async def run_project_analysis_crew(request: Request):
    """Run the unified project analysis crew.

    This crew consolidates implementation and sentiment analysis into a single
    comprehensive project health assessment.
    """
    stream = request.query_params.get("stream", "false").lower() == "true"

    try:
        body = await request.json()
        req = ProjectAnalysisRequest(**body)
        project_name = req.project.get("project_name", "Unknown") if req.project else "Unknown"
        logger.info(f"Running project analysis crew for: {project_name}")

        crew = ProjectAnalysisCrew()

        if stream:
            ctx = SimpleStreamingContext()

            # Adapter: project-analysis crew uses send_progress(stage, message)
            # but SimpleStreamingContext expects step_callback(message)
            def send_progress_adapter(stage: str, message: str):
                ctx.step_callback(f"[{stage}] {message}")

            async def generate():
                try:
                    yield ctx.init_message("Starting project analysis...")
                    result = crew.run(
                        project=req.project or {},
                        project_owner=req.projectOwner or {"type": "unknown"},
                        mavenlink_tasks=req.mavenlinkTasks or [],
                        mavenlink_time_entries=req.mavenlinkTimeEntries or [],
                        transcripts=req.transcripts or [],
                        call_activity=req.callActivity or {},
                        email_activity=req.emailActivity,
                        send_progress=send_progress_adapter,
                    )
                    for msg in ctx.get_progress_messages():
                        yield msg
                    logger.info(f"Project analysis crew completed in {ctx.execution_time:.2f}s")
                    yield ctx.result_message(result)
                except Exception as e:
                    logger.error(f"Project analysis crew failed: {str(e)}")
                    yield ctx.error_message(str(e))

            return create_streaming_response(generate())
        else:
            start_time = datetime.utcnow()
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
            return {"success": True, "result": result, "execution_time": execution_time}

    except Exception as e:
        logger.error(f"Project analysis crew failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/opportunity")
async def run_opportunity_strategy_crew(request: Request):
    """Run the opportunity strategy analysis crew with optional streaming."""
    stream = request.query_params.get("stream", "false").lower() == "true"

    try:
        body = await request.json()
        req = OpportunityStrategyRequest(**body)
        logger.info(f"Running opportunity strategy crew for: {req.opportunityId}")

        crew = OpportunityStrategyCrew(user_id=req.userId)

        if stream:
            ctx = SimpleStreamingContext()

            async def generate():
                try:
                    yield ctx.init_message("Starting strategic analysis...")
                    result = crew.run(
                        opportunity_id=req.opportunityId,
                        user_id=req.userId,
                        force_refresh=req.forceRefresh or False,
                        step_callback=ctx.step_callback,
                        opportunity_data=req.opportunityData.model_dump() if req.opportunityData else None,
                        transcription_data=[t.model_dump() for t in req.transcriptionData] if req.transcriptionData else None,
                        salesforce_account_id=req.salesforceAccountId,
                        presales_context=req.presalesContext.model_dump() if req.presalesContext else None,
                    )
                    for msg in ctx.get_progress_messages():
                        yield msg
                    logger.info(f"Opportunity strategy crew completed in {ctx.execution_time:.2f}s")
                    yield ctx.result_message(result.get('result'),
                        input_hash=result.get('input_hash'),
                        opportunity_name=result.get('opportunity_name'),
                        account_name=result.get('account_name'),
                        provider=result.get('provider'), model=result.get('model'))
                except Exception as e:
                    logger.error(f"Opportunity strategy crew failed: {str(e)}")
                    yield ctx.error_message(str(e))

            return create_streaming_response(generate())
        else:
            start_time = datetime.utcnow()
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
                "success": True, "result": result.get("result"),
                "input_hash": result.get("input_hash"),
                "opportunity_name": result.get("opportunity_name"),
                "account_name": result.get("account_name"),
                "provider": result.get("provider"), "model": result.get("model"),
                "execution_time": execution_time,
            }

    except Exception as e:
        logger.error(f"Opportunity strategy crew failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/competitive")
async def run_competitive_crew(request: Request):
    """Run the competitive intelligence analysis crew."""
    stream = request.query_params.get("stream", "false").lower() == "true"

    try:
        body = await request.json()
        req = CompetitiveRequest(**body)
        logger.info(f"Running competitive crew for {len(req.companies)} companies (type: {req.analysisType})")

        crew = CompetitiveCrew(user_id=req.userId)
        companies_data = [c.model_dump() for c in req.companies]

        if stream:
            ctx = SimpleStreamingContext()

            async def generate():
                try:
                    yield ctx.init_message("Starting competitive analysis...")
                    result = crew.run(
                        companies=companies_data,
                        analysis_type=req.analysisType or "comparative",
                        step_callback=ctx.step_callback,
                    )
                    for msg in ctx.get_progress_messages():
                        yield msg
                    logger.info(f"Competitive crew completed in {ctx.execution_time:.2f}s")
                    yield ctx.result_message(result.get('result'),
                        analysis=result.get('analysis'),
                        analysisType=result.get('analysisType'),
                        provider=result.get('provider'), model=result.get('model'))
                except Exception as e:
                    logger.error(f"Competitive crew failed: {str(e)}")
                    yield ctx.error_message(str(e))

            return create_streaming_response(generate())
        else:
            start_time = datetime.utcnow()
            result = crew.run(
                companies=companies_data,
                analysis_type=req.analysisType or "comparative",
            )
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"Competitive crew completed in {execution_time:.2f}s")
            return {
                "success": True, "result": result.get("result"),
                "analysis": result.get("analysis"),
                "analysisType": result.get("analysisType"),
                "provider": result.get("provider"), "model": result.get("model"),
                "execution_time": execution_time,
            }

    except Exception as e:
        logger.error(f"Competitive crew failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/support_resolution")
async def run_support_resolution_crew(request: Request):
    """Run the support resolution analysis crew with optional streaming."""
    stream = request.query_params.get("stream", "false").lower() == "true"

    try:
        body = await request.json()
        req = SupportResolutionRequest(**body)
        logger.info(f"Running support resolution crew for case: {req.caseSubject[:50] if req.caseSubject else 'Unknown'}...")

        crew = SupportResolutionCrew(user_id=req.userId)

        if stream:
            ctx = SimpleStreamingContext()

            async def generate():
                try:
                    yield ctx.init_message("Analyzing case...")
                    result = crew.run(
                        case_subject=req.caseSubject,
                        case_description=req.caseDescription,
                        case_type=req.caseType,
                        case_priority=req.casePriority,
                        account_name=req.accountName,
                        contact_name=req.contactName,
                        step_callback=ctx.step_callback,
                    )
                    for msg in ctx.get_progress_messages():
                        yield msg
                    logger.info(f"Support resolution crew completed in {ctx.execution_time:.2f}s")
                    yield ctx.result_message(result.get('result'))
                except Exception as e:
                    logger.error(f"Support resolution crew failed: {str(e)}")
                    yield ctx.error_message(str(e))

            return create_streaming_response(generate())
        else:
            start_time = datetime.utcnow()
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
            return {"success": True, "result": result.get("result"), "execution_time": execution_time}

    except Exception as e:
        logger.error(f"Support resolution crew failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/support_training")
async def run_support_training_crew(request: Request):
    """Alias for support_resolution - provides case analysis for training purposes."""
    return await run_support_resolution_crew(request)
