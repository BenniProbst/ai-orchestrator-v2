"""
Tests for Goal parsing and validation

Tests:
1. test_goal_parse_simple
2. test_goal_parse_complex
3. test_goal_parse_with_criteria
4. test_goal_validate_achieved
5. test_goal_validate_partial
6. test_goal_validate_failed
7. test_goal_criteria_extraction
8. test_goal_progress_tracking
"""

import pytest
from pathlib import Path
import tempfile

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from goal.parser import GoalParser, Goal, AcceptanceCriterion, CriterionStatus
from goal.validator import GoalValidator, ValidationResult, ValidationStatus
from goal.progress import ProgressTracker, ProgressState, IterationRecord


class TestGoalParsing:
    """Tests for Goal parsing"""

    def test_goal_parse_simple(self, temp_goal_file):
        """Test parsing a simple goal file"""
        parser = GoalParser()
        goal = parser.parse_file(temp_goal_file)

        assert goal.title == "Test Goal"
        assert len(goal.acceptance_criteria) == 3

    def test_goal_parse_complex(self, temp_dir):
        """Test parsing a complex goal file"""
        complex_goal = """# Complex Multi-Feature Goal

## Description
This is a complex goal with many features and requirements.
It spans multiple lines and has detailed descriptions.

## Acceptance Criteria
- [ ] Implement user authentication
- [ ] Add role-based access control
- [ ] Create API endpoints for CRUD
- [x] Setup project structure
- [ ] Write comprehensive tests

## Quality Requirements
- 90% test coverage
- No critical security issues
- Performance under 100ms response time
- Documentation for all public APIs

## Constraints
- Use Python 3.11+
- PostgreSQL database
- Docker deployment
- No external paid services
"""
        goal_path = Path(temp_dir) / "complex_goal.txt"
        goal_path.write_text(complex_goal)

        parser = GoalParser()
        goal = parser.parse_file(str(goal_path))

        assert goal.title == "Complex Multi-Feature Goal"
        assert len(goal.acceptance_criteria) == 5
        assert len(goal.quality_requirements) == 4
        assert len(goal.constraints) == 4
        assert goal.completed_criteria == 1

    def test_goal_parse_with_criteria(self, sample_goal):
        """Test parsing goal with pre-defined criteria"""
        assert sample_goal.total_criteria == 3
        assert sample_goal.completed_criteria == 1
        assert sample_goal.progress_percentage == pytest.approx(33.33, rel=0.1)

    def test_goal_parse_empty_file(self, empty_goal_file):
        """Test parsing empty goal file raises error"""
        parser = GoalParser()
        with pytest.raises(ValueError):
            parser.parse_file(empty_goal_file)

    def test_goal_parse_nonexistent_file(self):
        """Test parsing nonexistent file raises error"""
        parser = GoalParser()
        with pytest.raises(FileNotFoundError):
            parser.parse_file("/nonexistent/path/GOAL.txt")


class TestGoalValidation:
    """Tests for Goal validation"""

    def test_goal_validate_achieved(self, completed_goal, mock_agent):
        """Test validating a fully achieved goal"""
        validator = GoalValidator(agent=mock_agent, strict=True)

        # All criteria are completed
        result = validator.validate(completed_goal)

        assert result.status in [ValidationStatus.ACHIEVED, ValidationStatus.PARTIALLY_ACHIEVED]
        assert result.overall_score >= 0.8

    def test_goal_validate_partial(self, sample_goal, mock_agent):
        """Test validating a partially achieved goal"""
        mock_agent.execute.return_value = AgentResponse(
            success=True,
            output='{"passed": true, "confidence": 0.8, "evidence": "Looks good", "issues": []}',
        )

        validator = GoalValidator(agent=mock_agent)
        result = validator.validate(sample_goal)

        # One of three criteria is completed
        assert result.status in [
            ValidationStatus.PARTIALLY_ACHIEVED,
            ValidationStatus.IN_PROGRESS,
        ]

    def test_goal_validate_failed(self, simple_goal, mock_agent):
        """Test validating a failed goal"""
        mock_agent.execute.return_value = AgentResponse(
            success=True,
            output='{"passed": false, "confidence": 0.2, "evidence": "Not implemented", "issues": ["Missing"]}',
        )

        validator = GoalValidator(agent=mock_agent, strict=True)
        result = validator.validate(simple_goal)

        assert result.status != ValidationStatus.ACHIEVED

    def test_goal_validate_without_agent(self, sample_goal):
        """Test validation without AI agent (basic mode)"""
        validator = GoalValidator(agent=None)
        result = validator.validate(sample_goal)

        # Should still work, but less confident
        assert result is not None


class TestGoalCriteriaExtraction:
    """Tests for criteria extraction"""

    def test_goal_criteria_extraction(self):
        """Test extracting criteria from markdown"""
        parser = GoalParser()
        content = """# Test

## Acceptance Criteria
- [ ] First unchecked
- [x] Second checked
- [ ] Third unchecked
"""
        goal = parser.parse_content(content)

        assert len(goal.acceptance_criteria) == 3
        assert goal.acceptance_criteria[0].completed is False
        assert goal.acceptance_criteria[1].completed is True
        assert goal.acceptance_criteria[2].completed is False

    def test_goal_get_pending_criteria(self, sample_goal):
        """Test getting pending criteria"""
        pending = sample_goal.get_pending_criteria()

        assert len(pending) == 2
        for c in pending:
            assert not c.completed

    def test_goal_get_next_criterion(self, sample_goal):
        """Test getting next criterion to work on"""
        next_c = sample_goal.get_next_criterion()

        assert next_c is not None
        assert not next_c.completed


class TestGoalProgressTracking:
    """Tests for progress tracking"""

    def test_goal_progress_tracking(self, sample_goal, temp_dir):
        """Test progress tracker"""
        tracker = ProgressTracker(
            goal=sample_goal,
            session_dir=temp_dir,
            auto_save=False,
        )

        tracker.start()
        assert tracker.state == ProgressState.STARTING

        # Record iteration
        tracker.record_iteration(
            action="Implement feature",
            result="Success",
            success=True,
        )

        assert tracker.current_iteration == 1
        assert tracker.state == ProgressState.IN_PROGRESS

    def test_goal_progress_persistence(self, sample_goal, temp_dir):
        """Test progress persistence"""
        tracker = ProgressTracker(
            goal=sample_goal,
            session_dir=temp_dir,
            auto_save=False,
        )

        tracker.start()
        tracker.record_iteration("Action", "Result", True)

        # Save
        path = tracker.save()
        assert Path(path).exists()

        # Load in new tracker
        new_tracker = ProgressTracker(sample_goal, temp_dir, auto_save=False)
        new_tracker.load(path)

        assert new_tracker.current_iteration == 1

    def test_goal_progress_summary(self, sample_goal, temp_dir):
        """Test progress summary generation"""
        tracker = ProgressTracker(sample_goal, temp_dir, auto_save=False)
        tracker.start()

        summary = tracker.get_summary()

        assert "Test Goal" in summary
        assert "Progress:" in summary


class TestGoalMarkdownOutput:
    """Tests for Goal to markdown conversion"""

    def test_goal_to_markdown(self, sample_goal):
        """Test converting goal back to markdown"""
        parser = GoalParser()
        markdown = parser.to_markdown(sample_goal)

        assert "# Test Goal" in markdown
        assert "## Acceptance Criteria" in markdown
        assert "[ ]" in markdown  # Unchecked items
        assert "[x]" in markdown  # Checked item


# Import for type hints in fixtures
from agents.base import AgentResponse
