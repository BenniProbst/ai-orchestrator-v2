"""
Protocol Messages

Message types for communication between Master and Worker.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, List, Optional


class MessageType(Enum):
    """Types of protocol messages"""
    REQUEST = "request"
    RESPONSE = "response"
    ERROR = "error"
    STATUS = "status"
    HEARTBEAT = "heartbeat"
    DECISION = "decision"
    VERIFICATION = "verification"


class MessagePriority(Enum):
    """Message priority levels"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class Message:
    """Base message class"""
    type: MessageType
    id: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    sender: str = ""
    recipient: str = ""
    correlation_id: Optional[str] = None
    priority: MessagePriority = MessagePriority.NORMAL
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            import uuid
            self.id = str(uuid.uuid4())[:8]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "sender": self.sender,
            "recipient": self.recipient,
            "correlation_id": self.correlation_id,
            "priority": self.priority.value,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        data = data.copy()
        data["type"] = MessageType(data["type"])
        data["priority"] = MessagePriority(data.get("priority", 2))
        if "timestamp" in data and isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


@dataclass
class RequestMessage(Message):
    """Request from Master to Worker"""
    instruction: str = ""
    context: str = ""
    expected_outcome: str = ""
    constraints: List[str] = field(default_factory=list)
    files_to_modify: List[str] = field(default_factory=list)
    files_to_create: List[str] = field(default_factory=list)
    timeout_seconds: int = 300
    retry_count: int = 0

    def __post_init__(self):
        self.type = MessageType.REQUEST
        super().__post_init__()

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "instruction": self.instruction,
            "context": self.context,
            "expected_outcome": self.expected_outcome,
            "constraints": self.constraints,
            "files_to_modify": self.files_to_modify,
            "files_to_create": self.files_to_create,
            "timeout_seconds": self.timeout_seconds,
            "retry_count": self.retry_count,
        })
        return base

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RequestMessage":
        data = data.copy()
        data["type"] = MessageType.REQUEST
        data["priority"] = MessagePriority(data.get("priority", 2))
        if "timestamp" in data and isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


@dataclass
class ResponseMessage(Message):
    """Response from Worker to Master"""
    success: bool = False
    output: str = ""
    files_modified: List[str] = field(default_factory=list)
    files_created: List[str] = field(default_factory=list)
    files_deleted: List[str] = field(default_factory=list)
    error: Optional[str] = None
    exit_code: int = 0
    execution_time: float = 0.0

    def __post_init__(self):
        self.type = MessageType.RESPONSE
        super().__post_init__()

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "success": self.success,
            "output": self.output,
            "files_modified": self.files_modified,
            "files_created": self.files_created,
            "files_deleted": self.files_deleted,
            "error": self.error,
            "exit_code": self.exit_code,
            "execution_time": self.execution_time,
        })
        return base

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResponseMessage":
        data = data.copy()
        data["type"] = MessageType.RESPONSE
        data["priority"] = MessagePriority(data.get("priority", 2))
        if "timestamp" in data and isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


@dataclass
class ErrorMessage(Message):
    """Error message"""
    error_code: str = ""
    error_message: str = ""
    stack_trace: Optional[str] = None
    recoverable: bool = True

    def __post_init__(self):
        self.type = MessageType.ERROR
        self.priority = MessagePriority.HIGH
        super().__post_init__()

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "error_code": self.error_code,
            "error_message": self.error_message,
            "stack_trace": self.stack_trace,
            "recoverable": self.recoverable,
        })
        return base

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ErrorMessage":
        data = data.copy()
        data["type"] = MessageType.ERROR
        data["priority"] = MessagePriority(data.get("priority", 3))
        if "timestamp" in data and isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


@dataclass
class StatusMessage(Message):
    """Status update message"""
    status: str = ""
    progress: float = 0.0  # 0.0 to 1.0
    current_task: str = ""
    tasks_completed: int = 0
    tasks_total: int = 0
    estimated_remaining: Optional[float] = None  # seconds

    def __post_init__(self):
        self.type = MessageType.STATUS
        super().__post_init__()

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "status": self.status,
            "progress": self.progress,
            "current_task": self.current_task,
            "tasks_completed": self.tasks_completed,
            "tasks_total": self.tasks_total,
            "estimated_remaining": self.estimated_remaining,
        })
        return base


@dataclass
class DecisionMessage(Message):
    """Decision message from Master"""
    decision_type: str = ""  # IMPLEMENT, SKIP, DONE, RETRY, CORRECT
    instruction: str = ""
    reason: str = ""
    expected_outcome: str = ""

    def __post_init__(self):
        self.type = MessageType.DECISION
        super().__post_init__()

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "decision_type": self.decision_type,
            "instruction": self.instruction,
            "reason": self.reason,
            "expected_outcome": self.expected_outcome,
        })
        return base


@dataclass
class VerificationMessage(Message):
    """Verification result message"""
    passed: bool = False
    score: float = 0.0
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)

    def __post_init__(self):
        self.type = MessageType.VERIFICATION
        super().__post_init__()

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "passed": self.passed,
            "score": self.score,
            "issues": self.issues,
            "suggestions": self.suggestions,
        })
        return base


class MessageFactory:
    """Factory for creating messages"""

    @staticmethod
    def create_request(
        instruction: str,
        sender: str = "master",
        recipient: str = "worker",
        **kwargs,
    ) -> RequestMessage:
        return RequestMessage(
            instruction=instruction,
            sender=sender,
            recipient=recipient,
            **kwargs,
        )

    @staticmethod
    def create_response(
        success: bool,
        output: str,
        sender: str = "worker",
        recipient: str = "master",
        correlation_id: str = None,
        **kwargs,
    ) -> ResponseMessage:
        return ResponseMessage(
            success=success,
            output=output,
            sender=sender,
            recipient=recipient,
            correlation_id=correlation_id,
            **kwargs,
        )

    @staticmethod
    def create_error(
        error_code: str,
        error_message: str,
        sender: str = "",
        **kwargs,
    ) -> ErrorMessage:
        return ErrorMessage(
            error_code=error_code,
            error_message=error_message,
            sender=sender,
            **kwargs,
        )
