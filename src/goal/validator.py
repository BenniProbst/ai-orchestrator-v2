"""
Goal Validator

Validates goal achievement against acceptance criteria.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from enum import Enum

from .parser import Goal, AcceptanceCriterion, CriterionStatus
from ..agents.base import IAgent


class ValidationStatus(Enum):
    """Overall validation status"""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    PARTIALLY_ACHIEVED = "partially_achieved"
    ACHIEVED = "achieved"
    FAILED = "failed"


@dataclass
class CriterionValidation:
    """Validation result for a single criterion"""
    criterion: AcceptanceCriterion
    passed: bool
    confidence: float = 1.0  # 0.0 to 1.0
    evidence: str = ""
    issues: List[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    """Complete validation result"""
    status: ValidationStatus
    overall_score: float  # 0.0 to 1.0
    criteria_results: List[CriterionValidation] = field(default_factory=list)
    summary: str = ""
    recommendations: List[str] = field(default_factory=list)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.criteria_results if r.passed)

    @property
    def total_count(self) -> int:
        return len(self.criteria_results)

    @property
    def pass_rate(self) -> float:
        if self.total_count == 0:
            return 0.0
        return self.passed_count / self.total_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "overall_score": self.overall_score,
            "passed_count": self.passed_count,
            "total_count": self.total_count,
            "pass_rate": self.pass_rate,
            "summary": self.summary,
            "recommendations": self.recommendations,
            "criteria_results": [
                {
                    "description": r.criterion.description,
                    "passed": r.passed,
                    "confidence": r.confidence,
                    "evidence": r.evidence,
                    "issues": r.issues,
                }
                for r in self.criteria_results
            ],
        }


class GoalValidator:
    """
    Validates goal achievement.

    Can use an AI agent for intelligent validation or
    simple rule-based validation.
    """

    def __init__(self, agent: Optional[IAgent] = None, strict: bool = True):
        """
        Initialize validator.

        Args:
            agent: Optional AI agent for intelligent validation
            strict: If True, all criteria must pass for goal to be achieved
        """
        self.agent = agent
        self.strict = strict
        self._custom_validators: Dict[str, Callable] = {}

    def validate(
        self,
        goal: Goal,
        context: Dict[str, Any] = None,
    ) -> ValidationResult:
        """
        Validate goal achievement.

        Args:
            goal: Goal to validate
            context: Optional context (files, output, state)

        Returns:
            ValidationResult
        """
        context = context or {}
        criteria_results = []

        for criterion in goal.acceptance_criteria:
            result = self._validate_criterion(criterion, context)
            criteria_results.append(result)

        # Calculate overall score
        if criteria_results:
            overall_score = sum(r.confidence for r in criteria_results if r.passed) / len(criteria_results)
        else:
            overall_score = 0.0

        # Determine status
        status = self._determine_status(criteria_results, overall_score)

        # Generate summary and recommendations
        summary, recommendations = self._generate_feedback(criteria_results, goal)

        return ValidationResult(
            status=status,
            overall_score=overall_score,
            criteria_results=criteria_results,
            summary=summary,
            recommendations=recommendations,
        )

    def validate_criterion(
        self,
        criterion: AcceptanceCriterion,
        context: Dict[str, Any] = None,
    ) -> CriterionValidation:
        """
        Validate a single criterion.

        Args:
            criterion: Criterion to validate
            context: Validation context

        Returns:
            CriterionValidation result
        """
        return self._validate_criterion(criterion, context or {})

    def _validate_criterion(
        self,
        criterion: AcceptanceCriterion,
        context: Dict[str, Any],
    ) -> CriterionValidation:
        """Internal criterion validation."""
        # Check for custom validator
        for tag in criterion.tags:
            if tag in self._custom_validators:
                return self._custom_validators[tag](criterion, context)

        # If already marked completed, verify
        if criterion.completed:
            return CriterionValidation(
                criterion=criterion,
                passed=True,
                confidence=0.9,  # Slightly less confident about pre-marked
                evidence="Marked as completed",
            )

        # Use AI agent if available
        if self.agent:
            return self._validate_with_agent(criterion, context)

        # Default: not validated
        return CriterionValidation(
            criterion=criterion,
            passed=False,
            confidence=0.5,
            evidence="No validation performed",
            issues=["No validator available for this criterion"],
        )

    def _validate_with_agent(
        self,
        criterion: AcceptanceCriterion,
        context: Dict[str, Any],
    ) -> CriterionValidation:
        """Use AI agent to validate criterion."""
        context_str = self._format_context(context)

        prompt = f"""Validate if the following acceptance criterion is met.

CRITERION:
{criterion.description}

CONTEXT:
{context_str}

Respond in this exact JSON format:
{{
    "passed": true | false,
    "confidence": 0.0 to 1.0,
    "evidence": "What evidence supports this conclusion",
    "issues": ["List of issues if not passed"]
}}"""

        response = self.agent.execute(prompt)

        if not response.success:
            return CriterionValidation(
                criterion=criterion,
                passed=False,
                confidence=0.0,
                evidence=f"Validation failed: {response.error}",
            )

        try:
            import json
            output = response.output.strip()

            # Handle markdown code blocks
            if "```json" in output:
                output = output.split("```json")[1].split("```")[0]
            elif "```" in output:
                output = output.split("```")[1].split("```")[0]

            data = json.loads(output)

            return CriterionValidation(
                criterion=criterion,
                passed=data.get("passed", False),
                confidence=float(data.get("confidence", 0.5)),
                evidence=data.get("evidence", ""),
                issues=data.get("issues", []),
            )
        except Exception as e:
            return CriterionValidation(
                criterion=criterion,
                passed=False,
                confidence=0.0,
                evidence=f"Failed to parse validation: {e}",
            )

    def _determine_status(
        self,
        results: List[CriterionValidation],
        score: float,
    ) -> ValidationStatus:
        """Determine overall validation status."""
        if not results:
            return ValidationStatus.NOT_STARTED

        passed = sum(1 for r in results if r.passed)
        total = len(results)

        if passed == 0:
            if score > 0:
                return ValidationStatus.IN_PROGRESS
            return ValidationStatus.NOT_STARTED

        if passed == total:
            return ValidationStatus.ACHIEVED

        if self.strict:
            if passed / total >= 0.5:
                return ValidationStatus.PARTIALLY_ACHIEVED
            return ValidationStatus.IN_PROGRESS

        # Non-strict: 80% is good enough
        if passed / total >= 0.8:
            return ValidationStatus.ACHIEVED
        elif passed / total >= 0.5:
            return ValidationStatus.PARTIALLY_ACHIEVED
        else:
            return ValidationStatus.IN_PROGRESS

    def _generate_feedback(
        self,
        results: List[CriterionValidation],
        goal: Goal,
    ) -> tuple[str, List[str]]:
        """Generate summary and recommendations."""
        passed = [r for r in results if r.passed]
        failed = [r for r in results if not r.passed]

        # Summary
        summary_parts = [
            f"Validated {len(results)} criteria: {len(passed)} passed, {len(failed)} pending/failed.",
        ]

        if failed:
            summary_parts.append("Outstanding items:")
            for r in failed[:3]:  # Top 3
                summary_parts.append(f"  - {r.criterion.description[:50]}...")

        summary = "\n".join(summary_parts)

        # Recommendations
        recommendations = []
        if failed:
            recommendations.append(f"Complete the {len(failed)} remaining acceptance criteria.")

            # Add specific recommendations based on issues
            all_issues = []
            for r in failed:
                all_issues.extend(r.issues)

            if all_issues:
                recommendations.append("Address the following issues:")
                for issue in all_issues[:5]:  # Top 5 issues
                    recommendations.append(f"  - {issue}")

        if not goal.quality_requirements:
            recommendations.append("Consider adding quality requirements to the goal.")

        return summary, recommendations

    def _format_context(self, context: Dict[str, Any]) -> str:
        """Format context for prompt."""
        if not context:
            return "No additional context provided."

        parts = []
        for key, value in context.items():
            if isinstance(value, list):
                parts.append(f"{key}:\n" + "\n".join(f"  - {v}" for v in value[:10]))
            elif isinstance(value, dict):
                import json
                parts.append(f"{key}:\n{json.dumps(value, indent=2)[:500]}")
            else:
                parts.append(f"{key}: {str(value)[:200]}")

        return "\n\n".join(parts)

    def register_validator(
        self,
        tag: str,
        validator: Callable[[AcceptanceCriterion, Dict], CriterionValidation],
    ) -> None:
        """
        Register a custom validator for criteria with specific tag.

        Args:
            tag: Tag to match
            validator: Validation function
        """
        self._custom_validators[tag] = validator

    def update_goal_status(self, goal: Goal, result: ValidationResult) -> Goal:
        """
        Update goal's criteria status based on validation.

        Args:
            goal: Goal to update
            result: Validation result

        Returns:
            Updated Goal
        """
        for validation in result.criteria_results:
            for criterion in goal.acceptance_criteria:
                if criterion.description == validation.criterion.description:
                    if validation.passed:
                        criterion.mark_completed()
                    elif validation.confidence < 0.3:
                        criterion.mark_failed()

        return goal
