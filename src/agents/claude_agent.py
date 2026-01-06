"""
Claude Code CLI Agent Implementation

Adapter for using Claude Code CLI as an AI agent in the orchestration system.
"""

import subprocess
import json
import os
import shutil
from typing import Optional, List
from pathlib import Path

from .base import (
    IAgent,
    AgentType,
    AgentCapability,
    AgentResponse,
    AgentConfig,
)


class ClaudeAgent(IAgent):
    """
    Claude Code CLI agent implementation.

    Uses the Claude Code CLI to execute prompts and analyze code.
    Claude excels at analysis, planning, and strategic decisions.
    """

    def __init__(self, config: Optional[AgentConfig] = None):
        if config is None:
            config = AgentConfig(
                command="claude",
                timeout=120,
                sandbox=True,
                json_output=True,
            )
        super().__init__(config)

        self._capabilities = [
            AgentCapability.CODE_ANALYSIS,
            AgentCapability.CODE_REVIEW,
            AgentCapability.PLANNING,
            AgentCapability.VERIFICATION,
            AgentCapability.DOCUMENTATION,
            AgentCapability.CODE_GENERATION,
            AgentCapability.REFACTORING,
        ]

    @property
    def agent_type(self) -> AgentType:
        return AgentType.CLAUDE

    def execute(self, prompt: str, work_dir: Optional[str] = None) -> AgentResponse:
        """
        Execute a prompt using Claude Code CLI.

        Args:
            prompt: The instruction to execute
            work_dir: Working directory for execution

        Returns:
            AgentResponse with results
        """
        work_dir = work_dir or self.config.work_dir or os.getcwd()

        cmd = [self.config.command]

        # Add print mode for non-interactive execution
        cmd.extend(["--print", prompt])

        # Add output format if needed
        if self.config.json_output:
            cmd.extend(["--output-format", "json"])

        try:
            import time
            start_time = time.time()

            result = subprocess.run(
                cmd,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=self.config.timeout,
                env={**os.environ, **self.config.env_vars},
            )

            execution_time = time.time() - start_time

            # Parse output
            output = result.stdout
            files_modified = []
            files_created = []
            metadata = {}

            # Try to parse JSON output
            if self.config.json_output and output.strip():
                try:
                    parsed = json.loads(output)
                    if isinstance(parsed, dict):
                        output = parsed.get("result", output)
                        files_modified = parsed.get("files_modified", [])
                        files_created = parsed.get("files_created", [])
                        metadata = parsed.get("metadata", {})
                except json.JSONDecodeError:
                    pass  # Keep raw output

            return AgentResponse(
                success=result.returncode == 0,
                output=output,
                files_modified=files_modified,
                files_created=files_created,
                error=result.stderr if result.returncode != 0 else None,
                exit_code=result.returncode,
                execution_time=execution_time,
                metadata=metadata,
            )

        except subprocess.TimeoutExpired:
            return AgentResponse.error_response(
                f"Claude execution timed out after {self.config.timeout}s",
                exit_code=-1,
            )
        except FileNotFoundError:
            return AgentResponse.error_response(
                f"Claude CLI not found: {self.config.command}",
                exit_code=-2,
            )
        except Exception as e:
            return AgentResponse.error_response(str(e), exit_code=-3)

    def analyze(self, context: str, question: str) -> str:
        """
        Analyze context and answer a question.

        Args:
            context: Code or output to analyze
            question: What to determine

        Returns:
            Analysis result
        """
        prompt = f"""Analyze the following context and answer the question.

CONTEXT:
{context}

QUESTION:
{question}

Provide a clear, concise analysis."""

        response = self.execute(prompt)
        return response.output if response.success else f"Analysis failed: {response.error}"

    def verify(self, expected: str, actual: str) -> bool:
        """
        Verify actual output matches expected.

        Args:
            expected: Expected outcome description
            actual: Actual output/result

        Returns:
            True if verification passes
        """
        prompt = f"""Verify if the actual result matches the expected outcome.

EXPECTED:
{expected}

ACTUAL:
{actual}

Answer with only "PASS" if it matches or "FAIL" if it doesn't match."""

        response = self.execute(prompt)
        if response.success:
            return "PASS" in response.output.upper()
        return False

    def is_available(self) -> bool:
        """Check if Claude CLI is available."""
        return shutil.which(self.config.command) is not None

    def plan_implementation(
        self,
        goal: str,
        current_state: str,
        constraints: List[str] = None,
    ) -> str:
        """
        Create an implementation plan for a goal.

        Args:
            goal: The goal to achieve
            current_state: Current state of the project
            constraints: Any constraints to consider

        Returns:
            Implementation plan as string
        """
        constraints_text = ""
        if constraints:
            constraints_text = "\n".join(f"- {c}" for c in constraints)
            constraints_text = f"\nCONSTRAINTS:\n{constraints_text}"

        prompt = f"""Create a step-by-step implementation plan.

GOAL:
{goal}

CURRENT STATE:
{current_state}
{constraints_text}

Provide numbered steps with clear, actionable instructions."""

        response = self.execute(prompt)
        return response.output if response.success else ""

    def review_code(self, code: str, criteria: List[str] = None) -> str:
        """
        Review code against criteria.

        Args:
            code: Code to review
            criteria: Review criteria

        Returns:
            Review results
        """
        criteria_text = ""
        if criteria:
            criteria_text = "\n".join(f"- {c}" for c in criteria)
            criteria_text = f"\nREVIEW CRITERIA:\n{criteria_text}"

        prompt = f"""Review the following code.

CODE:
```
{code}
```
{criteria_text}

Provide:
1. Issues found (if any)
2. Suggestions for improvement
3. Overall assessment (GOOD/NEEDS_WORK/POOR)"""

        response = self.execute(prompt)
        return response.output if response.success else ""
