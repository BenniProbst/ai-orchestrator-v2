"""
Agent Factory

Creates and configures agents based on type and configuration.
"""

from typing import Optional, Dict, Any

from .base import IAgent, AgentType, AgentConfig
from .claude_agent import ClaudeAgent
from .codex_agent import CodexAgent


class AgentFactory:
    """
    Factory for creating AI agents.

    Provides a central point for agent creation with proper configuration.
    """

    _default_configs: Dict[AgentType, Dict[str, Any]] = {
        AgentType.CLAUDE: {
            "command": "claude",
            "timeout": 120,
            "sandbox": True,
            "json_output": True,
        },
        AgentType.CODEX: {
            "command": "codex",
            "timeout": 300,
            "sandbox": True,
            "full_auto": True,
            "json_output": True,
        },
    }

    @classmethod
    def create(
        cls,
        agent_type: AgentType,
        config: Optional[AgentConfig] = None,
        **kwargs,
    ) -> IAgent:
        """
        Create an agent of the specified type.

        Args:
            agent_type: Type of agent to create
            config: Optional configuration override
            **kwargs: Additional config parameters

        Returns:
            Configured IAgent instance

        Raises:
            ValueError: If agent type is unknown
        """
        if config is None:
            # Build config from defaults and kwargs
            default = cls._default_configs.get(agent_type, {}).copy()
            default.update(kwargs)
            config = AgentConfig(**default)

        if agent_type == AgentType.CLAUDE:
            return ClaudeAgent(config)
        elif agent_type == AgentType.CODEX:
            return CodexAgent(config)
        else:
            raise ValueError(f"Unknown agent type: {agent_type}")

    @classmethod
    def create_from_config(
        cls,
        config_dict: Dict[str, Any],
    ) -> IAgent:
        """
        Create an agent from a configuration dictionary.

        Args:
            config_dict: Dictionary with 'type' and config parameters

        Returns:
            Configured IAgent instance
        """
        agent_type = AgentType(config_dict.pop("type", "claude"))
        config = AgentConfig(**config_dict)
        return cls.create(agent_type, config)

    @classmethod
    def get_available_agents(cls) -> Dict[AgentType, bool]:
        """
        Check which agents are available.

        Returns:
            Dictionary of agent types and availability
        """
        availability = {}

        for agent_type in AgentType:
            try:
                agent = cls.create(agent_type)
                availability[agent_type] = agent.is_available()
            except Exception:
                availability[agent_type] = False

        return availability

    @classmethod
    def set_default_config(
        cls,
        agent_type: AgentType,
        **kwargs,
    ) -> None:
        """
        Update default configuration for an agent type.

        Args:
            agent_type: Agent type to configure
            **kwargs: Configuration parameters
        """
        if agent_type not in cls._default_configs:
            cls._default_configs[agent_type] = {}
        cls._default_configs[agent_type].update(kwargs)

    @classmethod
    def create_pair(
        cls,
        master_type: AgentType = AgentType.CLAUDE,
        worker_type: AgentType = AgentType.CODEX,
        master_config: Optional[AgentConfig] = None,
        worker_config: Optional[AgentConfig] = None,
    ) -> tuple[IAgent, IAgent]:
        """
        Create a Master-Worker agent pair.

        Args:
            master_type: Type for master agent
            worker_type: Type for worker agent
            master_config: Optional master configuration
            worker_config: Optional worker configuration

        Returns:
            Tuple of (master_agent, worker_agent)
        """
        master = cls.create(master_type, master_config)
        worker = cls.create(worker_type, worker_config)
        return master, worker
