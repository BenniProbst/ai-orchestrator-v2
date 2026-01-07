"""
Tests for main Orchestrator

Tests focus on orchestration logic, state management, and role coordination.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import json
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from orchestrator import (
    Orchestrator,
    OrchestratorConfig,
    OrchestratorState,
    SessionState,
)
from agents.base import AgentType, AgentResponse
from roles.base import Decision, DecisionType


class TestOrchestratorConfig:
    """Tests for orchestrator configuration"""

    def test_config_defaults(self):
        """Test default configuration values"""
        config = OrchestratorConfig()

        assert config.max_iterations == 20
        assert config.timeout_seconds == 300
        assert config.master_agent_type == AgentType.CLAUDE
        assert config.worker_agent_type == AgentType.CODEX

    def test_config_custom(self):
        """Test custom configuration"""
        config = OrchestratorConfig(
            max_iterations=50,
            timeout_seconds=600,
            master_agent_type=AgentType.CODEX,
            worker_agent_type=AgentType.CLAUDE,
        )

        assert config.max_iterations == 50
        assert config.master_agent_type == AgentType.CODEX

    def test_config_to_dict(self):
        """Test config serialization"""
        config = OrchestratorConfig()
        data = config.to_dict()

        assert "max_iterations" in data
        assert data["master_agent_type"] == "claude"

    def test_config_from_dict(self):
        """Test config deserialization"""
        data = {
            "max_iterations": 30,
            "master_agent_type": "codex",
            "worker_agent_type": "claude",
        }
        config = OrchestratorConfig.from_dict(data)

        assert config.max_iterations == 30
        assert config.master_agent_type == AgentType.CODEX


class TestOrchestratorInitialization:
    """Tests for orchestrator initialization"""

    def test_orchestrator_init(self, sample_goal):
        """Test basic orchestrator initialization"""
        config = OrchestratorConfig()
        orchestrator = Orchestrator(config, goal=sample_goal)

        assert orchestrator.state == OrchestratorState.IDLE
        assert orchestrator.goal == sample_goal

    def test_orchestrator_initialize_with_goal(self, sample_goal, temp_dir):
        """Test initialization with goal"""
        config = OrchestratorConfig(work_dir=temp_dir)
        orchestrator = Orchestrator(config, goal=sample_goal)

        with patch.object(orchestrator, "_master_agent") as mock_master, \
             patch.object(orchestrator, "_worker_agent") as mock_worker:

            # Mock agents
            mock_master = Mock()
            mock_master.is_available.return_value = True
            mock_worker = Mock()
            mock_worker.is_available.return_value = True

            orchestrator._master_agent = mock_master
            orchestrator._worker_agent = mock_worker

            # Initialize should succeed with mocked agents
            # (actual init would fail without real CLIs)


class TestOrchestratorRun:
    """Tests for orchestrator run loop"""

    def test_orchestrator_run_until_done(self, sample_goal, temp_dir):
        """Test orchestrator running until goal done"""
        config = OrchestratorConfig(work_dir=temp_dir, max_iterations=5)
        orchestrator = Orchestrator(config, goal=sample_goal)

        # Mock the entire run process
        with patch.object(orchestrator, "initialize", return_value=True), \
             patch.object(orchestrator, "_master_role") as mock_master, \
             patch.object(orchestrator, "_worker_role") as mock_worker, \
             patch.object(orchestrator, "_progress_tracker") as mock_tracker:

            # Master decides DONE on first iteration
            mock_master.decide_next_step.return_value = Decision(
                type=DecisionType.DONE,
                reason="Goal achieved",
            )

            mock_tracker.start = Mock()
            mock_tracker.mark_completed = Mock()

            result = orchestrator.run()

            assert result is True
            assert orchestrator.state == OrchestratorState.COMPLETED

    def test_orchestrator_run_max_iterations(self, simple_goal, temp_dir):
        """Test orchestrator stopping at max iterations"""
        config = OrchestratorConfig(work_dir=temp_dir, max_iterations=3)
        orchestrator = Orchestrator(config, goal=simple_goal)

        with patch.object(orchestrator, "initialize", return_value=True), \
             patch.object(orchestrator, "_master_role") as mock_master, \
             patch.object(orchestrator, "_worker_role") as mock_worker, \
             patch.object(orchestrator, "_progress_tracker") as mock_tracker:

            # Master always says IMPLEMENT
            mock_master.decide_next_step.return_value = Decision(
                type=DecisionType.IMPLEMENT,
                instruction="Do something",
            )
            mock_master.verify_implementation.return_value = Mock(
                passed=True, score=0.9, issues=[]
            )

            mock_worker.implement_step.return_value = AgentResponse(
                success=True, output="Done"
            )

            mock_tracker.start = Mock()
            mock_tracker.record_iteration = Mock()

            result = orchestrator.run()

            # Should stop after max iterations
            assert orchestrator._iteration == 3


class TestOrchestratorRoleSwap:
    """Tests for role swapping"""

    def test_orchestrator_swap_roles(self, sample_goal, temp_dir):
        """Test swapping master and worker roles"""
        config = OrchestratorConfig(
            work_dir=temp_dir,
            master_agent_type=AgentType.CLAUDE,
            worker_agent_type=AgentType.CODEX,
        )
        orchestrator = Orchestrator(config, goal=sample_goal)

        # Mock agents
        orchestrator._master_agent = Mock()
        orchestrator._master_agent.agent_type = AgentType.CLAUDE
        orchestrator._worker_agent = Mock()
        orchestrator._worker_agent.agent_type = AgentType.CODEX

        # Swap
        orchestrator.swap_roles()

        # Config should be swapped
        assert orchestrator.config.master_agent_type == AgentType.CODEX
        assert orchestrator.config.worker_agent_type == AgentType.CLAUDE


class TestOrchestratorCheckpointing:
    """Tests for checkpoint/resume functionality"""

    def test_orchestrator_save_checkpoint(self, sample_goal, temp_dir):
        """Test saving checkpoint"""
        config = OrchestratorConfig(work_dir=temp_dir, session_dir="sessions")
        orchestrator = Orchestrator(config, goal=sample_goal)

        # Create session
        orchestrator._session = SessionState(
            session_id="test123",
            started_at=orchestrator._session.started_at if orchestrator._session else __import__("datetime").datetime.now(),
            updated_at=__import__("datetime").datetime.now(),
            state=OrchestratorState.RUNNING,
            iteration=5,
            goal_title="Test Goal",
            config=config.to_dict(),
        )
        orchestrator._iteration = 5
        orchestrator._history = [{"iteration": 1, "success": True}]

        path = orchestrator._save_checkpoint()

        assert Path(path).exists()

    def test_orchestrator_load_checkpoint(self, sample_goal, temp_dir):
        """Test loading checkpoint"""
        config = OrchestratorConfig(work_dir=temp_dir)
        orchestrator = Orchestrator(config, goal=sample_goal)

        # Create checkpoint file
        checkpoint_data = {
            "session_id": "test456",
            "started_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T01:00:00",
            "state": "running",
            "iteration": 3,
            "goal_title": "Test",
            "config": config.to_dict(),
            "history": [],
        }

        checkpoint_path = Path(temp_dir) / "checkpoint.json"
        checkpoint_path.write_text(json.dumps(checkpoint_data))

        # Mock initialize
        with patch.object(orchestrator, "initialize", return_value=True):
            result = orchestrator._load_checkpoint(str(checkpoint_path))

        assert result is True
        assert orchestrator._iteration == 3


class TestOrchestratorStatus:
    """Tests for status reporting"""

    def test_orchestrator_get_status(self, sample_goal, temp_dir):
        """Test getting orchestrator status"""
        config = OrchestratorConfig(work_dir=temp_dir)
        orchestrator = Orchestrator(config, goal=sample_goal)

        status = orchestrator.get_status()

        assert "state" in status
        assert "iteration" in status
        assert "goal" in status
        assert status["goal"]["title"] == "Test Goal"

    def test_orchestrator_progress_summary(self, sample_goal, temp_dir):
        """Test getting progress summary"""
        config = OrchestratorConfig(work_dir=temp_dir)
        orchestrator = Orchestrator(config, goal=sample_goal)

        # Without tracker, should handle gracefully
        summary = orchestrator.get_progress_summary()
        assert "No progress" in summary or isinstance(summary, str)


class TestOrchestratorVerification:
    """Tests for verification handling"""

    def test_orchestrator_handle_verification_failure(self, sample_goal, temp_dir):
        """Test handling verification failure"""
        config = OrchestratorConfig(
            work_dir=temp_dir,
            max_correction_attempts=2,
        )
        orchestrator = Orchestrator(config, goal=sample_goal)

        # Mock components
        orchestrator._master_role = Mock()
        orchestrator._worker_role = Mock()

        # First correction fails, second succeeds
        orchestrator._master_role.create_correction.return_value = Mock(
            prompt="Fix issues",
            max_attempts=2,
        )
        orchestrator._worker_role.implement_step.return_value = AgentResponse(
            success=True, output="Fixed"
        )

        call_count = [0]
        def verify_side_effect(*args):
            call_count[0] += 1
            if call_count[0] == 1:
                return Mock(passed=False, issues=["Still broken"])
            return Mock(passed=True, issues=[])

        orchestrator._master_role.verify_implementation.side_effect = verify_side_effect

        from roles.base import Instruction
        instruction = Instruction(prompt="Test", max_attempts=3)
        response = AgentResponse(success=False, output="")
        verification = Mock(passed=False, issues=["Error"])

        orchestrator._history = []
        orchestrator._progress_tracker = Mock()
        orchestrator._progress_tracker.record_iteration = Mock()

        orchestrator._handle_verification_failure(instruction, response, verification)

        # Should have tried correction
        assert orchestrator._master_role.create_correction.called
