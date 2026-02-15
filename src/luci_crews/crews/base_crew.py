"""
Base Crew Class

Provides shared initialization logic for all crew classes:
- LLM initialization with user-specific settings or defaults
- Configuration loading for agents and tasks
- Optional Supabase client initialization
- Common JSON parsing utilities
- Method stubs for subclass implementation
- Helper methods for agent/task creation
"""

import os
import logging
from typing import Optional, Dict, Any, List

from crewai import Agent, LLM, Task
from supabase import create_client, Client

from ..ai_settings_helper import create_llm_for_user, DEFAULT_AI_SETTINGS
from ..config_loader import load_agents_config, load_tasks_config
from ..utils import extract_json_from_llm_response

logger = logging.getLogger(__name__)


class BaseCrew:
    """Base class for all CrewAI crews with shared initialization logic.

    Subclasses should implement:
        - _create_agents(): Create and store Agent instances as instance attributes
        - _create_tasks(): Create and return Task instances for the crew

    Subclasses may use:
        - create_agent_from_config(): Helper to create an Agent from agents.yaml config
        - _get_agent_config(): Get raw agent configuration dict
        - _get_task_config(): Get raw task configuration dict
        - _parse_json_result(): Parse JSON from LLM response text
    """

    # Subclasses can set this to True to initialize Supabase client
    needs_supabase: bool = False

    def __init__(
        self,
        user_id: Optional[str] = None,
        llm: Optional[LLM] = None,
    ):
        """Initialize the crew with optional user-specific AI settings.

        Args:
            user_id: Optional user ID to fetch management-level AI settings.
                    If not provided, uses default settings.
            llm: Optional pre-configured LLM instance. If provided, user_id is
                 ignored for LLM creation. Useful for fallback scenarios.
        """
        self.user_id = user_id
        self.llm = self._init_llm(user_id, llm)
        self.agents_config = load_agents_config()
        self.tasks_config = load_tasks_config()

        # Initialize Supabase if needed by subclass
        if self.needs_supabase:
            self.supabase = self._init_supabase()
        else:
            self.supabase = None

    def _init_llm(
        self,
        user_id: Optional[str],
        llm: Optional[LLM],
    ) -> LLM:
        """Initialize LLM with user settings or defaults.

        Args:
            user_id: Optional user ID for user-specific settings
            llm: Optional pre-configured LLM to use directly

        Returns:
            Configured LLM instance
        """
        if llm is not None:
            # Use the provided LLM (for fallback scenarios)
            return llm

        if user_id:
            return create_llm_for_user(user_id)

        # Default LLM configuration
        return LLM(
            model=os.environ.get("OPENAI_MODEL_NAME", DEFAULT_AI_SETTINGS["model_id"]),
            api_key=os.environ.get("OPENAI_API_KEY"),
        )

    def _init_supabase(self) -> Optional[Client]:
        """Initialize Supabase client for database access.

        Returns:
            Supabase client or None if credentials not available
        """
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if url and key:
            return create_client(url, key)
        return None

    def _parse_json_result(
        self,
        result_text: str,
        default: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Parse JSON from the crew result, handling various formats.

        Args:
            result_text: Raw text output from the crew
            default: Default dict to return if parsing fails

        Returns:
            Parsed JSON dict or default
        """
        if default is None:
            default = {"raw_result": result_text}

        return extract_json_from_llm_response(result_text, default=default)

    def _get_agent_config(self, agent_name: str) -> Dict[str, Any]:
        """Get agent configuration by name with defaults.

        Args:
            agent_name: Name of the agent in agents.yaml

        Returns:
            Agent configuration dict
        """
        return self.agents_config.get(agent_name, {})

    def _get_task_config(self, task_name: str) -> Dict[str, Any]:
        """Get task configuration by name with defaults.

        Args:
            task_name: Name of the task in tasks.yaml

        Returns:
            Task configuration dict
        """
        return self.tasks_config.get(task_name, {})

    def create_agent_from_config(
        self,
        config_key: str,
        *,
        role_default: str = "Agent",
        goal_default: str = "Complete the assigned task",
        backstory_default: str = "An AI assistant specialized in the task at hand",
        verbose_default: bool = True,
        allow_delegation_default: bool = False,
        **extra_kwargs: Any,
    ) -> Agent:
        """Create an Agent instance from agents.yaml configuration.

        This helper encapsulates the common pattern of loading agent config
        and creating an Agent with appropriate defaults. It reduces boilerplate
        in crew implementations.

        Args:
            config_key: The key in agents.yaml to load configuration from
                (e.g., "account_health_analyst", "sdr_activity_analyst")
            role_default: Default role if not specified in config
            goal_default: Default goal if not specified in config
            backstory_default: Default backstory if not specified in config
            verbose_default: Default verbose setting if not specified in config
            allow_delegation_default: Default allow_delegation if not in config
            **extra_kwargs: Additional keyword arguments to pass to Agent constructor
                (e.g., tools, max_iter, max_rpm). These override config values.

        Returns:
            Configured Agent instance ready for use in a Crew

        Example:
            # Simple usage with defaults
            analyst = self.create_agent_from_config("account_health_analyst")

            # With custom defaults
            analyst = self.create_agent_from_config(
                "account_health_analyst",
                role_default="Account Analyst",
                goal_default="Analyze account health metrics",
            )

            # With extra Agent kwargs
            analyst = self.create_agent_from_config(
                "research_agent",
                tools=[search_tool, scrape_tool],
                max_iter=5,
            )
        """
        config = self._get_agent_config(config_key)

        return Agent(
            role=config.get("role", role_default),
            goal=config.get("goal", goal_default),
            backstory=config.get("backstory", backstory_default),
            verbose=config.get("verbose", verbose_default),
            allow_delegation=config.get("allow_delegation", allow_delegation_default),
            llm=self.llm,
            **extra_kwargs,
        )

    def _create_agents(self) -> None:
        """Create and store Agent instances as instance attributes.

        Subclasses should override this method to create all agents needed
        for the crew. Agents should be stored as instance attributes
        (e.g., self.analyst, self.reviewer) so they can be referenced
        when creating tasks and assembling the crew.

        This method is typically called at the start of the run() method,
        before _create_tasks().

        The recommended pattern is to use create_agent_from_config() to
        reduce boilerplate:

        Example implementation:
            def _create_agents(self) -> None:
                self.analyst = self.create_agent_from_config(
                    "account_health_analyst",
                    role_default="Customer Success Analyst",
                    goal_default="Assess account health",
                )

                self.reviewer = self.create_agent_from_config(
                    "account_reviewer",
                    role_default="Senior Reviewer",
                    goal_default="Review and validate analysis",
                )

        Note:
            This is a stub method. Subclasses that don't override this
            method should create agents directly in their run() method.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _create_agents() "
            "or create agents directly in run()"
        )

    def _create_tasks(self, *args: Any, **kwargs: Any) -> List[Task]:
        """Create Task instances for the crew to execute.

        Subclasses should override this method to create all tasks needed
        for the crew. Tasks typically reference agents created in
        _create_agents() and may accept dynamic data via args/kwargs.

        This method is typically called after _create_agents() and before
        assembling and running the Crew.

        Args:
            *args: Positional arguments for task creation (crew-specific).
                Common patterns include passing context strings, data dicts,
                or formatted prompts.
            **kwargs: Keyword arguments for task creation (crew-specific).

        Returns:
            List[Task]: Task instances to be executed by the crew.
                Tasks should be ordered for sequential processing or
                include context references for hierarchical processing.

        Example implementation:
            def _create_tasks(self, account_data: Dict[str, Any]) -> List[Task]:
                task_config = self._get_task_config("assess_account_health")

                analysis_task = Task(
                    description=task_config.get("description", "").format(
                        account_name=account_data["name"],
                        account_tier=account_data.get("tier", "Unknown"),
                    ),
                    expected_output=task_config.get("expected_output", "Analysis"),
                    agent=self.analyst,
                )

                review_task = Task(
                    description="Review the analysis for accuracy",
                    expected_output="Validated analysis",
                    agent=self.reviewer,
                    context=[analysis_task],
                )

                return [analysis_task, review_task]

        Note:
            This is a stub method. Subclasses that don't override this
            method should create tasks directly in their run() method.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _create_tasks() "
            "or create tasks directly in run()"
        )
