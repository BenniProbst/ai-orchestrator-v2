"""
Progress Tracker

Tracks and persists progress toward goal completion.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from enum import Enum

from .parser import Goal, AcceptanceCriterion, CriterionStatus


class ProgressState(Enum):
    """Overall progress state"""
    NOT_STARTED = "not_started"
    STARTING = "starting"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETING = "completing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class IterationRecord:
    """Record of a single iteration"""
    iteration: int
    timestamp: datetime
    action: str
    result: str
    success: bool
    files_changed: List[str] = field(default_factory=list)
    criteria_addressed: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "iteration": self.iteration,
            "timestamp": self.timestamp.isoformat(),
            "action": self.action,
            "result": self.result,
            "success": self.success,
            "files_changed": self.files_changed,
            "criteria_addressed": self.criteria_addressed,
            "duration_seconds": self.duration_seconds,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IterationRecord":
        data = data.copy()
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


@dataclass
class ProgressSnapshot:
    """Complete progress snapshot"""
    goal_title: str
    state: ProgressState
    started_at: datetime
    updated_at: datetime
    total_criteria: int
    completed_criteria: int
    current_iteration: int
    iterations: List[IterationRecord] = field(default_factory=list)
    blocked_reason: Optional[str] = None
    criteria_status: Dict[str, str] = field(default_factory=dict)

    @property
    def progress_percentage(self) -> float:
        if self.total_criteria == 0:
            return 0.0
        return (self.completed_criteria / self.total_criteria) * 100

    @property
    def duration(self) -> float:
        """Total duration in seconds"""
        return (self.updated_at - self.started_at).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal_title": self.goal_title,
            "state": self.state.value,
            "started_at": self.started_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "total_criteria": self.total_criteria,
            "completed_criteria": self.completed_criteria,
            "progress_percentage": self.progress_percentage,
            "current_iteration": self.current_iteration,
            "iterations": [i.to_dict() for i in self.iterations],
            "blocked_reason": self.blocked_reason,
            "criteria_status": self.criteria_status,
            "duration_seconds": self.duration,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProgressSnapshot":
        data = data.copy()
        data["state"] = ProgressState(data["state"])
        data["started_at"] = datetime.fromisoformat(data["started_at"])
        data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        data["iterations"] = [IterationRecord.from_dict(i) for i in data.get("iterations", [])]
        # Remove computed properties
        data.pop("progress_percentage", None)
        data.pop("duration_seconds", None)
        return cls(**data)


class ProgressTracker:
    """
    Tracks progress toward goal completion.

    Maintains history of iterations and supports persistence.
    """

    def __init__(
        self,
        goal: Goal,
        session_dir: Optional[str] = None,
        auto_save: bool = True,
    ):
        """
        Initialize tracker.

        Args:
            goal: Goal being tracked
            session_dir: Directory for saving progress
            auto_save: Auto-save after each update
        """
        self.goal = goal
        self.session_dir = Path(session_dir) if session_dir else None
        self.auto_save = auto_save

        self._snapshot = ProgressSnapshot(
            goal_title=goal.title,
            state=ProgressState.NOT_STARTED,
            started_at=datetime.now(),
            updated_at=datetime.now(),
            total_criteria=goal.total_criteria,
            completed_criteria=goal.completed_criteria,
            current_iteration=0,
            criteria_status={
                c.description: c.status.value
                for c in goal.acceptance_criteria
            },
        )

    @property
    def snapshot(self) -> ProgressSnapshot:
        """Get current progress snapshot."""
        return self._snapshot

    @property
    def current_iteration(self) -> int:
        return self._snapshot.current_iteration

    @property
    def state(self) -> ProgressState:
        return self._snapshot.state

    def start(self) -> None:
        """Mark progress as started."""
        self._snapshot.state = ProgressState.STARTING
        self._snapshot.started_at = datetime.now()
        self._update()

    def record_iteration(
        self,
        action: str,
        result: str,
        success: bool,
        files_changed: List[str] = None,
        criteria_addressed: List[str] = None,
        duration: float = 0.0,
        metadata: Dict[str, Any] = None,
    ) -> IterationRecord:
        """
        Record an iteration.

        Args:
            action: What was attempted
            result: What happened
            success: Whether it succeeded
            files_changed: Files that were modified
            criteria_addressed: Criteria this iteration addressed
            duration: How long it took
            metadata: Additional data

        Returns:
            The created IterationRecord
        """
        self._snapshot.current_iteration += 1

        record = IterationRecord(
            iteration=self._snapshot.current_iteration,
            timestamp=datetime.now(),
            action=action,
            result=result,
            success=success,
            files_changed=files_changed or [],
            criteria_addressed=criteria_addressed or [],
            duration_seconds=duration,
            metadata=metadata or {},
        )

        self._snapshot.iterations.append(record)

        # Update state
        if self._snapshot.state == ProgressState.STARTING:
            self._snapshot.state = ProgressState.IN_PROGRESS

        self._update()
        return record

    def update_criterion(
        self,
        description: str,
        status: CriterionStatus,
    ) -> None:
        """
        Update status of a criterion.

        Args:
            description: Criterion description
            status: New status
        """
        self._snapshot.criteria_status[description] = status.value

        # Update completed count
        completed = sum(
            1 for s in self._snapshot.criteria_status.values()
            if s == CriterionStatus.COMPLETED.value
        )
        self._snapshot.completed_criteria = completed

        # Check for completion
        if completed == self._snapshot.total_criteria:
            self._snapshot.state = ProgressState.COMPLETING

        self._update()

    def mark_blocked(self, reason: str) -> None:
        """Mark progress as blocked."""
        self._snapshot.state = ProgressState.BLOCKED
        self._snapshot.blocked_reason = reason
        self._update()

    def unblock(self) -> None:
        """Remove blocked state."""
        self._snapshot.state = ProgressState.IN_PROGRESS
        self._snapshot.blocked_reason = None
        self._update()

    def mark_completed(self) -> None:
        """Mark goal as completed."""
        self._snapshot.state = ProgressState.COMPLETED
        self._update()

    def mark_failed(self, reason: str = "") -> None:
        """Mark goal as failed."""
        self._snapshot.state = ProgressState.FAILED
        self._snapshot.blocked_reason = reason
        self._update()

    def _update(self) -> None:
        """Update timestamp and optionally save."""
        self._snapshot.updated_at = datetime.now()
        if self.auto_save and self.session_dir:
            self.save()

    def save(self, path: Optional[str] = None) -> str:
        """
        Save progress to file.

        Args:
            path: Optional override path

        Returns:
            Path where saved
        """
        if path:
            save_path = Path(path)
        elif self.session_dir:
            self.session_dir.mkdir(parents=True, exist_ok=True)
            save_path = self.session_dir / "progress.json"
        else:
            raise ValueError("No save path available")

        save_path.write_text(
            json.dumps(self._snapshot.to_dict(), indent=2),
            encoding="utf-8",
        )

        return str(save_path)

    def load(self, path: str) -> None:
        """
        Load progress from file.

        Args:
            path: Path to progress file
        """
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self._snapshot = ProgressSnapshot.from_dict(data)

    def get_history(self, last_n: Optional[int] = None) -> List[IterationRecord]:
        """
        Get iteration history.

        Args:
            last_n: Only return last N iterations

        Returns:
            List of IterationRecords
        """
        iterations = self._snapshot.iterations
        if last_n:
            return iterations[-last_n:]
        return iterations

    def get_summary(self) -> str:
        """Get a text summary of progress."""
        s = self._snapshot
        lines = [
            f"Goal: {s.goal_title}",
            f"State: {s.state.value}",
            f"Progress: {s.completed_criteria}/{s.total_criteria} ({s.progress_percentage:.1f}%)",
            f"Iterations: {s.current_iteration}",
            f"Duration: {s.duration / 60:.1f} minutes",
        ]

        if s.blocked_reason:
            lines.append(f"Blocked: {s.blocked_reason}")

        return "\n".join(lines)

    def sync_with_goal(self, goal: Goal) -> None:
        """
        Sync tracker with goal's current state.

        Args:
            goal: Goal to sync with
        """
        self.goal = goal
        self._snapshot.total_criteria = goal.total_criteria
        self._snapshot.completed_criteria = goal.completed_criteria
        self._snapshot.criteria_status = {
            c.description: c.status.value
            for c in goal.acceptance_criteria
        }
        self._update()
