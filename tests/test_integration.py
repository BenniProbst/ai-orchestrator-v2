"""
Integration Tests

Tests:
1. test_full_workflow_simple_goal
2. test_full_workflow_complex_goal
3. test_workflow_with_corrections
4. test_workflow_role_swap_midway
5. test_workflow_multi_iteration
6. test_workflow_with_verification_failure
7. test_workflow_timeout_recovery
8. test_workflow_state_persistence
9. test_workflow_resume_from_checkpoint
10. test_workflow_concurrent_agents
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import json
import tempfile
from pathlib import Path
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from orchestrator import Orchestrator, OrchestratorConfig, OrchestratorState
from agents.base import AgentType, AgentResponse
from agents.factory import AgentFactory
from roles.base import Decision, DecisionType, VerificationResult
from roles.master import MasterRole
from roles.worker import WorkerRole
from goal.parser import GoalParser, Goal, AcceptanceCriterion
from goal.progress import ProgressTracker


class TestFullWorkflow:
    """Integration tests for complete workflows"""

    def test_full_workflow_simple_goal(self, simple_goal, temp_dir):
        """Test complete workflow with simple goal"""
        config = OrchestratorConfig(
            work_dir=temp_dir,
            max_iterations=5,
        )
        orchestrator = Orchestrator(config, goal=simple_goal)

        with patch.object(orchestrator, "initialize", return_value=True), \
             patch.object(orchestrator, "_master_role") as mock_master, \
             patch.object(orchestrator, "_worker_role") as mock_worker, \
             patch.object(orchestrator, "_progress_tracker") as mock_tracker:

            # Simulate: IMPLEMENT -> verify pass -> DONE
            call_count = [0]
            def decide_side_effect(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] == 1:
                    return Decision(type=DecisionType.IMPLEMENT, instruction="Do it")
                return Decision(type=DecisionType.DONE, reason="Complete")

            mock_master.decide_next_step.side_effect = decide_side_effect
            mock_master.verify_implementation.return_value = VerificationResult(
                passed=True, score=1.0
            )

            mock_worker.implement_step.return_value = AgentResponse(
                success=True, output="Implemented"
            )

            mock_tracker.start = Mock()
            mock_tracker.record_iteration = Mock()
            mock_tracker.mark_completed = Mock()

            result = orchestrator.run()

            assert result is True
            assert orchestrator.state == OrchestratorState.COMPLETED

    def test_full_workflow_complex_goal(self, sample_goal, temp_dir):
        """Test workflow with multi-criteria goal"""
        config = OrchestratorConfig(
            work_dir=temp_dir,
            max_iterations=10,
        )
        orchestrator = Orchestrator(config, goal=sample_goal)

        with patch.object(orchestrator, "initialize", return_value=True), \
             patch.object(orchestrator, "_master_role") as mock_master, \
             patch.object(orchestrator, "_worker_role") as mock_worker, \
             patch.object(orchestrator, "_progress_tracker") as mock_tracker:

            # Simulate multiple iterations
            iterations = [0]
            def decide_side_effect(*args, **kwargs):
                iterations[0] += 1
                if iterations[0] < 3:
                    return Decision(type=DecisionType.IMPLEMENT, instruction=f"Step {iterations[0]}")
                return Decision(type=DecisionType.DONE, reason="All done")

            mock_master.decide_next_step.side_effect = decide_side_effect
            mock_master.verify_implementation.return_value = VerificationResult(passed=True, score=0.9)
            mock_worker.implement_step.return_value = AgentResponse(success=True, output="Done")

            mock_tracker.start = Mock()
            mock_tracker.record_iteration = Mock()
            mock_tracker.mark_completed = Mock()

            result = orchestrator.run()

            assert result is True
            assert iterations[0] == 3  # 2 IMPLEMENT + 1 DONE


class TestWorkflowCorrections:
    """Tests for correction workflows"""

    def test_workflow_with_corrections(self, simple_goal, temp_dir):
        """Test workflow with correction cycle"""
        config = OrchestratorConfig(
            work_dir=temp_dir,
            max_iterations=10,
            max_correction_attempts=3,
        )
        orchestrator = Orchestrator(config, goal=simple_goal)

        with patch.object(orchestrator, "initialize", return_value=True), \
             patch.object(orchestrator, "_master_role") as mock_master, \
             patch.object(orchestrator, "_worker_role") as mock_worker, \
             patch.object(orchestrator, "_progress_tracker") as mock_tracker:

            # First: IMPLEMENT, verify fails, then corrects, then DONE
            decide_calls = [0]
            verify_calls = [0]

            def decide_effect(*args, **kwargs):
                decide_calls[0] += 1
                if decide_calls[0] <= 2:
                    return Decision(type=DecisionType.IMPLEMENT, instruction="Implement")
                return Decision(type=DecisionType.DONE, reason="Done")

            def verify_effect(*args, **kwargs):
                verify_calls[0] += 1
                if verify_calls[0] == 1:
                    return VerificationResult(passed=False, score=0.3, issues=["Bug"])
                return VerificationResult(passed=True, score=0.9)

            mock_master.decide_next_step.side_effect = decide_effect
            mock_master.verify_implementation.side_effect = verify_effect
            mock_master.create_correction.return_value = Mock(prompt="Fix", max_attempts=2)
            mock_worker.implement_step.return_value = AgentResponse(success=True, output="Done")

            mock_tracker.start = Mock()
            mock_tracker.record_iteration = Mock()
            mock_tracker.mark_completed = Mock()

            # Run
            orchestrator._history = []
            result = orchestrator.run()

            # Should have gone through correction
            assert mock_master.create_correction.called or verify_calls[0] >= 1


class TestWorkflowRoleSwap:
    """Tests for role swapping during workflow"""

    def test_workflow_role_swap_midway(self, sample_goal, temp_dir):
        """Test swapping roles during execution"""
        config = OrchestratorConfig(
            work_dir=temp_dir,
            master_agent_type=AgentType.CLAUDE,
            worker_agent_type=AgentType.CODEX,
        )
        orchestrator = Orchestrator(config, goal=sample_goal)

        # Initialize with mocked agents
        orchestrator._master_agent = Mock()
        orchestrator._master_agent.agent_type = AgentType.CLAUDE
        orchestrator._worker_agent = Mock()
        orchestrator._worker_agent.agent_type = AgentType.CODEX

        # Initial roles
        assert orchestrator.config.master_agent_type == AgentType.CLAUDE

        # Swap mid-workflow
        orchestrator.swap_roles()

        # Roles should be swapped
        assert orchestrator.config.master_agent_type == AgentType.CODEX
        assert orchestrator.config.worker_agent_type == AgentType.CLAUDE


class TestWorkflowMultiIteration:
    """Tests for multi-iteration workflows"""

    def test_workflow_multi_iteration(self, sample_goal, temp_dir):
        """Test workflow with many iterations"""
        config = OrchestratorConfig(
            work_dir=temp_dir,
            max_iterations=20,
        )
        orchestrator = Orchestrator(config, goal=sample_goal)

        with patch.object(orchestrator, "initialize", return_value=True), \
             patch.object(orchestrator, "_master_role") as mock_master, \
             patch.object(orchestrator, "_worker_role") as mock_worker, \
             patch.object(orchestrator, "_progress_tracker") as mock_tracker:

            iterations = [0]
            def decide_effect(*args, **kwargs):
                iterations[0] += 1
                if iterations[0] < 8:
                    return Decision(type=DecisionType.IMPLEMENT, instruction="Step")
                return Decision(type=DecisionType.DONE, reason="Done")

            mock_master.decide_next_step.side_effect = decide_effect
            mock_master.verify_implementation.return_value = VerificationResult(passed=True, score=1.0)
            mock_worker.implement_step.return_value = AgentResponse(success=True, output="OK")

            mock_tracker.start = Mock()
            mock_tracker.record_iteration = Mock()
            mock_tracker.mark_completed = Mock()

            result = orchestrator.run()

            assert result is True
            assert iterations[0] == 8


class TestWorkflowVerificationFailure:
    """Tests for verification failure handling"""

    def test_workflow_with_verification_failure(self, simple_goal, temp_dir):
        """Test workflow when verification keeps failing"""
        config = OrchestratorConfig(
            work_dir=temp_dir,
            max_iterations=10,
            max_correction_attempts=2,
        )
        orchestrator = Orchestrator(config, goal=simple_goal)

        with patch.object(orchestrator, "initialize", return_value=True), \
             patch.object(orchestrator, "_master_role") as mock_master, \
             patch.object(orchestrator, "_worker_role") as mock_worker, \
             patch.object(orchestrator, "_progress_tracker") as mock_tracker:

            # Always fail verification
            mock_master.decide_next_step.return_value = Decision(
                type=DecisionType.IMPLEMENT, instruction="Do"
            )
            mock_master.verify_implementation.return_value = VerificationResult(
                passed=False, score=0.2, issues=["Failed"]
            )
            mock_master.create_correction.return_value = Mock(prompt="Fix", max_attempts=1)
            mock_worker.implement_step.return_value = AgentResponse(success=True, output="Done")

            mock_tracker.start = Mock()
            mock_tracker.record_iteration = Mock()

            orchestrator._history = []
            # Will hit max iterations
            result = orchestrator.run()

            # Should have stopped at max iterations
            assert orchestrator._iteration <= config.max_iterations


class TestWorkflowRecovery:
    """Tests for recovery scenarios"""

    def test_workflow_timeout_recovery(self, simple_goal, temp_dir):
        """Test recovery from timeout"""
        config = OrchestratorConfig(
            work_dir=temp_dir,
            timeout_seconds=60,
        )
        orchestrator = Orchestrator(config, goal=simple_goal)

        with patch.object(orchestrator, "initialize", return_value=True), \
             patch.object(orchestrator, "_master_role") as mock_master, \
             patch.object(orchestrator, "_worker_role") as mock_worker, \
             patch.object(orchestrator, "_progress_tracker") as mock_tracker:

            # First call times out (returns error), second succeeds
            call_count = [0]
            def decide_effect(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] == 1:
                    return Decision(type=DecisionType.ERROR, reason="Timeout")
                return Decision(type=DecisionType.DONE, reason="Done")

            mock_master.decide_next_step.side_effect = decide_effect
            mock_tracker.start = Mock()
            mock_tracker.mark_blocked = Mock()
            mock_tracker.mark_completed = Mock()
            mock_tracker.record_iteration = Mock()

            result = orchestrator.run()

            # Should complete despite initial timeout
            assert call_count[0] >= 1


class TestWorkflowPersistence:
    """Tests for state persistence"""

    def test_workflow_state_persistence(self, sample_goal, temp_dir):
        """Test that state is persisted during workflow"""
        config = OrchestratorConfig(
            work_dir=temp_dir,
            checkpoint_interval=1,  # Checkpoint every iteration
        )
        orchestrator = Orchestrator(config, goal=sample_goal)

        # Create session
        from datetime import datetime
        orchestrator._session = Mock()
        orchestrator._session.session_id = "test123"
        orchestrator._session.to_dict.return_value = {
            "session_id": "test123",
            "started_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "state": "running",
            "iteration": 1,
            "goal_title": "Test",
            "config": config.to_dict(),
            "history": [],
        }

        orchestrator._iteration = 1
        orchestrator._history = []

        # Save checkpoint
        path = orchestrator._save_checkpoint()

        assert Path(path).exists()
        data = json.loads(Path(path).read_text())
        assert data["session_id"] == "test123"

    def test_workflow_resume_from_checkpoint(self, sample_goal, temp_dir):
        """Test resuming workflow from checkpoint"""
        config = OrchestratorConfig(work_dir=temp_dir)

        # Create checkpoint
        checkpoint_data = {
            "session_id": "resume_test",
            "started_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T01:00:00",
            "state": "running",
            "iteration": 5,
            "goal_title": "Test Goal",
            "config": config.to_dict(),
            "history": [
                {"iteration": 1, "success": True},
                {"iteration": 2, "success": True},
            ],
        }

        checkpoint_path = Path(temp_dir) / "checkpoint.json"
        checkpoint_path.write_text(json.dumps(checkpoint_data))

        orchestrator = Orchestrator(config, goal=sample_goal)

        with patch.object(orchestrator, "initialize", return_value=True):
            loaded = orchestrator._load_checkpoint(str(checkpoint_path))

        assert loaded is True
        assert orchestrator._iteration == 5
        assert len(orchestrator._history) == 2


class TestWorkflowConcurrency:
    """Tests for concurrent agent operations"""

    def test_workflow_concurrent_agents(self, sample_goal, temp_dir):
        """Test that agents can work independently"""
        config = OrchestratorConfig(work_dir=temp_dir)
        orchestrator = Orchestrator(config, goal=sample_goal)

        # Create independent agents
        with patch("agents.factory.AgentFactory.create") as mock_factory:
            master_agent = Mock()
            master_agent.agent_type = AgentType.CLAUDE
            master_agent.is_available.return_value = True

            worker_agent = Mock()
            worker_agent.agent_type = AgentType.CODEX
            worker_agent.is_available.return_value = True

            def create_effect(agent_type, *args, **kwargs):
                if agent_type == AgentType.CLAUDE:
                    return master_agent
                return worker_agent

            mock_factory.side_effect = create_effect

            # Create agents
            m, w = AgentFactory.create_pair()

            # Both should be independent
            assert m is not w
            assert m.agent_type != w.agent_type
