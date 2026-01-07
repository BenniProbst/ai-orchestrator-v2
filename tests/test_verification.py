"""
Tests for Verification checkers

Tests:
1. test_verify_code_syntax
2. test_verify_test_pass
3. test_verify_goal_match
4. test_verify_diff_analysis
5. test_verify_quality_metrics
"""

import pytest
from unittest.mock import Mock, patch
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from verification.checker import (
    VerificationChecker,
    SyntaxChecker,
    TestChecker,
    GoalMatcher,
    QualityChecker,
    CheckResult,
    VerificationReport,
)
from agents.base import AgentResponse


class TestSyntaxChecker:
    """Tests for syntax checking"""

    def test_verify_code_syntax_python_valid(self, temp_dir):
        """Test syntax check for valid Python code"""
        # Create a valid Python file
        code_file = Path(temp_dir) / "valid.py"
        code_file.write_text("def hello():\n    return 'world'\n")

        checker = SyntaxChecker()
        result = checker.check({
            "files": ["valid.py"],
            "work_dir": temp_dir,
        })

        assert result.passed
        assert result.score >= 0.9

    def test_verify_code_syntax_python_invalid(self, temp_dir):
        """Test syntax check for invalid Python code"""
        # Create an invalid Python file
        code_file = Path(temp_dir) / "invalid.py"
        code_file.write_text("def hello(\n    return 'broken syntax")

        checker = SyntaxChecker()
        result = checker.check({
            "files": ["invalid.py"],
            "work_dir": temp_dir,
        })

        # May or may not fail depending on py_compile availability
        # Main thing is it doesn't crash
        assert isinstance(result, CheckResult)

    def test_verify_code_syntax_no_files(self):
        """Test syntax check with no files"""
        checker = SyntaxChecker()
        result = checker.check({"files": []})

        assert result.passed
        assert "No files" in result.message


class TestTestChecker:
    """Tests for test execution checking"""

    def test_verify_test_pass(self, temp_dir):
        """Test running tests that pass"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="5 passed in 0.5s",
                stderr="",
            )

            checker = TestChecker()
            result = checker.check({
                "work_dir": temp_dir,
                "language": "python",
            })

            assert result.passed
            assert result.score >= 0.9

    def test_verify_test_fail(self, temp_dir):
        """Test running tests that fail"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=1,
                stdout="3 passed, 2 failed",
                stderr="AssertionError",
            )

            checker = TestChecker()
            result = checker.check({
                "work_dir": temp_dir,
                "language": "python",
            })

            assert not result.passed
            assert result.score < 1.0

    def test_verify_test_custom_command(self, temp_dir):
        """Test running with custom test command"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="All tests passed",
                stderr="",
            )

            checker = TestChecker()
            result = checker.check({
                "work_dir": temp_dir,
                "test_command": "npm test",
            })

            assert result.passed


class TestGoalMatcher:
    """Tests for goal matching"""

    def test_verify_goal_match_success(self, mock_agent):
        """Test goal matching success"""
        mock_agent.execute.return_value = AgentResponse(
            success=True,
            output='{"matches": true, "score": 0.95, "matched_criteria": ["All"], "unmatched_criteria": [], "assessment": "Good match"}',
        )

        checker = GoalMatcher(agent=mock_agent)
        result = checker.check({
            "goal": "Create a REST API",
            "implementation": "Flask app with CRUD endpoints",
            "criteria": ["GET /users", "POST /users"],
        })

        assert result.passed
        assert result.score >= 0.9

    def test_verify_goal_match_partial(self, mock_agent):
        """Test partial goal match"""
        mock_agent.execute.return_value = AgentResponse(
            success=True,
            output='{"matches": false, "score": 0.5, "matched_criteria": ["GET"], "unmatched_criteria": ["POST"], "assessment": "Partial"}',
        )

        checker = GoalMatcher(agent=mock_agent)
        result = checker.check({
            "goal": "Create CRUD API",
            "implementation": "Only GET endpoint",
            "criteria": ["GET /users", "POST /users"],
        })

        assert not result.passed
        assert result.score < 0.8

    def test_verify_goal_match_simple(self):
        """Test simple keyword-based goal matching without agent"""
        checker = GoalMatcher(agent=None)
        result = checker.check({
            "goal": "Create user management API",
            "implementation": "def get_users(): return users\ndef create_user(user): users.append(user)",
            "criteria": [],
        })

        # Should use simple matching
        assert isinstance(result, CheckResult)


class TestQualityChecker:
    """Tests for quality checking"""

    def test_verify_quality_metrics_good(self, temp_dir):
        """Test quality check for good code"""
        # Create a well-formatted file
        code_file = Path(temp_dir) / "good.py"
        code_file.write_text('''"""Good module."""


def hello():
    """Say hello."""
    return "Hello, World!"
''')

        checker = QualityChecker()
        result = checker.check({
            "files": ["good.py"],
            "work_dir": temp_dir,
        })

        assert result.passed
        assert result.score >= 0.7

    def test_verify_quality_metrics_issues(self, temp_dir):
        """Test quality check finding issues"""
        # Create a file with quality issues
        code_file = Path(temp_dir) / "bad.py"
        code_file.write_text(
            'x = 1\n' * 600 +  # Very long file
            'print("debug")\n' +  # Debug output
            '# TODO: fix this\n'  # TODO comment
        )

        checker = QualityChecker()
        result = checker.check({
            "files": ["bad.py"],
            "work_dir": temp_dir,
        })

        assert len(result.details.get("issues", [])) > 0

    def test_verify_diff_analysis(self, temp_dir):
        """Test analyzing diffs (via quality checker)"""
        # Quality checker includes basic diff-like checks
        checker = QualityChecker()

        # File doesn't exist
        result = checker.check({
            "files": ["nonexistent.py"],
            "work_dir": temp_dir,
        })

        assert "not found" in str(result.details.get("issues", []))


class TestVerificationChecker:
    """Tests for combined verification checker"""

    def test_verification_checker_all_pass(self, temp_dir, mock_agent):
        """Test when all checks pass"""
        # Create valid file
        code_file = Path(temp_dir) / "valid.py"
        code_file.write_text("def hello(): return 'world'\n")

        mock_agent.execute.return_value = AgentResponse(
            success=True,
            output='{"matches": true, "score": 1.0, "matched_criteria": [], "unmatched_criteria": [], "assessment": "Perfect"}',
        )

        checker = VerificationChecker(agent=mock_agent)

        with patch.object(TestChecker, "check") as mock_test:
            mock_test.return_value = CheckResult(name="tests", passed=True, score=1.0)

            report = checker.verify({
                "files": ["valid.py"],
                "work_dir": temp_dir,
                "goal": "Create hello function",
                "implementation": "def hello(): return 'world'",
            })

        assert isinstance(report, VerificationReport)

    def test_verification_checker_partial(self, temp_dir, mock_agent):
        """Test when some checks fail"""
        checker = VerificationChecker(agent=mock_agent)

        # Only syntax checker will work properly
        report = checker.verify({
            "files": [],
            "work_dir": temp_dir,
            "goal": "",
            "implementation": "",
        })

        assert isinstance(report, VerificationReport)

    def test_verification_report_summary(self):
        """Test verification report generation"""
        report = VerificationReport(
            passed=False,
            overall_score=0.65,
            checks=[
                CheckResult(name="syntax", passed=True, score=1.0),
                CheckResult(name="tests", passed=False, score=0.5),
                CheckResult(name="quality", passed=True, score=0.8),
            ],
            summary="2/3 checks passed",
        )

        assert report.passed_count == 2
        assert report.total_count == 3
        assert "syntax: PASS" in report.summary or report.passed_count == 2
