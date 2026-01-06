"""
AI Orchestrator V2

Main orchestrator that coordinates Master and Worker roles with support
for role swapping between Claude and Codex.
"""

import json
import os
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum

from .agents.base import IAgent, AgentType, AgentResponse
from .agents.factory import AgentFactory
from .roles.base import (
    IRoleStrategy,
    Decision,
    DecisionType,
    VerificationResult,
    Instruction,
)
from .roles.master import MasterRole
from .roles.worker import WorkerRole
from .goal.parser import GoalParser, Goal
from .goal.validator import GoalValidator, ValidationResult
from .goal.progress import ProgressTracker, ProgressState
from .protocol.messages import RequestMessage, ResponseMessage, MessageFactory
from .protocol.serializer import JSONSerializer
from .verification.checker import VerificationChecker, VerificationReport


class OrchestratorState(Enum):
    """Orchestrator states"""
    IDLE = "idle"
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    VERIFYING = "verifying"
    CORRECTING = "correcting"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class OrchestratorConfig:
    """Configuration for the orchestrator"""
    max_iterations: int = 20
    timeout_seconds: int = 300
    checkpoint_interval: int = 5
    strict_verification: bool = True
    max_correction_attempts: int = 3

    # Role configuration
    master_agent_type: AgentType = AgentType.CLAUDE
    worker_agent_type: AgentType = AgentType.CODEX

    # Paths
    work_dir: str = "."
    session_dir: str = "sessions"
    goal_file: str = "GOAL.txt"

    # Logging
    log_level: str = "INFO"
    log_file: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_iterations": self.max_iterations,
            "timeout_seconds": self.timeout_seconds,
            "checkpoint_interval": self.checkpoint_interval,
            "strict_verification": self.strict_verification,
            "max_correction_attempts": self.max_correction_attempts,
            "master_agent_type": self.master_agent_type.value,
            "worker_agent_type": self.worker_agent_type.value,
            "work_dir": self.work_dir,
            "session_dir": self.session_dir,
            "goal_file": self.goal_file,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OrchestratorConfig":
        data = data.copy()
        if "master_agent_type" in data:
            data["master_agent_type"] = AgentType(data["master_agent_type"])
        if "worker_agent_type" in data:
            data["worker_agent_type"] = AgentType(data["worker_agent_type"])
        return cls(**data)

    @classmethod
    def from_yaml(cls, path: str) -> "OrchestratorConfig":
        """Load config from YAML file"""
        import yaml
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data.get("orchestrator", data))


@dataclass
class SessionState:
    """Session state for persistence"""
    session_id: str
    started_at: datetime
    updated_at: datetime
    state: OrchestratorState
    iteration: int
    goal_title: str
    config: Dict[str, Any]
    history: List[Dict[str, Any]] = field(default_factory=list)
    current_decision: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "started_at": self.started_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "state": self.state.value,
            "iteration": self.iteration,
            "goal_title": self.goal_title,
            "config": self.config,
            "history": self.history,
            "current_decision": self.current_decision,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionState":
        data = data.copy()
        data["started_at"] = datetime.fromisoformat(data["started_at"])
        data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        data["state"] = OrchestratorState(data["state"])
        return cls(**data)


class Orchestrator:
    """
    Main orchestrator for AI agent coordination.

    Coordinates Master and Worker roles, supports role swapping,
    goal-oriented execution, and verification.
    """

    def __init__(
        self,
        config: Optional[OrchestratorConfig] = None,
        goal: Optional[Goal] = None,
    ):
        """
        Initialize orchestrator.

        Args:
            config: Orchestrator configuration
            goal: Goal to achieve (or load from file)
        """
        self.config = config or OrchestratorConfig()
        self.goal = goal
        self.state = OrchestratorState.IDLE

        # Setup logging
        self._setup_logging()

        # Initialize components
        self._master_agent: Optional[IAgent] = None
        self._worker_agent: Optional[IAgent] = None
        self._master_role: Optional[MasterRole] = None
        self._worker_role: Optional[WorkerRole] = None

        self._goal_parser = GoalParser()
        self._goal_validator: Optional[GoalValidator] = None
        self._progress_tracker: Optional[ProgressTracker] = None
        self._verifier: Optional[VerificationChecker] = None
        self._serializer = JSONSerializer()

        # Session state
        self._session: Optional[SessionState] = None
        self._iteration = 0
        self._history: List[Dict[str, Any]] = []

        self.logger.info(f"Orchestrator initialized with config: {self.config.to_dict()}")

    def _setup_logging(self) -> None:
        """Setup logging"""
        self.logger = logging.getLogger("orchestrator")
        self.logger.setLevel(getattr(logging, self.config.log_level.upper()))

        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(
                logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s")
            )
            self.logger.addHandler(handler)

        if self.config.log_file:
            file_handler = logging.FileHandler(self.config.log_file)
            file_handler.setFormatter(
                logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s")
            )
            self.logger.addHandler(file_handler)

    def initialize(self) -> bool:
        """
        Initialize all components.

        Returns:
            True if initialization successful
        """
        self.state = OrchestratorState.INITIALIZING
        self.logger.info("Initializing orchestrator components...")

        try:
            # Load goal if not provided
            if not self.goal:
                goal_path = os.path.join(self.config.work_dir, self.config.goal_file)
                if os.path.exists(goal_path):
                    self.goal = self._goal_parser.parse_file(goal_path)
                    self.logger.info(f"Loaded goal: {self.goal.title}")
                else:
                    self.logger.error(f"Goal file not found: {goal_path}")
                    return False

            # Create agents
            self._master_agent = AgentFactory.create(self.config.master_agent_type)
            self._worker_agent = AgentFactory.create(self.config.worker_agent_type)

            # Check availability
            if not self._master_agent.is_available():
                self.logger.warning(f"Master agent ({self.config.master_agent_type}) not available")

            if not self._worker_agent.is_available():
                self.logger.warning(f"Worker agent ({self.config.worker_agent_type}) not available")

            # Create roles
            self._master_role = MasterRole(self._master_agent)
            self._worker_role = WorkerRole(self._worker_agent)

            # Create validators and trackers
            self._goal_validator = GoalValidator(self._master_agent, strict=self.config.strict_verification)
            self._verifier = VerificationChecker(agent=self._master_agent)

            # Setup session
            session_dir = os.path.join(self.config.work_dir, self.config.session_dir)
            self._progress_tracker = ProgressTracker(
                self.goal,
                session_dir=session_dir,
                auto_save=True,
            )

            # Create session state
            import uuid
            self._session = SessionState(
                session_id=str(uuid.uuid4())[:8],
                started_at=datetime.now(),
                updated_at=datetime.now(),
                state=OrchestratorState.IDLE,
                iteration=0,
                goal_title=self.goal.title,
                config=self.config.to_dict(),
            )

            self.state = OrchestratorState.IDLE
            self.logger.info("Initialization complete")
            return True

        except Exception as e:
            self.logger.error(f"Initialization failed: {e}")
            self.state = OrchestratorState.FAILED
            return False

    def run(self) -> bool:
        """
        Run the orchestration loop.

        Returns:
            True if goal achieved
        """
        if not self._session:
            if not self.initialize():
                return False

        self.state = OrchestratorState.RUNNING
        self._progress_tracker.start()
        self.logger.info(f"Starting orchestration for: {self.goal.title}")

        try:
            while self._iteration < self.config.max_iterations:
                self._iteration += 1
                self.logger.info(f"--- Iteration {self._iteration} ---")

                # Get current state
                current_state = self._get_current_state()

                # Master decides next step
                decision = self._master_role.decide_next_step(
                    goal_description=self._format_goal_for_master(),
                    current_state=current_state,
                    history=self._history,
                )

                self.logger.info(f"Master decision: {decision.type.value} - {decision.reason[:100]}")

                # Handle decision
                if decision.type == DecisionType.DONE:
                    self.logger.info("Goal achieved!")
                    self.state = OrchestratorState.COMPLETED
                    self._progress_tracker.mark_completed()
                    return True

                if decision.type == DecisionType.SKIP:
                    self.logger.info(f"Skipping step: {decision.reason}")
                    self._record_iteration(decision, None, None)
                    continue

                if decision.type == DecisionType.ERROR:
                    self.logger.error(f"Error decision: {decision.reason}")
                    self._progress_tracker.mark_blocked(decision.reason)
                    continue

                # Worker implements
                instruction = Instruction(
                    prompt=decision.instruction,
                    expected_outcome=decision.expected_outcome,
                )

                response = self._worker_role.implement_step(instruction)
                self.logger.info(f"Worker response: success={response.success}")

                # Master verifies
                self.state = OrchestratorState.VERIFYING
                verification = self._master_role.verify_implementation(instruction, response)

                if verification.passed:
                    self.logger.info(f"Verification passed (score: {verification.score:.2f})")
                    self._record_iteration(decision, response, verification)
                else:
                    self.logger.warning(f"Verification failed: {verification.issues}")
                    self._handle_verification_failure(instruction, response, verification)

                # Checkpoint
                if self._iteration % self.config.checkpoint_interval == 0:
                    self._save_checkpoint()

                # Check if goal achieved
                if self.goal.is_achieved:
                    self.logger.info("All criteria completed!")
                    self.state = OrchestratorState.COMPLETED
                    self._progress_tracker.mark_completed()
                    return True

            self.logger.warning(f"Max iterations ({self.config.max_iterations}) reached")
            self.state = OrchestratorState.FAILED
            return False

        except KeyboardInterrupt:
            self.logger.info("Orchestration interrupted by user")
            self.state = OrchestratorState.PAUSED
            self._save_checkpoint()
            return False

        except Exception as e:
            self.logger.error(f"Orchestration failed: {e}")
            self.state = OrchestratorState.FAILED
            self._progress_tracker.mark_failed(str(e))
            return False

    def swap_roles(self) -> None:
        """
        Swap Master and Worker roles between agents.

        This allows Codex to become Master and Claude to become Worker.
        """
        self.logger.info("Swapping roles...")

        # Swap agent types in config
        self.config.master_agent_type, self.config.worker_agent_type = (
            self.config.worker_agent_type,
            self.config.master_agent_type,
        )

        # Swap agents
        self._master_agent, self._worker_agent = self._worker_agent, self._master_agent

        # Recreate roles with swapped agents
        self._master_role = MasterRole(self._master_agent)
        self._worker_role = WorkerRole(self._worker_agent)

        # Update validator
        self._goal_validator = GoalValidator(
            self._master_agent,
            strict=self.config.strict_verification,
        )

        self.logger.info(
            f"Roles swapped: Master={self.config.master_agent_type.value}, "
            f"Worker={self.config.worker_agent_type.value}"
        )

    def pause(self) -> None:
        """Pause orchestration"""
        self.state = OrchestratorState.PAUSED
        self._save_checkpoint()
        self.logger.info("Orchestration paused")

    def resume(self, checkpoint_path: Optional[str] = None) -> bool:
        """
        Resume from checkpoint.

        Args:
            checkpoint_path: Path to checkpoint file

        Returns:
            True if resume successful
        """
        if checkpoint_path:
            if not self._load_checkpoint(checkpoint_path):
                return False

        if not self._session:
            self.logger.error("No session to resume")
            return False

        self.logger.info(f"Resuming from iteration {self._iteration}")
        return self.run()

    def _handle_verification_failure(
        self,
        instruction: Instruction,
        response: AgentResponse,
        verification: VerificationResult,
    ) -> None:
        """Handle a failed verification"""
        self.state = OrchestratorState.CORRECTING

        for attempt in range(self.config.max_correction_attempts):
            self.logger.info(f"Correction attempt {attempt + 1}/{self.config.max_correction_attempts}")

            # Create correction instruction
            correction = self._master_role.create_correction(
                instruction,
                verification.issues,
            )

            # Worker implements correction
            response = self._worker_role.implement_step(correction)

            # Verify again
            verification = self._master_role.verify_implementation(correction, response)

            if verification.passed:
                self.logger.info("Correction successful")
                self._record_iteration(
                    Decision(type=DecisionType.CORRECT, instruction=correction.prompt),
                    response,
                    verification,
                )
                self.state = OrchestratorState.RUNNING
                return

        self.logger.warning("Max correction attempts reached")
        self._record_iteration(
            Decision(type=DecisionType.ERROR, reason="Correction failed"),
            response,
            verification,
        )
        self.state = OrchestratorState.RUNNING

    def _get_current_state(self) -> Dict[str, Any]:
        """Get current state for master decision"""
        return {
            "iteration": self._iteration,
            "goal_progress": self.goal.progress_percentage,
            "completed_criteria": self.goal.completed_criteria,
            "total_criteria": self.goal.total_criteria,
            "pending_criteria": [
                c.description for c in self.goal.get_pending_criteria()
            ],
            "last_success": (
                self._history[-1].get("success", True) if self._history else True
            ),
            "state": self.state.value,
        }

    def _format_goal_for_master(self) -> str:
        """Format goal description for master"""
        lines = [
            f"# {self.goal.title}",
            "",
            self.goal.description,
            "",
            "## Acceptance Criteria",
        ]

        for c in self.goal.acceptance_criteria:
            status = "[x]" if c.completed else "[ ]"
            lines.append(f"- {status} {c.description}")

        if self.goal.constraints:
            lines.extend(["", "## Constraints"])
            for c in self.goal.constraints:
                lines.append(f"- {c}")

        return "\n".join(lines)

    def _record_iteration(
        self,
        decision: Decision,
        response: Optional[AgentResponse],
        verification: Optional[VerificationResult],
    ) -> None:
        """Record an iteration in history"""
        record = {
            "iteration": self._iteration,
            "timestamp": datetime.now().isoformat(),
            "decision_type": decision.type.value,
            "instruction": decision.instruction[:500] if decision.instruction else "",
            "reason": decision.reason,
            "success": response.success if response else True,
            "output": response.output[:1000] if response else "",
            "verification_passed": verification.passed if verification else True,
            "verification_score": verification.score if verification else 1.0,
        }

        self._history.append(record)

        # Update progress tracker
        if response:
            self._progress_tracker.record_iteration(
                action=decision.instruction[:200] if decision.instruction else decision.type.value,
                result=response.output[:200] if response.output else "No output",
                success=response.success and (verification.passed if verification else True),
                files_changed=response.files_modified + response.files_created,
            )

    def _save_checkpoint(self) -> str:
        """Save checkpoint"""
        if not self._session:
            return ""

        self._session.updated_at = datetime.now()
        self._session.state = self.state
        self._session.iteration = self._iteration
        self._session.history = self._history

        session_dir = Path(self.config.work_dir) / self.config.session_dir
        session_dir.mkdir(parents=True, exist_ok=True)

        checkpoint_path = session_dir / f"checkpoint_{self._session.session_id}.json"
        checkpoint_path.write_text(
            json.dumps(self._session.to_dict(), indent=2),
            encoding="utf-8",
        )

        self.logger.info(f"Checkpoint saved: {checkpoint_path}")
        return str(checkpoint_path)

    def _load_checkpoint(self, path: str) -> bool:
        """Load checkpoint"""
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            self._session = SessionState.from_dict(data)
            self._iteration = self._session.iteration
            self._history = self._session.history
            self.config = OrchestratorConfig.from_dict(self._session.config)

            # Reinitialize components
            return self.initialize()

        except Exception as e:
            self.logger.error(f"Failed to load checkpoint: {e}")
            return False

    def get_status(self) -> Dict[str, Any]:
        """Get current status"""
        return {
            "state": self.state.value,
            "iteration": self._iteration,
            "max_iterations": self.config.max_iterations,
            "goal": {
                "title": self.goal.title if self.goal else None,
                "progress": self.goal.progress_percentage if self.goal else 0,
                "completed": self.goal.completed_criteria if self.goal else 0,
                "total": self.goal.total_criteria if self.goal else 0,
            },
            "roles": {
                "master": self.config.master_agent_type.value,
                "worker": self.config.worker_agent_type.value,
            },
            "session_id": self._session.session_id if self._session else None,
        }

    def get_progress_summary(self) -> str:
        """Get progress summary"""
        if self._progress_tracker:
            return self._progress_tracker.get_summary()
        return "No progress data available"


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="AI Orchestrator V2")
    parser.add_argument("--goal", "-g", help="Path to goal file")
    parser.add_argument("--work-dir", "-w", default=".", help="Working directory")
    parser.add_argument("--max-iterations", "-m", type=int, default=20)
    parser.add_argument("--master", choices=["claude", "codex"], default="claude")
    parser.add_argument("--worker", choices=["claude", "codex"], default="codex")
    parser.add_argument("--resume", "-r", help="Resume from checkpoint")
    parser.add_argument("--swap", action="store_true", help="Swap roles mid-run")

    args = parser.parse_args()

    config = OrchestratorConfig(
        work_dir=args.work_dir,
        max_iterations=args.max_iterations,
        master_agent_type=AgentType(args.master),
        worker_agent_type=AgentType(args.worker),
        goal_file=args.goal or "GOAL.txt",
    )

    orchestrator = Orchestrator(config)

    if args.resume:
        success = orchestrator.resume(args.resume)
    else:
        success = orchestrator.run()

    print(f"\nFinal Status:\n{json.dumps(orchestrator.get_status(), indent=2)}")
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
