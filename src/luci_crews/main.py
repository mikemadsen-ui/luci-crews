"""
LUCI CrewAI Service - FastAPI Application

Provides API endpoints for running CrewAI crews and serves the CrewAI Studio UI.
"""

import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from .crews.sales_pipeline_crew import SalesPipelineCrew
from .crews.account_health_crew import AccountHealthCrew
from .crews.implementation_crew import ImplementationCrew
from .crews.sentiment_crew import SentimentCrew

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


class SentimentRequest(BaseModel):
    account_id: str
    account_name: str
    communications_data: Optional[str] = None
    support_data: Optional[str] = None
    meeting_notes: Optional[str] = None


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
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "0.1.0",
    }


@app.get("/")
async def root():
    """Root endpoint with service info."""
    return {
        "service": "LUCI CrewAI Service",
        "version": "0.1.0",
        "endpoints": {
            "health": "/health",
            "sales_pipeline": "/api/crew/sales_pipeline",
            "account_health": "/api/crew/account",
            "implementation": "/api/crew/implementation",
            "sentiment": "/api/crew/sentiment",
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


# =============================================================================
# Configuration Endpoints (for future Studio UI integration)
# =============================================================================

@app.get("/api/config/agents")
async def get_agents_config():
    """Get current agents configuration."""
    import yaml
    config_path = os.path.join(os.path.dirname(__file__), "config", "agents.yaml")

    try:
        with open(config_path, 'r') as f:
            agents = yaml.safe_load(f)
        return {"agents": agents}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/config/tasks")
async def get_tasks_config():
    """Get current tasks configuration."""
    import yaml
    config_path = os.path.join(os.path.dirname(__file__), "config", "tasks.yaml")

    try:
        with open(config_path, 'r') as f:
            tasks = yaml.safe_load(f)
        return {"tasks": tasks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/config/agents/{agent_name}")
async def update_agent_config(agent_name: str, config: dict):
    """Update an agent's configuration."""
    import yaml
    config_path = os.path.join(os.path.dirname(__file__), "config", "agents.yaml")

    try:
        with open(config_path, 'r') as f:
            agents = yaml.safe_load(f)

        if agent_name not in agents:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

        agents[agent_name].update(config)

        with open(config_path, 'w') as f:
            yaml.dump(agents, f, default_flow_style=False, allow_unicode=True)

        return {"success": True, "agent": agents[agent_name]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
