"""
Worker Role Implementation

The Worker role is responsible for:
- Implementing instructions from the Master
- Executing code changes
- Running tests
- Reporting results
"""

from typing import Dict, Any, List, Optional
import json

from ..agents.base import IAgent, AgentResponse, AgentCapability
from .base import (
    IRoleStrategy,
    Decision,
    DecisionType,
    VerificationResult,
    Instruction,
)


class WorkerRole(IRoleStrategy):
    """
    Worker role implementation.

    The Worker implements, executes, and reports.
    Can be assigned to either Claude or Codex.
    """

    def __init__(self, agent: IAgent):
        super().__init__(agent)
        self._last_instruction: Optional[Instruction] = None
        self._attempt_count: int = 0

    @property
    def role_name(self) -> str:
        return "worker"

    def decide_next_step(
        self,
        goal_description: str,
        current_state: Dict[str, Any],
        history: List[Dict[str, Any]],
    ) -> Decision:
        """
        Worker typically doesn't decide, but can provide input.

        This implementation provides a simple decision based on state.
        """
        # Worker's decision is usually just to continue or report done
        if current_state.get("goal_achieved", False):
            return Decision(
                type=DecisionType.DONE,
                reason="Goal appears to be achieved based on current state.",
            )

        # Check for blocking errors
        if current_state.get("blocking_error"):
            return Decision(
                type=DecisionType.ERROR,
                reason=f"Blocking error: {current_state['blocking_error']}",
            )

        # Default: ready for next instruction
        return Decision(
            type=DecisionType.IMPLEMENT,
            reason="Ready to implement next instruction.",
        )

    def implement_step(self, instruction: Instruction) -> AgentResponse:
        """
        Implement an instruction.

        This is the Worker's primary function.
        """
        self._last_instruction = instruction
        self._attempt_count += 1

        # Build implementation prompt
        prompt = self._build_implementation_prompt(instruction)

        # Execute with the agent
        response = self.agent.execute(prompt)

        # Enrich response with instruction context
        response.metadata["instruction"] = instruction.prompt[:200]
        response.metadata["attempt"] = self._attempt_count

        return response

    def verify_implementation(
        self,
        instruction: Instruction,
        response: AgentResponse,
    ) -> VerificationResult:
        """
        Worker performs basic self-verification.

        Note: Master should do thorough verification.
        """
        # Basic checks
        issues = []
        suggestions = []

        if not response.success:
            issues.append(f"Execution failed: {response.error}")

        if response.exit_code != 0:
            issues.append(f"Non-zero exit code: {response.exit_code}")

        # Check if expected files were created
        if instruction.files_to_create:
            missing = set(instruction.files_to_create) - set(response.files_created)
            if missing:
                issues.append(f"Expected files not created: {missing}")

        # Calculate score
        score = 1.0
        if issues:
            score = max(0.0, 1.0 - (len(issues) * 0.25))

        return VerificationResult(
            passed=len(issues) == 0 and response.success,
            score=score,
            issues=issues,
            suggestions=suggestions,
        )

    def create_correction(
        self,
        original_instruction: Instruction,
        issues: List[str],
    ) -> Instruction:
        """
        Worker creates a simple correction instruction.
        """
        issues_text = "\n".join(f"- {issue}" for issue in issues)

        return Instruction(
            prompt=f"""Fix the issues from the previous attempt:

Original task: {original_instruction.prompt}

Issues to fix:
{issues_text}

Make the necessary corrections.""",
            context=original_instruction.context,
            files_to_modify=original_instruction.files_to_modify + original_instruction.files_to_create,
            constraints=original_instruction.constraints,
            expected_outcome=original_instruction.expected_outcome,
            max_attempts=original_instruction.max_attempts - 1,
        )

    def _build_implementation_prompt(self, instruction: Instruction) -> str:
        """Build the full implementation prompt."""
        parts = [
            "You are a WORKER implementing code.",
            "",
            "INSTRUCTION:",
            instruction.prompt,
        ]

        if instruction.context:
            parts.extend(["", "CONTEXT:", instruction.context])

        if instruction.files_to_modify:
            parts.extend([
                "",
                "FILES TO MODIFY:",
                *[f"- {f}" for f in instruction.files_to_modify],
            ])

        if instruction.files_to_create:
            parts.extend([
                "",
                "FILES TO CREATE:",
                *[f"- {f}" for f in instruction.files_to_create],
            ])

        if instruction.constraints:
            parts.extend([
                "",
                "CONSTRAINTS:",
                *[f"- {c}" for c in instruction.constraints],
            ])

        if instruction.expected_outcome:
            parts.extend([
                "",
                "EXPECTED OUTCOME:",
                instruction.expected_outcome,
            ])

        parts.extend([
            "",
            "Implement the instruction carefully and completely.",
            "Create or modify files as needed.",
            "Report any issues encountered.",
        ])

        return "\n".join(parts)

    def execute_tests(self, test_command: str) -> AgentResponse:
        """
        Execute tests and report results.
        """
        prompt = f"""Execute the following test command:

{test_command}

Run the tests and provide a summary of:
- Number of tests passed
- Number of tests failed
- Any errors or failures"""

        return self.agent.execute(prompt)

    def apply_fix(self, file_path: str, fix_description: str) -> AgentResponse:
        """
        Apply a specific fix to a file.
        """
        prompt = f"""Apply the following fix to {file_path}:

{fix_description}

Make the change and confirm it was applied."""

        return self.agent.execute(prompt)

    def refactor_code(
        self,
        file_path: str,
        refactor_type: str,
        details: str = "",
    ) -> AgentResponse:
        """
        Refactor code in a file.
        """
        prompt = f"""Refactor the code in {file_path}.

Refactoring type: {refactor_type}
{f'Details: {details}' if details else ''}

Apply the refactoring while maintaining functionality."""

        return self.agent.execute(prompt)

    def generate_documentation(
        self,
        target: str,
        doc_type: str = "docstring",
    ) -> AgentResponse:
        """
        Generate documentation for code.
        """
        prompt = f"""Generate {doc_type} documentation for:

{target}

Create clear, comprehensive documentation."""

        return self.agent.execute(prompt)

    def reset_attempts(self) -> None:
        """Reset attempt counter."""
        self._attempt_count = 0
        self._last_instruction = None
