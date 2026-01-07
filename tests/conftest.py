"""
Pytest configuration and shared fixtures
"""

import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock
from datetime import datetime

# Add src to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agents.base import IAgent, AgentType, AgentCapability, AgentResponse, AgentConfig
from roles.base import Decision, DecisionType, VerificationResult, Instruction
from goal.parser import Goal, AcceptanceCriterion, CriterionStatus
from protocol.messages import RequestMessage, ResponseMessage, MessageType


@pytest.fixture
def mock_agent():
    """Create a mock agent for testing"""
    agent = Mock(spec=IAgent)
    agent.agent_type = AgentType.CLAUDE
    agent.capabilities = [AgentCapability.CODE_GENERATION, AgentCapability.CODE_ANALYSIS]
    agent.config = AgentConfig(command="mock", timeout=60)
    agent.is_available.return_value = True

    # Default execute response
    agent.execute.return_value = AgentResponse(
        success=True,
        output="Mock output",
        files_modified=[],
        files_created=[],
    )

    return agent


@pytest.fixture
def mock_claude_agent(mock_agent):
    """Claude-specific mock agent"""
    mock_agent.agent_type = AgentType.CLAUDE
    mock_agent.capabilities = [
        AgentCapability.CODE_ANALYSIS,
        AgentCapability.CODE_REVIEW,
        AgentCapability.PLANNING,
        AgentCapability.VERIFICATION,
    ]
    return mock_agent


@pytest.fixture
def mock_codex_agent(mock_agent):
    """Codex-specific mock agent"""
    mock_agent.agent_type = AgentType.CODEX
    mock_agent.capabilities = [
        AgentCapability.CODE_GENERATION,
        AgentCapability.FILE_OPERATIONS,
        AgentCapability.TEST_EXECUTION,
    ]
    return mock_agent


@pytest.fixture
def sample_goal():
    """Create a sample goal for testing"""
    return Goal(
        title="Test Goal",
        description="A test goal for unit testing",
        acceptance_criteria=[
            AcceptanceCriterion(description="Criterion 1", status=CriterionStatus.PENDING),
            AcceptanceCriterion(description="Criterion 2", status=CriterionStatus.PENDING),
            AcceptanceCriterion(description="Criterion 3", status=CriterionStatus.COMPLETED, completed=True),
        ],
        quality_requirements=["Quality 1", "Quality 2"],
        constraints=["Constraint 1"],
    )


@pytest.fixture
def simple_goal():
    """Create a simple goal with one criterion"""
    return Goal(
        title="Simple Goal",
        description="A simple goal",
        acceptance_criteria=[
            AcceptanceCriterion(description="Single criterion"),
        ],
    )


@pytest.fixture
def completed_goal():
    """Create a fully completed goal"""
    return Goal(
        title="Completed Goal",
        description="Already done",
        acceptance_criteria=[
            AcceptanceCriterion(description="Done 1", completed=True, status=CriterionStatus.COMPLETED),
            AcceptanceCriterion(description="Done 2", completed=True, status=CriterionStatus.COMPLETED),
        ],
    )


@pytest.fixture
def sample_decision():
    """Create a sample decision"""
    return Decision(
        type=DecisionType.IMPLEMENT,
        instruction="Implement feature X",
        reason="This is the next logical step",
        expected_outcome="Feature X working",
    )


@pytest.fixture
def sample_instruction():
    """Create a sample instruction"""
    return Instruction(
        prompt="Create a hello world function",
        context="Python project",
        files_to_create=["hello.py"],
        constraints=["Use type hints"],
        expected_outcome="Function that prints hello world",
    )


@pytest.fixture
def sample_agent_response():
    """Create a sample agent response"""
    return AgentResponse(
        success=True,
        output="Function created successfully",
        files_created=["hello.py"],
        execution_time=1.5,
    )


@pytest.fixture
def failed_agent_response():
    """Create a failed agent response"""
    return AgentResponse(
        success=False,
        output="",
        error="Execution failed",
        exit_code=1,
    )


@pytest.fixture
def sample_verification():
    """Create a sample verification result"""
    return VerificationResult(
        passed=True,
        score=0.95,
        issues=[],
        suggestions=["Consider adding more tests"],
    )


@pytest.fixture
def failed_verification():
    """Create a failed verification result"""
    return VerificationResult(
        passed=False,
        score=0.3,
        issues=["Missing error handling", "No tests"],
        suggestions=["Add try/except", "Write unit tests"],
    )


@pytest.fixture
def sample_request_message():
    """Create a sample request message"""
    return RequestMessage(
        instruction="Create a REST API endpoint",
        context="FastAPI project",
        expected_outcome="Working endpoint",
        sender="master",
        recipient="worker",
    )


@pytest.fixture
def sample_response_message():
    """Create a sample response message"""
    return ResponseMessage(
        success=True,
        output="Endpoint created at /api/users",
        files_created=["api/users.py"],
        sender="worker",
        recipient="master",
    )


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def temp_goal_file(temp_dir):
    """Create a temporary goal file"""
    goal_content = """# Test Goal

## Description
A test goal for testing.

## Acceptance Criteria
- [ ] First criterion
- [ ] Second criterion
- [x] Third criterion (done)

## Quality Requirements
- Must be tested
- Must be documented

## Constraints
- Use Python
"""
    goal_path = Path(temp_dir) / "GOAL.txt"
    goal_path.write_text(goal_content)
    return str(goal_path)


@pytest.fixture
def empty_goal_file(temp_dir):
    """Create an empty goal file"""
    goal_path = Path(temp_dir) / "EMPTY_GOAL.txt"
    goal_path.write_text("")
    return str(goal_path)


@pytest.fixture
def invalid_goal_file(temp_dir):
    """Create an invalid goal file"""
    goal_path = Path(temp_dir) / "INVALID_GOAL.txt"
    goal_path.write_text("This is not a valid goal format\nNo structure here")
    return str(goal_path)
