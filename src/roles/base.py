"""
Base Role Strategy Interface and Data Classes

Defines the contract for Master and Worker roles.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional, List
from datetime import datetime

from ..agents.base import IAgent, AgentResponse


class DecisionType(Enum):
    """Types of decisions a Master can make"""
    IMPLEMENT = "implement"  # Proceed with implementation
    SKIP = "skip"            # Skip this step
    DONE = "done"            # Goal achieved, stop
    ERROR = "error"          # Error occurred, handle
    RETRY = "retry"          # Retry last step
    CORRECT = "correct"      # Apply correction


@dataclass
class Decision:
    """A decision made by the Master role"""
    type: DecisionType
    instruction: str = ""
    reason: str = ""
    expected_outcome: str = ""
    priority: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "instruction": self.instruction,
            "reason": self.reason,
            "expected_outcome": self.expected_outcome,
            "priority": self.priority,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Decision":
        data = data.copy()
        data["type"] = DecisionType(data["type"])
        if "timestamp" in data and isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


@dataclass
class VerificationResult:
    """Result of verifying a Worker's implementation"""
    passed: bool
    score: float = 1.0  # 0.0 to 1.0
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "score": self.score,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "details": self.details,
        }


@dataclass
class Instruction:
    """An instruction from Master to Worker"""
    prompt: str
    context: str = ""
    files_to_modify: List[str] = field(default_factory=list)
    files_to_create: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    expected_outcome: str = ""
    max_attempts: int = 3


class IRoleStrategy(ABC):
    """
    Abstract base class for role strategies (Master/Worker).

    Roles define behavior patterns that can be assigned to any agent.
    This allows swapping Claude and Codex between Master and Worker roles.
    """

    def __init__(self, agent: IAgent):
        self.agent = agent
        self._iteration_count = 0

    @property
    @abstractmethod
    def role_name(self) -> str:
        """Return the name of this role"""
        pass

    @abstractmethod
    def decide_next_step(
        self,
        goal_description: str,
        current_state: Dict[str, Any],
        history: List[Dict[str, Any]],
    ) -> Decision:
        """
        Decide what the next step should be.

        Args:
            goal_description: The overall goal to achieve
            current_state: Current state of the project
            history: History of previous iterations

        Returns:
            Decision object with next action
        """
        pass

    @abstractmethod
    def implement_step(self, instruction: Instruction) -> AgentResponse:
        """
        Implement an instruction.

        Args:
            instruction: The instruction to implement

        Returns:
            AgentResponse with implementation results
        """
        pass

    @abstractmethod
    def verify_implementation(
        self,
        instruction: Instruction,
        response: AgentResponse,
    ) -> VerificationResult:
        """
        Verify that an implementation meets expectations.

        Args:
            instruction: The original instruction
            response: The implementation response

        Returns:
            VerificationResult with pass/fail and details
        """
        pass

    @abstractmethod
    def create_correction(
        self,
        original_instruction: Instruction,
        issues: List[str],
    ) -> Instruction:
        """
        Create a correction instruction based on issues.

        Args:
            original_instruction: The instruction that had issues
            issues: List of issues found

        Returns:
            New Instruction with corrections
        """
        pass

    def increment_iteration(self) -> int:
        """Increment and return iteration count"""
        self._iteration_count += 1
        return self._iteration_count

    def reset_iterations(self) -> None:
        """Reset iteration count"""
        self._iteration_count = 0
