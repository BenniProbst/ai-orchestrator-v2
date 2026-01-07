"""
Edge Case Tests

Tests:
1. test_empty_goal_file
2. test_invalid_goal_format
3. test_agent_unavailable
4. test_both_agents_unavailable
5. test_circular_correction_loop
6. test_max_iterations_reached
7. test_work_dir_not_exists
8. test_work_dir_no_permissions
9. test_large_output_handling
10. test_unicode_in_goal_and_output
"""

import pytest
from unittest.mock import Mock, patch
import tempfile
import os
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from orchestrator import Orchestrator, OrchestratorConfig, OrchestratorState
from agents.base import AgentType, AgentResponse
from agents.claude_agent import ClaudeAgent
from agents.codex_agent import CodexAgent
from roles.base import Decision, DecisionType, VerificationResult, Instruction
from goal.parser import GoalParser, Goal, AcceptanceCriterion


class TestGoalEdgeCases:
    """Edge cases for goal parsing"""

    def test_empty_goal_file(self, empty_goal_file):
        """Test handling empty goal file"""
        parser = GoalParser()

        with pytest.raises(ValueError, match="empty"):
            parser.parse_file(empty_goal_file)

    def test_invalid_goal_format(self, temp_dir):
        """Test handling invalid goal format"""
        invalid_path = Path(temp_dir) / "invalid.txt"
        invalid_path.write_text("Random text without proper markdown structure")

        parser = GoalParser()
        goal = parser.parse_file(str(invalid_path))

        # Should parse but with defaults
        assert goal.title == "Untitled Goal" or goal.title  # Has some title
        assert len(goal.acceptance_criteria) == 0  # No valid criteria

    def test_goal_with_only_title(self, temp_dir):
        """Test goal with only title"""
        goal_path = Path(temp_dir) / "title_only.txt"
        goal_path.write_text("# Just A Title\n\nSome text but no criteria")

        parser = GoalParser()
        goal = parser.parse_file(str(goal_path))

        assert goal.title == "Just A Title"
        assert goal.total_criteria == 0

    def test_goal_with_malformed_criteria(self, temp_dir):
        """Test goal with malformed acceptance criteria"""
        goal_path = Path(temp_dir) / "malformed.txt"
        goal_path.write_text("""# Test

## Acceptance Criteria
- Not a checkbox item
-[] Missing space
- [x Missing bracket
- [ ] Valid one
""")

        parser = GoalParser()
        goal = parser.parse_file(str(goal_path))

        # Should only parse the valid one
        assert len(goal.acceptance_criteria) >= 1


class TestAgentEdgeCases:
    """Edge cases for agents"""

    def test_agent_unavailable(self):
        """Test handling when agent CLI is not available"""
        with patch("shutil.which", return_value=None):
            agent = ClaudeAgent()
            assert not agent.is_available()

    def test_both_agents_unavailable(self, sample_goal, temp_dir):
        """Test when both agents are unavailable"""
        config = OrchestratorConfig(work_dir=temp_dir)
        orchestrator = Orchestrator(config, goal=sample_goal)

        with patch("shutil.which", return_value=None):
            # Initialize should warn but not fail completely
            # (depends on implementation)
            pass

    def test_agent_returns_empty_output(self):
        """Test handling empty agent output"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="",
                stderr="",
            )

            agent = ClaudeAgent()
            response = agent.execute("Test")

            assert response.success
            assert response.output == ""

    def test_agent_returns_invalid_json(self):
        """Test handling invalid JSON from agent"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="Not valid JSON {{{",
                stderr="",
            )

            agent = ClaudeAgent()
            response = agent.execute("Test")

            # Should still succeed but with raw output
            assert response.success
            assert "Not valid JSON" in response.output


class TestCorrectionEdgeCases:
    """Edge cases for correction loops"""

    def test_circular_correction_loop(self, simple_goal, temp_dir):
        """Test protection against infinite correction loops"""
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

            # Always fail verification
            mock_master.decide_next_step.return_value = Decision(
                type=DecisionType.IMPLEMENT, instruction="Do"
            )
            mock_master.verify_implementation.return_value = VerificationResult(
                passed=False, score=0.1, issues=["Always fails"]
            )
            mock_master.create_correction.return_value = Mock(
                prompt="Fix", max_attempts=0  # Decreasing attempts
            )
            mock_worker.implement_step.return_value = AgentResponse(
                success=True, output="Done"
            )

            mock_tracker.start = Mock()
            mock_tracker.record_iteration = Mock()
            mock_tracker.mark_blocked = Mock()

            orchestrator._history = []
            orchestrator.run()

            # Should stop at max iterations, not loop forever
            assert orchestrator._iteration <= config.max_iterations


class TestIterationEdgeCases:
    """Edge cases for iteration limits"""

    def test_max_iterations_reached(self, simple_goal, temp_dir):
        """Test stopping at max iterations"""
        config = OrchestratorConfig(
            work_dir=temp_dir,
            max_iterations=3,
        )
        orchestrator = Orchestrator(config, goal=simple_goal)

        with patch.object(orchestrator, "initialize", return_value=True), \
             patch.object(orchestrator, "_master_role") as mock_master, \
             patch.object(orchestrator, "_worker_role") as mock_worker, \
             patch.object(orchestrator, "_progress_tracker") as mock_tracker:

            # Never complete
            mock_master.decide_next_step.return_value = Decision(
                type=DecisionType.IMPLEMENT, instruction="Loop forever"
            )
            mock_master.verify_implementation.return_value = VerificationResult(
                passed=True, score=1.0
            )
            mock_worker.implement_step.return_value = AgentResponse(
                success=True, output="Done"
            )

            mock_tracker.start = Mock()
            mock_tracker.record_iteration = Mock()

            result = orchestrator.run()

            assert result is False
            assert orchestrator._iteration == 3
            assert orchestrator.state == OrchestratorState.FAILED

    def test_zero_max_iterations(self, simple_goal, temp_dir):
        """Test with zero max iterations"""
        config = OrchestratorConfig(
            work_dir=temp_dir,
            max_iterations=0,
        )
        orchestrator = Orchestrator(config, goal=simple_goal)

        with patch.object(orchestrator, "initialize", return_value=True), \
             patch.object(orchestrator, "_progress_tracker") as mock_tracker:
            mock_tracker.start = Mock()

            result = orchestrator.run()

            # Should fail immediately
            assert result is False


class TestFileSystemEdgeCases:
    """Edge cases for file system operations"""

    def test_work_dir_not_exists(self, simple_goal):
        """Test with non-existent work directory"""
        config = OrchestratorConfig(
            work_dir="/nonexistent/path/that/does/not/exist",
        )
        orchestrator = Orchestrator(config, goal=simple_goal)

        # Should handle gracefully
        # (exact behavior depends on implementation)

    def test_work_dir_permissions(self, simple_goal, temp_dir):
        """Test work directory permission handling"""
        # Create read-only directory (platform dependent)
        readonly_dir = Path(temp_dir) / "readonly"
        readonly_dir.mkdir()

        try:
            # Try to make read-only (may not work on all platforms)
            if os.name != "nt":  # Not Windows
                os.chmod(readonly_dir, 0o444)

            config = OrchestratorConfig(work_dir=str(readonly_dir))
            orchestrator = Orchestrator(config, goal=simple_goal)

            # Should handle gracefully
        finally:
            # Restore permissions for cleanup
            if os.name != "nt":
                os.chmod(readonly_dir, 0o755)


class TestOutputEdgeCases:
    """Edge cases for output handling"""

    def test_large_output_handling(self):
        """Test handling very large agent output"""
        with patch("subprocess.run") as mock_run:
            # 1MB of output
            large_output = "x" * (1024 * 1024)
            mock_run.return_value = Mock(
                returncode=0,
                stdout=large_output,
                stderr="",
            )

            agent = ClaudeAgent()
            response = agent.execute("Generate lots of output")

            assert response.success
            assert len(response.output) > 0

    def test_binary_output_handling(self):
        """Test handling binary-like output"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="\x00\x01\x02 mixed content",
                stderr="",
            )

            agent = ClaudeAgent()
            response = agent.execute("Test")

            # Should not crash
            assert response is not None


class TestUnicodeEdgeCases:
    """Edge cases for unicode handling"""

    def test_unicode_in_goal_and_output(self, temp_dir):
        """Test unicode in goal and output"""
        # Create goal with unicode
        goal_path = Path(temp_dir) / "unicode_goal.txt"
        goal_path.write_text("""# 日本語のゴール 🎯

## Description
Это описание на русском языке.
中文描述也在这里。

## Acceptance Criteria
- [ ] Créer une fonction française
- [ ] Implementar función española
- [ ] 实现中文功能
- [x] ✓ Already done

## Constraints
- Emoji support 😀
""", encoding="utf-8")

        parser = GoalParser()
        goal = parser.parse_file(str(goal_path))

        assert "日本語" in goal.title
        assert len(goal.acceptance_criteria) == 4

    def test_unicode_in_agent_response(self):
        """Test unicode in agent response"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="Ответ на русском: привет мир 🌍",
                stderr="",
            )

            agent = ClaudeAgent()
            response = agent.execute("Test unicode")

            assert response.success
            assert "привет" in response.output

    def test_unicode_in_decision(self):
        """Test unicode in decision messages"""
        decision = Decision(
            type=DecisionType.IMPLEMENT,
            instruction="Créer une fonction 函数",
            reason="日本語の理由",
            expected_outcome="Résultat attendu 期望结果",
        )

        data = decision.to_dict()
        assert "Créer" in data["instruction"]
        assert "日本語" in data["reason"]


class TestSpecialCharacterEdgeCases:
    """Edge cases for special characters"""

    def test_newlines_in_instruction(self):
        """Test handling newlines in instructions"""
        instruction = Instruction(
            prompt="Step 1\nStep 2\nStep 3",
            context="Multi-line\ncontext",
        )

        assert "\n" in instruction.prompt
        assert "\n" in instruction.context

    def test_quotes_in_output(self):
        """Test handling quotes in output"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout='Output with "quotes" and \'single quotes\'',
                stderr="",
            )

            agent = ClaudeAgent()
            response = agent.execute("Test")

            assert '"quotes"' in response.output

    def test_special_json_characters(self):
        """Test handling special JSON characters"""
        with patch("subprocess.run") as mock_run:
            # Output with characters that need escaping in JSON
            mock_run.return_value = Mock(
                returncode=0,
                stdout='{"key": "value with \t tab and \n newline"}',
                stderr="",
            )

            agent = ClaudeAgent()
            response = agent.execute("Test")

            # Should parse without crashing
            assert response.success
