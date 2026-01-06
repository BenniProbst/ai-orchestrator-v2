"""
OpenAI Codex CLI Agent Implementation

Adapter for using Codex CLI as an AI agent in the orchestration system.
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


class CodexAgent(IAgent):
    """
    Codex CLI agent implementation.

    Uses the OpenAI Codex CLI to execute prompts and generate code.
    Codex excels at code generation, implementation, and execution.
    """

    def __init__(self, config: Optional[AgentConfig] = None):
        if config is None:
            config = AgentConfig(
                command="codex",
                timeout=300,
                sandbox=True,
                full_auto=True,
                json_output=True,
            )
        super().__init__(config)

        self._capabilities = [
            AgentCapability.CODE_GENERATION,
            AgentCapability.FILE_OPERATIONS,
            AgentCapability.TEST_EXECUTION,
            AgentCapability.REFACTORING,
            AgentCapability.CODE_ANALYSIS,
        ]

    @property
    def agent_type(self) -> AgentType:
        return AgentType.CODEX

    def execute(self, prompt: str, work_dir: Optional[str] = None) -> AgentResponse:
        """
        Execute a prompt using Codex CLI.

        Uses 'codex exec' for non-interactive execution.

        Args:
            prompt: The instruction to execute
            work_dir: Working directory for execution

        Returns:
            AgentResponse with results
        """
        work_dir = work_dir or self.config.work_dir or os.getcwd()

        # Build command for exec mode
        cmd = [self.config.command, "exec"]

        # Add flags
        if self.config.full_auto:
            cmd.append("--full-auto")

        if self.config.json_output:
            cmd.append("--json")

        if self.config.sandbox:
            cmd.extend(["--sandbox", "workspace-write"])

        # Add prompt (using - to read from stdin or direct prompt)
        cmd.append(prompt)

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
            files_deleted = []
            metadata = {}

            # Parse JSON output from Codex
            if self.config.json_output and output.strip():
                try:
                    parsed = json.loads(output)
                    if isinstance(parsed, dict):
                        output = parsed.get("output", parsed.get("result", output))
                        files_modified = parsed.get("files_modified", [])
                        files_created = parsed.get("files_created", [])
                        files_deleted = parsed.get("files_deleted", [])
                        metadata = {
                            "model": parsed.get("model"),
                            "tokens_used": parsed.get("tokens_used"),
                            "session_id": parsed.get("session_id"),
                        }
                except json.JSONDecodeError:
                    pass  # Keep raw output

            return AgentResponse(
                success=result.returncode == 0,
                output=output,
                files_modified=files_modified,
                files_created=files_created,
                files_deleted=files_deleted,
                error=result.stderr if result.returncode != 0 else None,
                exit_code=result.returncode,
                execution_time=execution_time,
                metadata=metadata,
            )

        except subprocess.TimeoutExpired:
            return AgentResponse.error_response(
                f"Codex execution timed out after {self.config.timeout}s",
                exit_code=-1,
            )
        except FileNotFoundError:
            return AgentResponse.error_response(
                f"Codex CLI not found: {self.config.command}",
                exit_code=-2,
            )
        except Exception as e:
            return AgentResponse.error_response(str(e), exit_code=-3)

    def execute_with_stdin(
        self,
        prompt: str,
        work_dir: Optional[str] = None,
    ) -> AgentResponse:
        """
        Execute using stdin pipe (for longer prompts).

        Args:
            prompt: The instruction to pipe
            work_dir: Working directory

        Returns:
            AgentResponse with results
        """
        work_dir = work_dir or self.config.work_dir or os.getcwd()

        cmd = [self.config.command, "exec"]

        if self.config.full_auto:
            cmd.append("--full-auto")

        if self.config.json_output:
            cmd.append("--json")

        if self.config.sandbox:
            cmd.extend(["--sandbox", "workspace-write"])

        # Use - to read from stdin
        cmd.append("-")

        try:
            import time
            start_time = time.time()

            result = subprocess.run(
                cmd,
                cwd=work_dir,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self.config.timeout,
                env={**os.environ, **self.config.env_vars},
            )

            execution_time = time.time() - start_time

            return AgentResponse(
                success=result.returncode == 0,
                output=result.stdout,
                error=result.stderr if result.returncode != 0 else None,
                exit_code=result.returncode,
                execution_time=execution_time,
            )

        except subprocess.TimeoutExpired:
            return AgentResponse.error_response(
                f"Codex execution timed out after {self.config.timeout}s"
            )
        except Exception as e:
            return AgentResponse.error_response(str(e))

    def analyze(self, context: str, question: str) -> str:
        """
        Analyze context using Codex.

        Note: Codex is better at code-specific analysis.
        """
        prompt = f"""Analyze:

{context}

Question: {question}

Answer:"""

        response = self.execute(prompt)
        return response.output if response.success else f"Analysis failed: {response.error}"

    def verify(self, expected: str, actual: str) -> bool:
        """Verify output matches expected."""
        # For Codex, we do a simpler comparison or delegate to code execution
        prompt = f"""Compare expected vs actual:

Expected: {expected}
Actual: {actual}

Output only: MATCH or MISMATCH"""

        response = self.execute(prompt)
        if response.success:
            return "MATCH" in response.output.upper()
        return False

    def is_available(self) -> bool:
        """Check if Codex CLI is available."""
        return shutil.which(self.config.command) is not None

    def generate_code(
        self,
        specification: str,
        language: str = "python",
        file_path: Optional[str] = None,
    ) -> AgentResponse:
        """
        Generate code from specification.

        Args:
            specification: What the code should do
            language: Programming language
            file_path: Where to save the code

        Returns:
            AgentResponse with generated code
        """
        file_instruction = ""
        if file_path:
            file_instruction = f"\nSave the code to: {file_path}"

        prompt = f"""Generate {language} code:

{specification}
{file_instruction}

Write clean, well-documented code."""

        return self.execute(prompt)

    def run_tests(self, test_command: str, work_dir: Optional[str] = None) -> AgentResponse:
        """
        Run tests using Codex.

        Args:
            test_command: The test command to run
            work_dir: Working directory

        Returns:
            AgentResponse with test results
        """
        prompt = f"""Run the following test command and report results:

{test_command}

Execute the command and summarize:
- Tests passed
- Tests failed
- Any errors"""

        return self.execute(prompt, work_dir)

    def implement_feature(
        self,
        feature_description: str,
        existing_files: List[str] = None,
        constraints: List[str] = None,
    ) -> AgentResponse:
        """
        Implement a feature based on description.

        Args:
            feature_description: What to implement
            existing_files: Files to consider/modify
            constraints: Implementation constraints

        Returns:
            AgentResponse with implementation
        """
        files_text = ""
        if existing_files:
            files_text = "\nExisting files to consider:\n" + "\n".join(f"- {f}" for f in existing_files)

        constraints_text = ""
        if constraints:
            constraints_text = "\nConstraints:\n" + "\n".join(f"- {c}" for c in constraints)

        prompt = f"""Implement the following feature:

{feature_description}
{files_text}
{constraints_text}

Create or modify files as needed."""

        return self.execute(prompt)
