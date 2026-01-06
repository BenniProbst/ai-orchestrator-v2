"""
Base Agent Interface and Data Classes

Defines the contract for all AI agents (Claude, Codex) and common data structures.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional, List
from datetime import datetime


class AgentType(Enum):
    """Available AI agent types"""
    CLAUDE = "claude"
    CODEX = "codex"


class AgentCapability(Enum):
    """Capabilities that agents may support"""
    CODE_GENERATION = "code_generation"
    CODE_ANALYSIS = "code_analysis"
    CODE_REVIEW = "code_review"
    FILE_OPERATIONS = "file_operations"
    TEST_EXECUTION = "test_execution"
    REFACTORING = "refactoring"
    DOCUMENTATION = "documentation"
    PLANNING = "planning"
    VERIFICATION = "verification"


@dataclass
class AgentResponse:
    """Response from an agent execution"""
    success: bool
    output: str
    files_modified: List[str] = field(default_factory=list)
    files_created: List[str] = field(default_factory=list)
    files_deleted: List[str] = field(default_factory=list)
    error: Optional[str] = None
    exit_code: int = 0
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "success": self.success,
            "output": self.output,
            "files_modified": self.files_modified,
            "files_created": self.files_created,
            "files_deleted": self.files_deleted,
            "error": self.error,
            "exit_code": self.exit_code,
            "execution_time": self.execution_time,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentResponse":
        """Create from dictionary"""
        data = data.copy()
        if "timestamp" in data and isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)

    @classmethod
    def error_response(cls, error: str, exit_code: int = 1) -> "AgentResponse":
        """Create an error response"""
        return cls(
            success=False,
            output="",
            error=error,
            exit_code=exit_code,
        )


@dataclass
class AgentConfig:
    """Configuration for an agent"""
    command: str
    timeout: int = 120
    sandbox: bool = True
    full_auto: bool = False
    json_output: bool = True
    work_dir: Optional[str] = None
    env_vars: Dict[str, str] = field(default_factory=dict)


class IAgent(ABC):
    """
    Abstract base class for AI agents.

    All AI agents (Claude Code, Codex CLI) must implement this interface
    to be usable in the orchestration system.
    """

    def __init__(self, config: AgentConfig):
        self.config = config
        self._capabilities: List[AgentCapability] = []

    @property
    def agent_type(self) -> AgentType:
        """Return the type of this agent"""
        raise NotImplementedError

    @property
    def capabilities(self) -> List[AgentCapability]:
        """Return list of supported capabilities"""
        return self._capabilities

    @abstractmethod
    def execute(self, prompt: str, work_dir: Optional[str] = None) -> AgentResponse:
        """
        Execute a prompt/command using this agent.

        Args:
            prompt: The instruction or prompt to execute
            work_dir: Optional working directory override

        Returns:
            AgentResponse with execution results
        """
        pass

    @abstractmethod
    def analyze(self, context: str, question: str) -> str:
        """
        Analyze context and answer a question about it.

        Args:
            context: The context to analyze (code, output, etc.)
            question: What to analyze or determine

        Returns:
            Analysis result as string
        """
        pass

    @abstractmethod
    def verify(self, expected: str, actual: str) -> bool:
        """
        Verify that actual output matches expected outcome.

        Args:
            expected: What was expected
            actual: What was actually produced

        Returns:
            True if verification passes
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if this agent is available and properly configured.

        Returns:
            True if agent can be used
        """
        pass

    def has_capability(self, capability: AgentCapability) -> bool:
        """Check if agent has a specific capability"""
        return capability in self._capabilities

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(type={self.agent_type.value})"
