"""
AI Settings Helper

Fetches AI model settings from Supabase based on user's management level.
This allows different management levels to use different AI models.

Includes fallback logic for when a provider hits quota/rate limits.
"""

import os
import logging
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass
from supabase import create_client, Client

logger = logging.getLogger(__name__)

# Default AI settings if database lookup fails
# Note: Using OpenAI as default since it's most reliable
# Google's gemini-1.5-flash was deprecated in late 2025
DEFAULT_AI_SETTINGS = {
    "provider": "openai",
    "model_id": os.getenv("FAST_LLM_MODEL", "gpt-4o-mini"),
    "temperature": 0.7,
    "max_tokens": 4096,
}

# Map provider names to CrewAI-compatible model prefixes
PROVIDER_MODEL_PREFIXES = {
    "openai": "",  # OpenAI models don't need prefix in CrewAI
    "anthropic": "anthropic/",
    "google": "gemini/",
}

# Fallback provider chain - ordered by preference
# Each entry: (provider, model_id, env_var_for_api_key)
FALLBACK_PROVIDERS = [
    ("openai", os.getenv("FAST_LLM_MODEL", "gpt-4o-mini"), "OPENAI_API_KEY"),
    ("anthropic", os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"), "ANTHROPIC_API_KEY"),
    ("google", os.getenv("GOOGLE_MODEL", "gemini-1.5-flash"), "GOOGLE_API_KEY"),
]

# Error patterns that indicate quota/rate limit issues
QUOTA_ERROR_PATTERNS = [
    "insufficient_quota",
    "rate_limit",
    "429",
    "quota exceeded",
    "billing",
    "exceeded your current quota",
    "resource_exhausted",
    "too many requests",
]


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


def is_quota_error(error: Exception) -> bool:
    """
    Check if an error is a quota/rate limit error that should trigger fallback.

    Args:
        error: The exception to check

    Returns:
        True if this is a quota/rate limit error
    """
    error_str = str(error).lower()
    return any(pattern in error_str for pattern in QUOTA_ERROR_PATTERNS)


def get_available_providers() -> List[tuple]:
    """
    Get list of providers that have API keys configured.

    Returns:
        List of (provider, model_id, api_key) tuples for available providers
    """
    available = []
    for provider, model_id, env_var in FALLBACK_PROVIDERS:
        api_key = os.getenv(env_var)
        if api_key:
            available.append((provider, model_id, api_key))
        else:
            logger.debug(f"Provider {provider} not available: {env_var} not set")
    return available


def create_llm_for_provider(provider: str, model_id: str, api_key: str, temperature: float = 0.7, max_tokens: int = 4096):
    """
    Create a CrewAI LLM instance for a specific provider.

    Args:
        provider: Provider name (openai, anthropic, google)
        model_id: Model ID for the provider
        api_key: API key for the provider
        temperature: LLM temperature
        max_tokens: Max tokens for response

    Returns:
        CrewAI LLM instance
    """
    from crewai import LLM

    prefix = PROVIDER_MODEL_PREFIXES.get(provider, "")
    model_name = f"{prefix}{model_id}"

    logger.info(f"Creating LLM for provider {provider}: model={model_name}")

    return LLM(
        model=model_name,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def run_with_fallback(
    crew_factory: Callable,
    run_args: Dict[str, Any],
    user_id: Optional[str] = None,
    max_retries: int = 3,
) -> Dict[str, Any]:
    """
    Run a crew with automatic fallback to other providers on quota errors.

    This function attempts to run a crew, and if it fails with a quota/rate limit
    error, it automatically retries with the next available provider.

    Args:
        crew_factory: A callable that takes an LLM and returns a crew instance
        run_args: Arguments to pass to crew.run()
        user_id: Optional user ID for user-specific settings
        max_retries: Maximum number of providers to try

    Returns:
        The crew result dict

    Raises:
        Exception: If all providers fail
    """
    available_providers = get_available_providers()

    if not available_providers:
        raise RuntimeError("No AI providers configured. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY.")

    last_error = None
    providers_tried = []

    for i, (provider, model_id, api_key) in enumerate(available_providers[:max_retries]):
        providers_tried.append(provider)

        try:
            logger.info(f"Attempting with provider {provider} (attempt {i + 1}/{min(len(available_providers), max_retries)})")

            # Create LLM for this provider
            llm = create_llm_for_provider(provider, model_id, api_key)

            # Create and run the crew
            crew = crew_factory(llm)
            result = crew.run(**run_args)

            logger.info(f"Successfully completed with provider {provider}")

            # Add metadata about which provider was used
            if isinstance(result, dict):
                result["_provider_used"] = provider
                result["_providers_tried"] = providers_tried

            return result

        except Exception as e:
            last_error = e
            error_str = str(e)

            if is_quota_error(e):
                logger.warning(f"Provider {provider} quota/rate limit error: {error_str[:200]}")
                if i + 1 < min(len(available_providers), max_retries):
                    logger.info(f"Falling back to next provider...")
                    continue
                else:
                    logger.error(f"All providers exhausted after quota errors")
            else:
                # Non-quota error - don't retry with other providers
                logger.error(f"Provider {provider} failed with non-quota error: {error_str[:200]}")
                raise

    # All providers failed
    raise RuntimeError(
        f"All AI providers failed. Tried: {', '.join(providers_tried)}. "
        f"Last error: {str(last_error)[:200]}"
    )
