"""Health check and capabilities endpoints.

This module contains endpoints for:
- Health check for Railway deployment monitoring
- AI provider capabilities detection
- Root service information
"""

import os
from datetime import datetime

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
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


@router.get("/api/capabilities")
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


@router.get("/")
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
