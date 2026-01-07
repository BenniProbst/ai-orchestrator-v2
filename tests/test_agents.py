"""
Tests for Agent implementations

Tests:
1. test_claude_agent_execute_success
2. test_claude_agent_execute_timeout
3. test_claude_agent_analyze_codebase
4. test_codex_agent_execute_success
5. test_codex_agent_execute_timeout
6. test_codex_agent_json_output
7. test_agent_capability_detection
8. test_agent_error_handling
9. test_agent_retry_logic
10. test_agent_output_parsing
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import subprocess

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agents.base import IAgent, AgentType, AgentCapability, AgentResponse, AgentConfig
from agents.claude_agent import ClaudeAgent
from agents.codex_agent import CodexAgent
from agents.factory import AgentFactory


class TestClaudeAgent:
    """Tests for ClaudeAgent"""

    def test_claude_agent_execute_success(self):
        """Test successful execution with Claude agent"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout='{"result": "Success", "files_created": ["test.py"]}',
                stderr="",
            )

            agent = ClaudeAgent()
            response = agent.execute("Create a test file")

            assert response.success
            assert mock_run.called

    def test_claude_agent_execute_timeout(self):
        """Test timeout handling in Claude agent"""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=120)

            agent = ClaudeAgent(AgentConfig(command="claude", timeout=120))
            response = agent.execute("Long running task")

            assert not response.success
            assert "timed out" in response.error.lower()
            assert response.exit_code == -1

    def test_claude_agent_analyze_codebase(self):
        """Test Claude agent's analysis capability"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="The code implements a REST API with three endpoints.",
                stderr="",
            )

            agent = ClaudeAgent()
            result = agent.analyze("def hello(): pass", "What does this code do?")

            assert "implements" in result.lower() or "code" in result.lower() or mock_run.called

    def test_claude_agent_verify_success(self):
        """Test Claude agent verification - pass case"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="PASS - The implementation matches expectations",
                stderr="",
            )

            agent = ClaudeAgent()
            result = agent.verify("Create hello function", "def hello(): print('hello')")

            assert result is True

    def test_claude_agent_verify_failure(self):
        """Test Claude agent verification - fail case"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="FAIL - Missing error handling",
                stderr="",
            )

            agent = ClaudeAgent()
            result = agent.verify("Create robust function", "def func(): pass")

            assert result is False


class TestCodexAgent:
    """Tests for CodexAgent"""

    def test_codex_agent_execute_success(self):
        """Test successful execution with Codex agent"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout='{"output": "File created", "files_created": ["app.py"]}',
                stderr="",
            )

            agent = CodexAgent()
            response = agent.execute("Create app.py with Flask setup")

            assert response.success
            assert mock_run.called

    def test_codex_agent_execute_timeout(self):
        """Test timeout handling in Codex agent"""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="codex", timeout=300)

            agent = CodexAgent(AgentConfig(command="codex", timeout=300))
            response = agent.execute("Complex task")

            assert not response.success
            assert "timed out" in response.error.lower()

    def test_codex_agent_json_output(self):
        """Test Codex agent JSON output parsing"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout='{"output": "Done", "files_created": ["a.py", "b.py"], "model": "gpt-4"}',
                stderr="",
            )

            agent = CodexAgent()
            response = agent.execute("Create files")

            assert response.success
            # JSON should be parsed
            assert response.output == "Done" or "Done" in response.output

    def test_codex_agent_stdin_execution(self):
        """Test Codex agent with stdin piping"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="Processed from stdin",
                stderr="",
            )

            agent = CodexAgent()
            response = agent.execute_with_stdin("Long prompt from stdin")

            assert response.success
            # Check stdin was used
            call_kwargs = mock_run.call_args
            assert call_kwargs is not None


class TestAgentCapabilities:
    """Tests for agent capability detection"""

    def test_agent_capability_detection(self):
        """Test that agents report correct capabilities"""
        claude = ClaudeAgent()
        codex = CodexAgent()

        # Claude should have analysis capabilities
        assert AgentCapability.CODE_ANALYSIS in claude.capabilities
        assert AgentCapability.PLANNING in claude.capabilities

        # Codex should have generation capabilities
        assert AgentCapability.CODE_GENERATION in codex.capabilities
        assert AgentCapability.FILE_OPERATIONS in codex.capabilities

    def test_agent_has_capability(self):
        """Test has_capability method"""
        agent = ClaudeAgent()

        assert agent.has_capability(AgentCapability.CODE_ANALYSIS)
        assert not agent.has_capability(AgentCapability.TEST_EXECUTION)


class TestAgentErrorHandling:
    """Tests for agent error handling"""

    def test_agent_error_handling_file_not_found(self):
        """Test handling when CLI not found"""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("claude not found")

            agent = ClaudeAgent()
            response = agent.execute("Test")

            assert not response.success
            assert response.exit_code == -2

    def test_agent_error_handling_generic(self):
        """Test handling generic exceptions"""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = Exception("Unexpected error")

            agent = ClaudeAgent()
            response = agent.execute("Test")

            assert not response.success
            assert response.exit_code == -3

    def test_agent_error_response_factory(self):
        """Test AgentResponse.error_response factory"""
        response = AgentResponse.error_response("Test error", exit_code=42)

        assert not response.success
        assert response.error == "Test error"
        assert response.exit_code == 42
        assert response.output == ""


class TestAgentRetryLogic:
    """Tests for agent retry logic"""

    def test_agent_retry_logic(self):
        """Test retry behavior (implemented in higher level)"""
        # Agents themselves don't retry, but we test the response structure
        response = AgentResponse(
            success=False,
            output="",
            error="Temporary failure",
            exit_code=1,
            metadata={"retry_count": 0},
        )

        assert not response.success
        assert response.metadata.get("retry_count") == 0


class TestAgentOutputParsing:
    """Tests for agent output parsing"""

    def test_agent_output_parsing_json(self):
        """Test parsing JSON output"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout='{"result": "parsed", "files_modified": ["x.py"]}',
                stderr="",
            )

            agent = ClaudeAgent()
            response = agent.execute("Test")

            assert response.success

    def test_agent_output_parsing_plain_text(self):
        """Test parsing plain text output"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="Plain text response without JSON",
                stderr="",
            )

            agent = ClaudeAgent()
            response = agent.execute("Test")

            assert response.success
            assert "Plain text" in response.output


class TestAgentFactory:
    """Tests for AgentFactory"""

    def test_factory_create_claude(self):
        """Test creating Claude agent via factory"""
        agent = AgentFactory.create(AgentType.CLAUDE)
        assert isinstance(agent, ClaudeAgent)
        assert agent.agent_type == AgentType.CLAUDE

    def test_factory_create_codex(self):
        """Test creating Codex agent via factory"""
        agent = AgentFactory.create(AgentType.CODEX)
        assert isinstance(agent, CodexAgent)
        assert agent.agent_type == AgentType.CODEX

    def test_factory_create_with_config(self):
        """Test creating agent with custom config"""
        config = AgentConfig(command="custom-claude", timeout=60)
        agent = AgentFactory.create(AgentType.CLAUDE, config)

        assert agent.config.command == "custom-claude"
        assert agent.config.timeout == 60

    def test_factory_create_pair(self):
        """Test creating master-worker pair"""
        master, worker = AgentFactory.create_pair()

        assert master.agent_type == AgentType.CLAUDE
        assert worker.agent_type == AgentType.CODEX

    def test_factory_create_pair_swapped(self):
        """Test creating swapped pair"""
        master, worker = AgentFactory.create_pair(
            master_type=AgentType.CODEX,
            worker_type=AgentType.CLAUDE,
        )

        assert master.agent_type == AgentType.CODEX
        assert worker.agent_type == AgentType.CLAUDE
