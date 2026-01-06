"""
Master Role Implementation

The Master role is responsible for:
- Analyzing the current state
- Deciding next steps
- Verifying Worker implementations
- Creating corrections when needed
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


class MasterRole(IRoleStrategy):
    """
    Master role implementation.

    The Master analyzes, plans, decides, and verifies.
    Can be assigned to either Claude or Codex.
    """

    def __init__(self, agent: IAgent):
        super().__init__(agent)
        self._analysis_cache: Dict[str, str] = {}

    @property
    def role_name(self) -> str:
        return "master"

    def decide_next_step(
        self,
        goal_description: str,
        current_state: Dict[str, Any],
        history: List[Dict[str, Any]],
    ) -> Decision:
        """
        Analyze state and decide next step toward goal.

        Uses the agent to analyze the current situation and
        determine what action to take next.
        """
        # Build context for decision
        history_summary = self._summarize_history(history)
        state_summary = self._format_state(current_state)

        prompt = f"""You are the MASTER in an AI orchestration system.
Your job is to decide the next step toward achieving a goal.

GOAL:
{goal_description}

CURRENT STATE:
{state_summary}

HISTORY OF PREVIOUS STEPS:
{history_summary}

Based on this information, decide what to do next.

Respond in this exact JSON format:
{{
    "decision_type": "IMPLEMENT" | "SKIP" | "DONE" | "RETRY" | "CORRECT",
    "instruction": "Detailed instruction for the worker (if IMPLEMENT/CORRECT/RETRY)",
    "reason": "Why this decision was made",
    "expected_outcome": "What should result from this step"
}}

Rules:
- Use DONE if the goal is achieved
- Use IMPLEMENT for new work
- Use SKIP if a step is unnecessary
- Use RETRY if the last step failed but should be retried
- Use CORRECT if the last step had issues that need fixing"""

        response = self.agent.execute(prompt)

        if not response.success:
            return Decision(
                type=DecisionType.ERROR,
                reason=f"Failed to decide: {response.error}",
            )

        # Parse response
        try:
            parsed = self._parse_decision_response(response.output)
            return parsed
        except Exception as e:
            return Decision(
                type=DecisionType.ERROR,
                reason=f"Failed to parse decision: {e}",
            )

    def implement_step(self, instruction: Instruction) -> AgentResponse:
        """
        Master doesn't typically implement, but can if needed.
        """
        # Build implementation prompt
        prompt = f"""Implement the following:

{instruction.prompt}

Context: {instruction.context}

Expected outcome: {instruction.expected_outcome}

Constraints:
{chr(10).join('- ' + c for c in instruction.constraints) if instruction.constraints else 'None'}

Files to modify: {', '.join(instruction.files_to_modify) if instruction.files_to_modify else 'As needed'}
Files to create: {', '.join(instruction.files_to_create) if instruction.files_to_create else 'As needed'}"""

        return self.agent.execute(prompt)

    def verify_implementation(
        self,
        instruction: Instruction,
        response: AgentResponse,
    ) -> VerificationResult:
        """
        Verify that Worker's implementation meets expectations.
        """
        prompt = f"""You are verifying an implementation.

ORIGINAL INSTRUCTION:
{instruction.prompt}

EXPECTED OUTCOME:
{instruction.expected_outcome}

IMPLEMENTATION RESULT:
Success: {response.success}
Output: {response.output}
Files Modified: {', '.join(response.files_modified)}
Files Created: {', '.join(response.files_created)}
Errors: {response.error or 'None'}

Verify the implementation and respond in this exact JSON format:
{{
    "passed": true | false,
    "score": 0.0 to 1.0,
    "issues": ["list of issues if any"],
    "suggestions": ["list of improvement suggestions"]
}}

Be thorough but fair in your assessment."""

        verify_response = self.agent.execute(prompt)

        if not verify_response.success:
            return VerificationResult(
                passed=False,
                score=0.0,
                issues=[f"Verification failed: {verify_response.error}"],
            )

        try:
            return self._parse_verification_response(verify_response.output)
        except Exception as e:
            return VerificationResult(
                passed=False,
                score=0.0,
                issues=[f"Failed to parse verification: {e}"],
            )

    def create_correction(
        self,
        original_instruction: Instruction,
        issues: List[str],
    ) -> Instruction:
        """
        Create a correction instruction based on issues found.
        """
        issues_text = "\n".join(f"- {issue}" for issue in issues)

        prompt = f"""Create a correction instruction.

ORIGINAL INSTRUCTION:
{original_instruction.prompt}

ISSUES FOUND:
{issues_text}

Create a new instruction that:
1. Addresses all the issues
2. Maintains the original intent
3. Is clear and specific

Respond with just the corrected instruction text."""

        response = self.agent.execute(prompt)

        correction_prompt = response.output if response.success else (
            f"Fix the following issues in the previous implementation:\n{issues_text}"
        )

        return Instruction(
            prompt=correction_prompt,
            context=f"Correction for: {original_instruction.prompt}",
            files_to_modify=original_instruction.files_to_modify,
            files_to_create=original_instruction.files_to_create,
            constraints=original_instruction.constraints + ["Fix all previously identified issues"],
            expected_outcome=original_instruction.expected_outcome,
            max_attempts=original_instruction.max_attempts - 1,
        )

    def analyze_codebase(
        self,
        work_dir: str,
        focus_areas: List[str] = None,
    ) -> Dict[str, Any]:
        """
        Analyze a codebase to understand its structure.
        """
        focus_text = ""
        if focus_areas:
            focus_text = f"\nFocus on: {', '.join(focus_areas)}"

        prompt = f"""Analyze the codebase in the current directory.
{focus_text}

Provide:
1. Project structure overview
2. Key components and their purposes
3. Entry points
4. Dependencies
5. Potential areas of concern

Respond in JSON format."""

        response = self.agent.execute(prompt, work_dir)

        if response.success:
            try:
                return json.loads(response.output)
            except json.JSONDecodeError:
                return {"analysis": response.output}
        return {"error": response.error}

    def _summarize_history(self, history: List[Dict[str, Any]]) -> str:
        """Summarize iteration history."""
        if not history:
            return "No previous steps."

        summaries = []
        for i, item in enumerate(history[-5:], 1):  # Last 5 items
            status = "SUCCESS" if item.get("success", False) else "FAILED"
            summaries.append(
                f"Step {i}: {item.get('instruction', 'N/A')[:100]}... [{status}]"
            )

        return "\n".join(summaries)

    def _format_state(self, state: Dict[str, Any]) -> str:
        """Format current state for prompt."""
        if not state:
            return "Initial state - no previous work."

        lines = []
        for key, value in state.items():
            if isinstance(value, list):
                lines.append(f"{key}: {', '.join(str(v) for v in value[:5])}")
            else:
                lines.append(f"{key}: {value}")

        return "\n".join(lines)

    def _parse_decision_response(self, output: str) -> Decision:
        """Parse JSON decision response."""
        # Try to extract JSON from response
        output = output.strip()

        # Handle markdown code blocks
        if "```json" in output:
            output = output.split("```json")[1].split("```")[0]
        elif "```" in output:
            output = output.split("```")[1].split("```")[0]

        data = json.loads(output)

        decision_type_map = {
            "IMPLEMENT": DecisionType.IMPLEMENT,
            "SKIP": DecisionType.SKIP,
            "DONE": DecisionType.DONE,
            "RETRY": DecisionType.RETRY,
            "CORRECT": DecisionType.CORRECT,
            "ERROR": DecisionType.ERROR,
        }

        return Decision(
            type=decision_type_map.get(
                data.get("decision_type", "").upper(),
                DecisionType.ERROR,
            ),
            instruction=data.get("instruction", ""),
            reason=data.get("reason", ""),
            expected_outcome=data.get("expected_outcome", ""),
        )

    def _parse_verification_response(self, output: str) -> VerificationResult:
        """Parse JSON verification response."""
        output = output.strip()

        if "```json" in output:
            output = output.split("```json")[1].split("```")[0]
        elif "```" in output:
            output = output.split("```")[1].split("```")[0]

        data = json.loads(output)

        return VerificationResult(
            passed=data.get("passed", False),
            score=float(data.get("score", 0.0)),
            issues=data.get("issues", []),
            suggestions=data.get("suggestions", []),
        )
