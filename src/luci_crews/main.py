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
