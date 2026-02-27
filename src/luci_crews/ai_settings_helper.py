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
from enum import Enum


class TaskPriority(Enum):
    """Task importance level for model selection.

    LOW: Background batch tasks (embeddings, nightly sync)
         Uses cheapest available model regardless of user role.

    MEDIUM: User-triggered analysis (call analysis, project sentiment)
            Uses user's assigned model with quality-ordered fallback.

    HIGH: Critical automated tasks (dashboard scores, executive briefings)
          Uses user's assigned model with quality-ordered fallback.
    """
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ModelTier(Enum):
    """Model capability tier for fallback ordering."""
    ECONOMY = "ECONOMY"
    STANDARD = "STANDARD"
    PREMIUM = "PREMIUM"


# Tier ordering for fallback (highest to lowest)
TIER_ORDER = [ModelTier.PREMIUM, ModelTier.STANDARD, ModelTier.ECONOMY]

# Deprecated model upgrades — automatically replace retired models
# Key = old model ID (from database), Value = replacement model ID
DEPRECATED_MODEL_UPGRADES = {
    "claude-3-5-sonnet-20241022": "claude-sonnet-4-6-20260217",
    "claude-3-5-haiku-20241022": "claude-haiku-4-5-20251001",
    "gemini-1.5-flash": "gemini-2.0-flash",
    "gemini-1.5-pro": "gemini-2.0-flash",
}

# Model tier classification (mirrors database, used as fallback)
# Only includes models verified to exist as of Feb 2026
MODEL_TIERS = {
    # PREMIUM - highest capability
    "claude-sonnet-4-6-20260217": ModelTier.PREMIUM,
    "claude-sonnet-4-5-20250929": ModelTier.PREMIUM,
    "gpt-4.1": ModelTier.PREMIUM,
    "gpt-4o": ModelTier.PREMIUM,

    # STANDARD - balanced
    "claude-haiku-4-5-20251001": ModelTier.STANDARD,
    "gpt-4.1-mini": ModelTier.STANDARD,
    "gpt-4o-mini": ModelTier.STANDARD,
    "gemini-2.0-flash": ModelTier.STANDARD,
    "gemini-2.5-flash": ModelTier.STANDARD,

    # ECONOMY - cheapest
    "gpt-4.1-nano": ModelTier.ECONOMY,
}


def get_model_tier(model_id: str) -> ModelTier:
    """Get the tier for a model, defaulting to STANDARD if unknown."""
    return MODEL_TIERS.get(model_id, ModelTier.STANDARD)


# Provider ordering within each tier (for fallback diversity)
# Uses verified existing models only
TIER_PROVIDERS = {
    ModelTier.PREMIUM: [
        ("anthropic", "claude-sonnet-4-5-20250929"),
        ("openai", "gpt-4.1"),
        ("google", "gemini-2.0-flash"),
    ],
    ModelTier.STANDARD: [
        ("openai", "gpt-4.1-mini"),
        ("google", "gemini-2.0-flash"),
        ("anthropic", "claude-haiku-4-5-20251001"),
    ],
    ModelTier.ECONOMY: [
        ("openai", "gpt-4.1-nano"),
    ],
}


logger = logging.getLogger(__name__)

# Default AI settings if database lookup fails
# Note: Using OpenAI as default since it's most reliable and stable
# Updated Feb 2026: Claude 3.5 Sonnet (Oct 2025) and Gemini 1.5 Flash retired
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
# NOTE: Model versions updated Feb 2026 - Claude 3.5 and Gemini 1.5 were retired
# NOTE: Model IDs here should NOT include provider prefixes - those are added automatically
FALLBACK_PROVIDERS = [
    ("openai", os.getenv("FAST_LLM_MODEL", "gpt-4o-mini"), "OPENAI_API_KEY"),
    # Claude 3.5 Sonnet retired Oct 2025 - upgraded to Claude Sonnet 4.6 (released Feb 17, 2026)
    ("anthropic", os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6-20260217"), "ANTHROPIC_API_KEY"),
    # Gemini 1.5 Flash retired - upgraded to Gemini 2.5 Flash (stable, fast, cost-efficient)
    # Note: "gemini/" prefix is added automatically by create_llm_for_provider
    ("google", os.getenv("GOOGLE_MODEL", "gemini-2.5-flash"), "GOOGLE_API_KEY"),
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
    "credit balance",  # Anthropic credit balance errors
    "credits",  # General credit-based quota errors
]

# Error patterns that indicate ACCOUNT-WIDE issues (skip ALL models from this provider)
ACCOUNT_EXHAUSTED_PATTERNS = [
    "credit balance is too low",  # Anthropic: no credits left
    "billing hard limit",  # OpenAI: spending limit hit
    "account.*suspended",  # Any provider: account issues
    "api key.*invalid",  # Bad API key
    "authentication failed",
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
            model_id = model_data.get("model_id", DEFAULT_AI_SETTINGS["model_id"])
            provider = model_data.get("provider", DEFAULT_AI_SETTINGS["provider"])

            # Auto-upgrade deprecated models
            if model_id in DEPRECATED_MODEL_UPGRADES:
                new_model = DEPRECATED_MODEL_UPGRADES[model_id]
                logger.warning(f"Model {model_id} is deprecated, upgrading to {new_model}")
                model_id = new_model

            return AISettings(
                provider=provider,
                model_id=model_id,
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

    Falls back to available providers if the user's assigned provider has no API key.

    Args:
        user_id: The user's ID

    Returns:
        CrewAI LLM instance
    """
    from crewai import LLM

    settings = get_ai_settings_for_user(user_id)
    model_name = settings.get_crewai_model_name()
    api_key = os.getenv(settings.get_api_key_env_var())

    # If the user's assigned provider has no API key, fall back to an available one
    if not api_key:
        logger.warning(f"User {user_id}'s assigned provider ({settings.provider}) has no API key, falling back")
        available = get_available_providers()
        if not available:
            raise RuntimeError("No AI providers configured. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY.")
        fallback_provider, fallback_model, fallback_key = available[0]
        logger.info(f"Falling back to {fallback_provider}/{fallback_model} for user {user_id}")
        return create_llm_for_provider(fallback_provider, fallback_model, fallback_key,
                                       settings.temperature, settings.max_tokens)

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


def is_account_exhausted_error(error: Exception) -> bool:
    """
    Check if an error indicates the ENTIRE provider account is exhausted.

    This is different from rate limits - credit balance errors mean NO models
    from this provider will work until credits are purchased.

    Args:
        error: The exception to check

    Returns:
        True if ALL models from this provider should be skipped
    """
    error_str = str(error).lower()
    return any(pattern in error_str for pattern in ACCOUNT_EXHAUSTED_PATTERNS)


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

    # Safety net: auto-upgrade deprecated models regardless of source
    if model_id in DEPRECATED_MODEL_UPGRADES:
        new_model = DEPRECATED_MODEL_UPGRADES[model_id]
        logger.warning(f"create_llm_for_provider: Model {model_id} is deprecated, upgrading to {new_model}")
        model_id = new_model

    prefix = PROVIDER_MODEL_PREFIXES.get(provider, "")
    model_name = f"{prefix}{model_id}"

    logger.info(f"Creating LLM for provider {provider}: model={model_name}")

    return LLM(
        model=model_name,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def build_fallback_chain(
    starting_model: str,
    starting_provider: str,
    task_priority: TaskPriority,
) -> List[tuple]:
    """
    Build a quality-ordered fallback chain starting from the given model.

    For HIGH/MEDIUM priority: Start with assigned model, try same-tier alternates,
    then step down to lower tiers.

    For LOW priority: Start with cheapest (ECONOMY), work up if needed.

    Returns:
        List of (provider, model_id, api_key_env_var) tuples
    """
    chain = []
    seen = set()

    if task_priority == TaskPriority.LOW:
        # Cost-ordered: Start with cheapest
        for tier in reversed(TIER_ORDER):  # ECONOMY -> STANDARD -> PREMIUM
            for provider, model_id in TIER_PROVIDERS.get(tier, []):
                env_var = f"{provider.upper()}_API_KEY"
                if env_var == "GOOGLE_API_KEY":
                    env_var = "GOOGLE_API_KEY"
                api_key = os.getenv(env_var)
                if api_key and (provider, model_id) not in seen:
                    chain.append((provider, model_id, env_var))
                    seen.add((provider, model_id))
    else:
        # Quality-ordered: Start with assigned model
        starting_tier = get_model_tier(starting_model)
        env_var_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
        }

        # First, add the assigned model
        env_var = env_var_map.get(starting_provider, "OPENAI_API_KEY")
        if os.getenv(env_var):
            chain.append((starting_provider, starting_model, env_var))
            seen.add((starting_provider, starting_model))

        # Then add same-tier alternatives from other providers
        starting_tier_idx = TIER_ORDER.index(starting_tier)

        for tier in TIER_ORDER[starting_tier_idx:]:  # Same tier and below
            for provider, model_id in TIER_PROVIDERS.get(tier, []):
                env_var = env_var_map.get(provider, "OPENAI_API_KEY")
                api_key = os.getenv(env_var)
                if api_key and (provider, model_id) not in seen:
                    chain.append((provider, model_id, env_var))
                    seen.add((provider, model_id))

    return chain


def get_llm_for_task(
    task_priority: TaskPriority,
    user_id: Optional[str] = None,
    task_name: Optional[str] = None,
) -> tuple:
    """
    Get model configuration for a task based on priority and user role.

    This is the SINGLE ENTRY POINT for all AI model selection.

    Args:
        task_priority: Importance level (LOW/MEDIUM/HIGH)
        user_id: Optional user ID for role-based ceiling
        task_name: Optional name for logging

    Returns:
        Tuple of (provider, model_id, api_key_env_var, fallback_chain)
    """
    # Get user's assigned model (if user_id provided)
    if user_id and task_priority != TaskPriority.LOW:
        settings = get_ai_settings_for_user(user_id)
        starting_provider = settings.provider
        starting_model = settings.model_id
        logger.info(f"[{task_name or 'unknown'}] User {user_id} assigned: {starting_provider}/{starting_model}")
    else:
        # LOW priority or no user: use cheapest
        starting_provider = "openai"
        starting_model = "gpt-4.1-mini"
        logger.info(f"[{task_name or 'unknown'}] Using economy model for {task_priority.value} priority")

    # Build the fallback chain
    fallback_chain = build_fallback_chain(
        starting_model=starting_model,
        starting_provider=starting_provider,
        task_priority=task_priority,
    )

    if not fallback_chain:
        raise RuntimeError("No AI providers configured. Set API keys for OpenAI, Anthropic, or Google.")

    primary = fallback_chain[0]
    logger.info(f"[{task_name or 'unknown'}] Primary: {primary[0]}/{primary[1]}, Fallbacks: {len(fallback_chain)-1}")

    return primary[0], primary[1], primary[2], fallback_chain


def run_with_smart_fallback(
    crew_factory: Callable,
    run_args: Dict[str, Any],
    task_priority: TaskPriority,
    user_id: Optional[str] = None,
    task_name: Optional[str] = None,
    max_retries: int = 6,
) -> Dict[str, Any]:
    """
    Run a crew with intelligent model selection and quality-ordered fallback.

    This function:
    1. Determines the best starting model based on task priority and user role
    2. Builds a quality-ordered fallback chain
    3. Tries each model in sequence until success
    4. Logs usage for cost tracking
    5. Skips ALL models from a provider when account-wide errors occur (e.g., credit exhausted)

    Args:
        crew_factory: Callable that takes an LLM and returns a crew instance
        run_args: Arguments to pass to crew.run()
        task_priority: Task importance (LOW/MEDIUM/HIGH)
        user_id: Optional user ID for role-based model ceiling
        task_name: Optional name for logging
        max_retries: Maximum number of models to try

    Returns:
        The crew result dict with metadata about model used

    Raises:
        RuntimeError: If all models fail
    """
    # Get model configuration and fallback chain
    primary_provider, primary_model, _, fallback_chain = get_llm_for_task(
        task_priority=task_priority,
        user_id=user_id,
        task_name=task_name,
    )

    last_error = None
    providers_tried = []
    exhausted_providers = set()  # Track providers with account-wide failures

    attempt_num = 0
    for i, (provider, model_id, env_var) in enumerate(fallback_chain[:max_retries]):
        # Skip if this provider is exhausted (credit balance, billing, etc.)
        if provider in exhausted_providers:
            logger.info(f"[{task_name or 'crew'}] Skipping {provider}/{model_id} (provider exhausted)")
            continue

        attempt_num += 1
        providers_tried.append(f"{provider}/{model_id}")

        try:
            logger.info(f"[{task_name or 'crew'}] Attempt {attempt_num}/{min(len(fallback_chain), max_retries)}: {provider}/{model_id}")

            # Create LLM for this provider
            llm = create_llm_for_provider(provider, model_id, os.getenv(env_var))

            # Create and run the crew
            crew = crew_factory(llm)
            result = crew.run(**run_args)

            logger.info(f"[{task_name or 'crew'}] Success with {provider}/{model_id}")

            # Add metadata
            if isinstance(result, dict):
                result["_model_used"] = model_id
                result["_provider_used"] = provider
                result["_task_priority"] = task_priority.value
                result["_providers_tried"] = providers_tried
                result["_fallback_count"] = attempt_num - 1

            return result

        except Exception as e:
            last_error = e

            # Check for account-wide exhaustion (skip ALL models from this provider)
            if is_account_exhausted_error(e):
                logger.warning(f"[{task_name or 'crew'}] {provider} account exhausted (credits/billing), skipping all {provider} models")
                exhausted_providers.add(provider)
                continue
            elif is_quota_error(e):
                # Regular quota error (rate limit) - just try next model
                logger.warning(f"[{task_name or 'crew'}] {provider} quota/credit error, trying next...")
                continue
            else:
                # Non-quota error - log but still try next provider
                logger.error(f"[{task_name or 'crew'}] {provider} error: {str(e)[:200]}")
                # For non-quota errors, we could either:
                # 1. Raise immediately (strict)
                # 2. Try next provider (lenient)
                # Using lenient approach for better availability
                continue

    # All providers failed
    raise RuntimeError(
        f"All AI providers failed for {task_name or 'crew'}. "
        f"Tried: {', '.join(providers_tried)}. "
        f"Exhausted providers: {', '.join(exhausted_providers) or 'none'}. "
        f"Last error: {str(last_error)[:200]}"
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
