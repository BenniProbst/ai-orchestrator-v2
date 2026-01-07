"""
Tests for Role implementations

Tests:
1. test_master_decide_implement
2. test_master_decide_skip
3. test_master_decide_done
4. test_master_verify_success
5. test_master_verify_failure
6. test_worker_implement_success
7. test_worker_implement_partial
8. test_role_swap_claude_to_codex
9. test_role_swap_codex_to_claude
10. test_role_configuration_validation
"""

import pytest
from unittest.mock import Mock, patch
import json

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agents.base import AgentType, AgentResponse, AgentConfig
from roles.base import Decision, DecisionType, VerificationResult, Instruction, IRoleStrategy
from roles.master import MasterRole
from roles.worker import WorkerRole


class TestMasterDecisions:
    """Tests for Master role decisions"""

    def test_master_decide_implement(self, mock_agent):
        """Test Master deciding to implement"""
        mock_agent.execute.return_value = AgentResponse(
            success=True,
            output=json.dumps({
                "decision_type": "IMPLEMENT",
                "instruction": "Create the user model",
                "reason": "Next step in the plan",
                "expected_outcome": "User model created",
            }),
        )

        master = MasterRole(mock_agent)
        decision = master.decide_next_step(
            goal_description="Create user management",
            current_state={"iteration": 1},
            history=[],
        )

        assert decision.type == DecisionType.IMPLEMENT
        assert "user" in decision.instruction.lower() or decision.instruction != ""

    def test_master_decide_skip(self, mock_agent):
        """Test Master deciding to skip"""
        mock_agent.execute.return_value = AgentResponse(
            success=True,
            output=json.dumps({
                "decision_type": "SKIP",
                "instruction": "",
                "reason": "Already implemented",
                "expected_outcome": "",
            }),
        )

        master = MasterRole(mock_agent)
        decision = master.decide_next_step(
            goal_description="Already done task",
            current_state={"goal_progress": 100},
            history=[],
        )

        assert decision.type == DecisionType.SKIP

    def test_master_decide_done(self, mock_agent):
        """Test Master deciding goal is done"""
        mock_agent.execute.return_value = AgentResponse(
            success=True,
            output=json.dumps({
                "decision_type": "DONE",
                "instruction": "",
                "reason": "All criteria met",
                "expected_outcome": "",
            }),
        )

        master = MasterRole(mock_agent)
        decision = master.decide_next_step(
            goal_description="Completed goal",
            current_state={"goal_progress": 100, "completed_criteria": 5, "total_criteria": 5},
            history=[],
        )

        assert decision.type == DecisionType.DONE

    def test_master_decide_error_on_failure(self, mock_agent):
        """Test Master returns error on agent failure"""
        mock_agent.execute.return_value = AgentResponse(
            success=False,
            output="",
            error="Agent failed",
        )

        master = MasterRole(mock_agent)
        decision = master.decide_next_step(
            goal_description="Test",
            current_state={},
            history=[],
        )

        assert decision.type == DecisionType.ERROR


class TestMasterVerification:
    """Tests for Master verification"""

    def test_master_verify_success(self, mock_agent, sample_instruction, sample_agent_response):
        """Test successful verification"""
        mock_agent.execute.return_value = AgentResponse(
            success=True,
            output=json.dumps({
                "passed": True,
                "score": 0.95,
                "issues": [],
                "suggestions": ["Add more comments"],
            }),
        )

        master = MasterRole(mock_agent)
        result = master.verify_implementation(sample_instruction, sample_agent_response)

        assert result.passed
        assert result.score >= 0.9

    def test_master_verify_failure(self, mock_agent, sample_instruction, sample_agent_response):
        """Test failed verification"""
        mock_agent.execute.return_value = AgentResponse(
            success=True,
            output=json.dumps({
                "passed": False,
                "score": 0.3,
                "issues": ["Missing error handling", "No tests"],
                "suggestions": ["Add try/except"],
            }),
        )

        master = MasterRole(mock_agent)
        result = master.verify_implementation(sample_instruction, sample_agent_response)

        assert not result.passed
        assert result.score < 0.5
        assert len(result.issues) > 0


class TestWorkerImplementation:
    """Tests for Worker implementation"""

    def test_worker_implement_success(self, mock_agent, sample_instruction):
        """Test successful Worker implementation"""
        mock_agent.execute.return_value = AgentResponse(
            success=True,
            output="Implementation complete",
            files_created=["hello.py"],
        )

        worker = WorkerRole(mock_agent)
        response = worker.implement_step(sample_instruction)

        assert response.success
        assert mock_agent.execute.called

    def test_worker_implement_partial(self, mock_agent, sample_instruction):
        """Test partial Worker implementation"""
        mock_agent.execute.return_value = AgentResponse(
            success=True,
            output="Partially implemented",
            files_created=[],  # No files created despite instruction
        )

        worker = WorkerRole(mock_agent)
        response = worker.implement_step(sample_instruction)

        # Success but verification would catch missing files
        assert response.success

    def test_worker_self_verify(self, mock_agent, sample_instruction, sample_agent_response):
        """Test Worker's self-verification"""
        worker = WorkerRole(mock_agent)

        # Good response
        result = worker.verify_implementation(sample_instruction, sample_agent_response)
        assert result.passed  # Files created match expected

    def test_worker_self_verify_failure(self, mock_agent, sample_instruction, failed_agent_response):
        """Test Worker's self-verification on failure"""
        worker = WorkerRole(mock_agent)

        result = worker.verify_implementation(sample_instruction, failed_agent_response)
        assert not result.passed
        assert len(result.issues) > 0


class TestRoleSwapping:
    """Tests for role swapping"""

    def test_role_swap_claude_to_codex(self, mock_claude_agent, mock_codex_agent):
        """Test swapping Claude from Master to Worker"""
        # Initially Claude is Master
        master = MasterRole(mock_claude_agent)
        worker = WorkerRole(mock_codex_agent)

        assert master.agent.agent_type == AgentType.CLAUDE
        assert worker.agent.agent_type == AgentType.CODEX

        # Swap roles
        new_master = MasterRole(mock_codex_agent)
        new_worker = WorkerRole(mock_claude_agent)

        assert new_master.agent.agent_type == AgentType.CODEX
        assert new_worker.agent.agent_type == AgentType.CLAUDE

    def test_role_swap_codex_to_claude(self, mock_claude_agent, mock_codex_agent):
        """Test swapping Codex from Worker to Master"""
        # Same as above but explicit
        master = MasterRole(mock_codex_agent)
        worker = WorkerRole(mock_claude_agent)

        assert master.agent.agent_type == AgentType.CODEX
        assert worker.agent.agent_type == AgentType.CLAUDE
        assert master.role_name == "master"
        assert worker.role_name == "worker"


class TestRoleConfiguration:
    """Tests for role configuration"""

    def test_role_configuration_validation(self, mock_agent):
        """Test role configuration is valid"""
        master = MasterRole(mock_agent)
        worker = WorkerRole(mock_agent)

        assert master.role_name == "master"
        assert worker.role_name == "worker"
        assert master.agent is not None
        assert worker.agent is not None

    def test_role_iteration_tracking(self, mock_agent):
        """Test iteration counter"""
        master = MasterRole(mock_agent)

        assert master._iteration_count == 0
        master.increment_iteration()
        assert master._iteration_count == 1
        master.increment_iteration()
        assert master._iteration_count == 2
        master.reset_iterations()
        assert master._iteration_count == 0


class TestMasterCorrection:
    """Tests for Master correction creation"""

    def test_master_create_correction(self, mock_agent, sample_instruction):
        """Test creating correction instruction"""
        mock_agent.execute.return_value = AgentResponse(
            success=True,
            output="Fix the missing error handling by adding try/except blocks",
        )

        master = MasterRole(mock_agent)
        correction = master.create_correction(
            sample_instruction,
            issues=["Missing error handling", "No input validation"],
        )

        assert isinstance(correction, Instruction)
        assert correction.max_attempts < sample_instruction.max_attempts

    def test_master_correction_preserves_context(self, mock_agent, sample_instruction):
        """Test correction preserves original context"""
        mock_agent.execute.return_value = AgentResponse(
            success=True,
            output="Add error handling",
        )

        master = MasterRole(mock_agent)
        correction = master.create_correction(sample_instruction, ["Error"])

        assert len(correction.constraints) > len(sample_instruction.constraints)
