"""
Verification Checkers

Various checkers for verifying implementation quality and correctness.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import subprocess
import os
import re


@dataclass
class CheckResult:
    """Result of a single check"""
    name: str
    passed: bool
    score: float = 1.0  # 0.0 to 1.0
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VerificationReport:
    """Complete verification report"""
    passed: bool
    overall_score: float
    checks: List[CheckResult] = field(default_factory=list)
    summary: str = ""

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def total_count(self) -> int:
        return len(self.checks)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "overall_score": self.overall_score,
            "passed_count": self.passed_count,
            "total_count": self.total_count,
            "summary": self.summary,
            "checks": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "score": c.score,
                    "message": c.message,
                    "details": c.details,
                }
                for c in self.checks
            ],
        }


class IChecker(ABC):
    """Abstract checker interface"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Checker name"""
        pass

    @abstractmethod
    def check(self, context: Dict[str, Any]) -> CheckResult:
        """
        Perform check.

        Args:
            context: Check context

        Returns:
            CheckResult
        """
        pass


class SyntaxChecker(IChecker):
    """Checks code syntax validity"""

    SYNTAX_COMMANDS = {
        ".py": ["python", "-m", "py_compile"],
        ".js": ["node", "--check"],
        ".ts": ["npx", "tsc", "--noEmit"],
        ".go": ["go", "build", "-n"],
        ".rs": ["rustfmt", "--check"],
        ".cpp": ["g++", "-fsyntax-only"],
        ".c": ["gcc", "-fsyntax-only"],
    }

    @property
    def name(self) -> str:
        return "syntax"

    def check(self, context: Dict[str, Any]) -> CheckResult:
        """
        Check syntax of files.

        Context should contain:
            - files: List of file paths
            - work_dir: Working directory
        """
        files = context.get("files", [])
        work_dir = context.get("work_dir", os.getcwd())

        if not files:
            return CheckResult(
                name=self.name,
                passed=True,
                message="No files to check",
            )

        errors = []
        for file_path in files:
            error = self._check_file_syntax(file_path, work_dir)
            if error:
                errors.append(error)

        passed = len(errors) == 0
        score = 1.0 - (len(errors) / len(files)) if files else 1.0

        return CheckResult(
            name=self.name,
            passed=passed,
            score=max(0.0, score),
            message=f"Checked {len(files)} files, {len(errors)} syntax errors",
            details={"errors": errors},
        )

    def _check_file_syntax(self, file_path: str, work_dir: str) -> Optional[str]:
        """Check single file syntax"""
        ext = os.path.splitext(file_path)[1].lower()
        cmd = self.SYNTAX_COMMANDS.get(ext)

        if not cmd:
            return None  # Unknown file type, skip

        full_path = os.path.join(work_dir, file_path)
        if not os.path.exists(full_path):
            return f"File not found: {file_path}"

        try:
            result = subprocess.run(
                cmd + [full_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return f"{file_path}: {result.stderr[:200]}"
        except subprocess.TimeoutExpired:
            return f"{file_path}: Syntax check timed out"
        except FileNotFoundError:
            return None  # Tool not available, skip

        return None


class TestChecker(IChecker):
    """Runs tests and checks results"""

    TEST_COMMANDS = {
        "python": ["python", "-m", "pytest", "-v"],
        "javascript": ["npm", "test"],
        "typescript": ["npm", "test"],
        "go": ["go", "test", "./..."],
        "rust": ["cargo", "test"],
    }

    @property
    def name(self) -> str:
        return "tests"

    def check(self, context: Dict[str, Any]) -> CheckResult:
        """
        Run tests.

        Context should contain:
            - work_dir: Working directory
            - language: Programming language
            - test_command: Optional custom test command
        """
        work_dir = context.get("work_dir", os.getcwd())
        language = context.get("language", "python")
        custom_cmd = context.get("test_command")

        cmd = custom_cmd.split() if custom_cmd else self.TEST_COMMANDS.get(language)

        if not cmd:
            return CheckResult(
                name=self.name,
                passed=True,
                score=0.5,
                message=f"No test command for {language}",
            )

        try:
            result = subprocess.run(
                cmd,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=300,
            )

            passed = result.returncode == 0
            output = result.stdout + result.stderr

            # Try to parse test results
            stats = self._parse_test_output(output)

            if stats["total"] > 0:
                score = stats["passed"] / stats["total"]
            else:
                score = 1.0 if passed else 0.0

            return CheckResult(
                name=self.name,
                passed=passed,
                score=score,
                message=f"Tests: {stats['passed']}/{stats['total']} passed",
                details={
                    "output": output[:2000],
                    "stats": stats,
                },
            )

        except subprocess.TimeoutExpired:
            return CheckResult(
                name=self.name,
                passed=False,
                score=0.0,
                message="Tests timed out",
            )
        except Exception as e:
            return CheckResult(
                name=self.name,
                passed=False,
                score=0.0,
                message=f"Test execution failed: {e}",
            )

    def _parse_test_output(self, output: str) -> Dict[str, int]:
        """Parse test output for statistics"""
        stats = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}

        # pytest format: "X passed, Y failed"
        pytest_match = re.search(r"(\d+) passed", output)
        if pytest_match:
            stats["passed"] = int(pytest_match.group(1))

        failed_match = re.search(r"(\d+) failed", output)
        if failed_match:
            stats["failed"] = int(failed_match.group(1))

        skipped_match = re.search(r"(\d+) skipped", output)
        if skipped_match:
            stats["skipped"] = int(skipped_match.group(1))

        stats["total"] = stats["passed"] + stats["failed"] + stats["skipped"]

        return stats


class GoalMatcher(IChecker):
    """Matches implementation against goal criteria"""

    def __init__(self, agent=None):
        """
        Initialize matcher.

        Args:
            agent: Optional AI agent for intelligent matching
        """
        self.agent = agent

    @property
    def name(self) -> str:
        return "goal_match"

    def check(self, context: Dict[str, Any]) -> CheckResult:
        """
        Check if implementation matches goal.

        Context should contain:
            - goal: Goal description
            - implementation: Implementation description or output
            - criteria: List of acceptance criteria
        """
        goal = context.get("goal", "")
        implementation = context.get("implementation", "")
        criteria = context.get("criteria", [])

        if not goal or not implementation:
            return CheckResult(
                name=self.name,
                passed=False,
                score=0.0,
                message="Missing goal or implementation",
            )

        if self.agent:
            return self._check_with_agent(goal, implementation, criteria)

        # Simple keyword-based matching
        return self._simple_match(goal, implementation, criteria)

    def _check_with_agent(
        self,
        goal: str,
        implementation: str,
        criteria: List[str],
    ) -> CheckResult:
        """Use AI agent for matching"""
        criteria_text = "\n".join(f"- {c}" for c in criteria) if criteria else "None specified"

        prompt = f"""Evaluate if the implementation meets the goal.

GOAL:
{goal}

ACCEPTANCE CRITERIA:
{criteria_text}

IMPLEMENTATION:
{implementation[:3000]}

Respond with JSON:
{{
    "matches": true | false,
    "score": 0.0 to 1.0,
    "matched_criteria": ["list of met criteria"],
    "unmatched_criteria": ["list of unmet criteria"],
    "assessment": "brief assessment"
}}"""

        response = self.agent.execute(prompt)

        if not response.success:
            return CheckResult(
                name=self.name,
                passed=False,
                score=0.0,
                message=f"Agent check failed: {response.error}",
            )

        try:
            import json
            output = response.output.strip()
            if "```json" in output:
                output = output.split("```json")[1].split("```")[0]
            elif "```" in output:
                output = output.split("```")[1].split("```")[0]

            data = json.loads(output)

            return CheckResult(
                name=self.name,
                passed=data.get("matches", False),
                score=float(data.get("score", 0.0)),
                message=data.get("assessment", ""),
                details={
                    "matched": data.get("matched_criteria", []),
                    "unmatched": data.get("unmatched_criteria", []),
                },
            )
        except Exception as e:
            return CheckResult(
                name=self.name,
                passed=False,
                score=0.0,
                message=f"Failed to parse response: {e}",
            )

    def _simple_match(
        self,
        goal: str,
        implementation: str,
        criteria: List[str],
    ) -> CheckResult:
        """Simple keyword-based matching"""
        # Extract keywords from goal
        goal_words = set(
            word.lower()
            for word in re.findall(r"\b\w+\b", goal)
            if len(word) > 3
        )

        impl_words = set(
            word.lower()
            for word in re.findall(r"\b\w+\b", implementation)
            if len(word) > 3
        )

        # Calculate overlap
        common = goal_words & impl_words
        if goal_words:
            score = len(common) / len(goal_words)
        else:
            score = 0.5

        return CheckResult(
            name=self.name,
            passed=score >= 0.5,
            score=min(1.0, score),
            message=f"Keyword match: {len(common)}/{len(goal_words)} keywords",
        )


class QualityChecker(IChecker):
    """Checks code quality metrics"""

    @property
    def name(self) -> str:
        return "quality"

    def check(self, context: Dict[str, Any]) -> CheckResult:
        """
        Check code quality.

        Context should contain:
            - files: List of file paths
            - work_dir: Working directory
            - requirements: Quality requirements
        """
        files = context.get("files", [])
        work_dir = context.get("work_dir", os.getcwd())
        requirements = context.get("requirements", [])

        issues = []
        score = 1.0

        for file_path in files:
            file_issues = self._check_file_quality(file_path, work_dir)
            issues.extend(file_issues)

        # Deduct for issues
        if issues:
            score = max(0.0, 1.0 - (len(issues) * 0.1))

        return CheckResult(
            name=self.name,
            passed=score >= 0.7,
            score=score,
            message=f"Found {len(issues)} quality issues",
            details={"issues": issues},
        )

    def _check_file_quality(self, file_path: str, work_dir: str) -> List[str]:
        """Check single file quality"""
        issues = []
        full_path = os.path.join(work_dir, file_path)

        if not os.path.exists(full_path):
            return [f"File not found: {file_path}"]

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.split("\n")

            # Check for common issues
            if len(lines) > 500:
                issues.append(f"{file_path}: File too long ({len(lines)} lines)")

            for i, line in enumerate(lines, 1):
                if len(line) > 120:
                    issues.append(f"{file_path}:{i}: Line too long ({len(line)} chars)")
                    break  # Only report first occurrence

            # Check for debugging code
            if "print(" in content or "console.log" in content:
                issues.append(f"{file_path}: Contains debug output")

            # Check for TODO/FIXME
            if "TODO" in content or "FIXME" in content:
                issues.append(f"{file_path}: Contains TODO/FIXME comments")

        except Exception as e:
            issues.append(f"{file_path}: Could not read file: {e}")

        return issues


class VerificationChecker:
    """
    Main verification checker that combines multiple checks.
    """

    def __init__(self, checkers: List[IChecker] = None, agent=None):
        """
        Initialize checker.

        Args:
            checkers: List of checkers to use
            agent: Optional AI agent for intelligent checks
        """
        self.agent = agent

        if checkers is None:
            self.checkers = [
                SyntaxChecker(),
                TestChecker(),
                GoalMatcher(agent),
                QualityChecker(),
            ]
        else:
            self.checkers = checkers

    def verify(self, context: Dict[str, Any]) -> VerificationReport:
        """
        Run all checks.

        Args:
            context: Verification context

        Returns:
            VerificationReport
        """
        results = []

        for checker in self.checkers:
            try:
                result = checker.check(context)
                results.append(result)
            except Exception as e:
                results.append(CheckResult(
                    name=checker.name,
                    passed=False,
                    score=0.0,
                    message=f"Check failed: {e}",
                ))

        # Calculate overall
        if results:
            overall_score = sum(r.score for r in results) / len(results)
            passed = all(r.passed for r in results)
        else:
            overall_score = 0.0
            passed = False

        # Generate summary
        summary_parts = []
        for r in results:
            status = "PASS" if r.passed else "FAIL"
            summary_parts.append(f"{r.name}: {status} ({r.score:.1%})")

        return VerificationReport(
            passed=passed,
            overall_score=overall_score,
            checks=results,
            summary=" | ".join(summary_parts),
        )

    def add_checker(self, checker: IChecker) -> None:
        """Add a checker"""
        self.checkers.append(checker)

    def remove_checker(self, name: str) -> None:
        """Remove a checker by name"""
        self.checkers = [c for c in self.checkers if c.name != name]
