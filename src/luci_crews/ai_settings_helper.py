"""
AI Settings Helper

Fetches AI model settings from Supabase based on user's management level.
This allows different management levels to use different AI models.
"""

import os
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from supabase import create_client, Client

logger = logging.getLogger(__name__)

# Default AI settings if database lookup fails
# Note: Using OpenAI as default since it's most reliable
# Google's gemini-1.5-flash was deprecated in late 2025
DEFAULT_AI_SETTINGS = {
    "provider": "openai",
    "model_id": "gpt-4o-mini",
    "temperature": 0.7,
    "max_tokens": 4096,
}

# Map provider names to CrewAI-compatible model prefixes
PROVIDER_MODEL_PREFIXES = {
    "openai": "",  # OpenAI models don't need prefix in CrewAI
    "anthropic": "anthropic/",
    "google": "gemini/",
}


@dataclass
class AISettings:
    """AI settings for a user based on their management level."""
    provider: str
    model_id: str
    temperature: float
    max_tokens: int

    def get_crewai_model_name(self) -> str:
        """Get the model name in CrewAI format."""
        prefix = PROVIDER_MODEL_PREFIXES.get(self.provider, "")
        return f"{prefix}{self.model_id}"

    def get_api_key_env_var(self) -> str:
        """Get the environment variable name for this provider's API key."""
        # Note: Google's genai library uses GOOGLE_API_KEY by default
        key_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
        }
        return key_map.get(self.provider, "OPENAI_API_KEY")


def get_supabase_client() -> Optional[Client]:
    """Get Supabase client for database access."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if url and key:
        return create_client(url, key)
    return None


def get_user_management_level(supabase: Client, user_id: str) -> Optional[str]:
    """Get the management level for a user."""
    try:
        result = supabase.table("users").select("management_level").eq("id", user_id).single().execute()
        if result.data:
            return result.data.get("management_level", "individual_contributor")
    except Exception as e:
        logger.warning(f"Failed to get user management level: {e}")
    return "individual_contributor"


def get_ai_settings_for_level(supabase: Client, management_level: str) -> AISettings:
    """Get AI settings for a specific management level."""
    try:
        result = supabase.table("management_level_ai_settings").select(
            "temperature, max_tokens, ai_models(provider, model_id)"
        ).eq("management_level", management_level).single().execute()

        if result.data and result.data.get("ai_models"):
            model_data = result.data["ai_models"]
            return AISettings(
                provider=model_data.get("provider", DEFAULT_AI_SETTINGS["provider"]),
                model_id=model_data.get("model_id", DEFAULT_AI_SETTINGS["model_id"]),
                temperature=float(result.data.get("temperature", DEFAULT_AI_SETTINGS["temperature"])),
                max_tokens=int(result.data.get("max_tokens", DEFAULT_AI_SETTINGS["max_tokens"])),
            )
    except Exception as e:
        logger.warning(f"Failed to get AI settings for level {management_level}: {e}")

    # Return defaults
    return AISettings(**DEFAULT_AI_SETTINGS)


def get_ai_settings_for_user(user_id: str) -> AISettings:
    """
    Get AI settings for a user based on their management level.

    Args:
        user_id: The user's ID

    Returns:
        AISettings object with provider, model, temperature, and max_tokens
    """
    supabase = get_supabase_client()
    if not supabase:
        logger.warning("Supabase client not available, using default AI settings")
        return AISettings(**DEFAULT_AI_SETTINGS)

    # Get user's management level
    management_level = get_user_management_level(supabase, user_id)
    logger.info(f"User {user_id} has management level: {management_level}")

    # Get AI settings for that level
    settings = get_ai_settings_for_level(supabase, management_level)
    logger.info(f"AI settings for {management_level}: {settings.provider}/{settings.model_id}")

    return settings


def create_llm_for_user(user_id: str):
    """
    Create a CrewAI LLM instance configured for the user's management level.

    Args:
        user_id: The user's ID

    Returns:
        CrewAI LLM instance
    """
    from crewai import LLM

    settings = get_ai_settings_for_user(user_id)
    model_name = settings.get_crewai_model_name()
    api_key = os.getenv(settings.get_api_key_env_var())

    logger.info(f"Creating LLM for user {user_id}: model={model_name}, temp={settings.temperature}")

    return LLM(
        model=model_name,
        api_key=api_key,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
    )
