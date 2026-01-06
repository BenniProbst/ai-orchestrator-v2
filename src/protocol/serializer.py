"""
Protocol Serializers

Serialize and deserialize messages in various formats.
"""

import json
import re
from abc import ABC, abstractmethod
from typing import Dict, Any, Type, Optional, Union
from datetime import datetime

from .messages import (
    Message,
    MessageType,
    RequestMessage,
    ResponseMessage,
    ErrorMessage,
    StatusMessage,
    DecisionMessage,
    VerificationMessage,
)


class Serializer(ABC):
    """Abstract base serializer"""

    @abstractmethod
    def serialize(self, message: Message) -> str:
        """Serialize message to string"""
        pass

    @abstractmethod
    def deserialize(self, data: str) -> Message:
        """Deserialize string to message"""
        pass


class JSONSerializer(Serializer):
    """JSON format serializer"""

    # Message type to class mapping
    MESSAGE_CLASSES: Dict[MessageType, Type[Message]] = {
        MessageType.REQUEST: RequestMessage,
        MessageType.RESPONSE: ResponseMessage,
        MessageType.ERROR: ErrorMessage,
        MessageType.STATUS: StatusMessage,
        MessageType.DECISION: DecisionMessage,
        MessageType.VERIFICATION: VerificationMessage,
    }

    def __init__(self, indent: int = 2, sort_keys: bool = False):
        self.indent = indent
        self.sort_keys = sort_keys

    def serialize(self, message: Message) -> str:
        """
        Serialize message to JSON.

        Args:
            message: Message to serialize

        Returns:
            JSON string
        """
        return json.dumps(
            message.to_dict(),
            indent=self.indent,
            sort_keys=self.sort_keys,
            default=self._json_serializer,
        )

    def deserialize(self, data: str) -> Message:
        """
        Deserialize JSON to message.

        Args:
            data: JSON string

        Returns:
            Message object

        Raises:
            ValueError: If JSON is invalid or message type unknown
        """
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")

        if "type" not in parsed:
            raise ValueError("Message type not specified")

        msg_type = MessageType(parsed["type"])
        msg_class = self.MESSAGE_CLASSES.get(msg_type, Message)

        return msg_class.from_dict(parsed)

    def _json_serializer(self, obj: Any) -> Any:
        """Custom JSON serializer for special types"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, "value"):  # Enum
            return obj.value
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


class MarkdownSerializer(Serializer):
    """
    Markdown format serializer.

    Useful for human-readable message exchange.
    """

    # Section markers
    MARKERS = {
        "type": "---TYPE---",
        "instruction": "---INSTRUCTION---",
        "context": "---CONTEXT---",
        "expected": "---EXPECTED---",
        "constraints": "---CONSTRAINTS---",
        "output": "---OUTPUT---",
        "error": "---ERROR---",
        "status": "---STATUS---",
        "decision": "---DECISION---",
        "analysis": "---ANALYSIS---",
        "metadata": "---METADATA---",
    }

    def serialize(self, message: Message) -> str:
        """
        Serialize message to Markdown.

        Args:
            message: Message to serialize

        Returns:
            Markdown string
        """
        lines = [
            f"{self.MARKERS['type']}",
            message.type.value.upper(),
            "",
        ]

        if isinstance(message, RequestMessage):
            lines.extend(self._serialize_request(message))
        elif isinstance(message, ResponseMessage):
            lines.extend(self._serialize_response(message))
        elif isinstance(message, ErrorMessage):
            lines.extend(self._serialize_error(message))
        elif isinstance(message, DecisionMessage):
            lines.extend(self._serialize_decision(message))
        elif isinstance(message, VerificationMessage):
            lines.extend(self._serialize_verification(message))
        else:
            lines.extend(self._serialize_generic(message))

        # Add metadata
        lines.extend([
            f"{self.MARKERS['metadata']}",
            f"ID: {message.id}",
            f"Timestamp: {message.timestamp.isoformat()}",
            f"Sender: {message.sender}",
            f"Recipient: {message.recipient}",
        ])

        return "\n".join(lines)

    def deserialize(self, data: str) -> Message:
        """
        Deserialize Markdown to message.

        Args:
            data: Markdown string

        Returns:
            Message object
        """
        sections = self._parse_sections(data)

        # Determine message type
        msg_type_str = sections.get("type", "").strip().upper()
        try:
            msg_type = MessageType(msg_type_str.lower())
        except ValueError:
            msg_type = MessageType.REQUEST  # Default

        # Parse based on type
        if msg_type == MessageType.REQUEST:
            return self._deserialize_request(sections)
        elif msg_type == MessageType.RESPONSE:
            return self._deserialize_response(sections)
        elif msg_type == MessageType.ERROR:
            return self._deserialize_error(sections)
        elif msg_type == MessageType.DECISION:
            return self._deserialize_decision(sections)
        else:
            return self._deserialize_generic(sections, msg_type)

    def _serialize_request(self, msg: RequestMessage) -> list:
        lines = [
            f"{self.MARKERS['instruction']}",
            msg.instruction,
            "",
        ]

        if msg.context:
            lines.extend([
                f"{self.MARKERS['context']}",
                msg.context,
                "",
            ])

        if msg.expected_outcome:
            lines.extend([
                f"{self.MARKERS['expected']}",
                msg.expected_outcome,
                "",
            ])

        if msg.constraints:
            lines.extend([
                f"{self.MARKERS['constraints']}",
                *[f"- {c}" for c in msg.constraints],
                "",
            ])

        return lines

    def _serialize_response(self, msg: ResponseMessage) -> list:
        lines = [
            f"{self.MARKERS['status']}",
            "SUCCESS" if msg.success else "FAILED",
            "",
            f"{self.MARKERS['output']}",
            msg.output,
            "",
        ]

        if msg.error:
            lines.extend([
                f"{self.MARKERS['error']}",
                msg.error,
                "",
            ])

        return lines

    def _serialize_error(self, msg: ErrorMessage) -> list:
        return [
            f"{self.MARKERS['error']}",
            f"Code: {msg.error_code}",
            f"Message: {msg.error_message}",
            f"Recoverable: {msg.recoverable}",
            "",
        ]

    def _serialize_decision(self, msg: DecisionMessage) -> list:
        return [
            f"{self.MARKERS['decision']}",
            msg.decision_type,
            "",
            f"{self.MARKERS['instruction']}",
            msg.instruction,
            "",
            f"{self.MARKERS['analysis']}",
            msg.reason,
            "",
        ]

    def _serialize_verification(self, msg: VerificationMessage) -> list:
        lines = [
            f"{self.MARKERS['status']}",
            "PASSED" if msg.passed else "FAILED",
            f"Score: {msg.score:.2f}",
            "",
        ]

        if msg.issues:
            lines.append("Issues:")
            lines.extend([f"- {i}" for i in msg.issues])
            lines.append("")

        if msg.suggestions:
            lines.append("Suggestions:")
            lines.extend([f"- {s}" for s in msg.suggestions])
            lines.append("")

        return lines

    def _serialize_generic(self, msg: Message) -> list:
        return [f"Data: {json.dumps(msg.to_dict())}"]

    def _parse_sections(self, data: str) -> Dict[str, str]:
        """Parse markdown into sections"""
        sections = {}
        current_section = "preamble"
        current_content = []

        for line in data.split("\n"):
            # Check for section marker
            found_marker = False
            for name, marker in self.MARKERS.items():
                if line.strip() == marker:
                    # Save previous section
                    if current_content:
                        sections[current_section] = "\n".join(current_content).strip()
                    current_section = name
                    current_content = []
                    found_marker = True
                    break

            if not found_marker:
                current_content.append(line)

        # Save last section
        if current_content:
            sections[current_section] = "\n".join(current_content).strip()

        return sections

    def _deserialize_request(self, sections: Dict[str, str]) -> RequestMessage:
        constraints = []
        if "constraints" in sections:
            for line in sections["constraints"].split("\n"):
                if line.strip().startswith("- "):
                    constraints.append(line.strip()[2:])

        return RequestMessage(
            instruction=sections.get("instruction", ""),
            context=sections.get("context", ""),
            expected_outcome=sections.get("expected", ""),
            constraints=constraints,
        )

    def _deserialize_response(self, sections: Dict[str, str]) -> ResponseMessage:
        status = sections.get("status", "").strip().upper()
        return ResponseMessage(
            success=status == "SUCCESS",
            output=sections.get("output", ""),
            error=sections.get("error"),
        )

    def _deserialize_error(self, sections: Dict[str, str]) -> ErrorMessage:
        error_content = sections.get("error", "")
        code = ""
        message = error_content

        for line in error_content.split("\n"):
            if line.startswith("Code:"):
                code = line[5:].strip()
            elif line.startswith("Message:"):
                message = line[8:].strip()

        return ErrorMessage(
            error_code=code,
            error_message=message,
        )

    def _deserialize_decision(self, sections: Dict[str, str]) -> DecisionMessage:
        return DecisionMessage(
            decision_type=sections.get("decision", "").strip().upper(),
            instruction=sections.get("instruction", ""),
            reason=sections.get("analysis", ""),
        )

    def _deserialize_generic(
        self,
        sections: Dict[str, str],
        msg_type: MessageType,
    ) -> Message:
        return Message(type=msg_type)


class SerializerFactory:
    """Factory for creating serializers"""

    @staticmethod
    def create(format: str = "json") -> Serializer:
        """
        Create a serializer.

        Args:
            format: "json" or "markdown"

        Returns:
            Serializer instance
        """
        if format.lower() == "json":
            return JSONSerializer()
        elif format.lower() in ("markdown", "md"):
            return MarkdownSerializer()
        else:
            raise ValueError(f"Unknown format: {format}")

    @staticmethod
    def auto_detect(data: str) -> Serializer:
        """
        Auto-detect serializer based on content.

        Args:
            data: Data to analyze

        Returns:
            Appropriate Serializer
        """
        data = data.strip()

        # JSON starts with { or [
        if data.startswith(("{", "[")):
            return JSONSerializer()

        # Markdown has section markers
        if "---" in data:
            return MarkdownSerializer()

        # Default to JSON
        return JSONSerializer()
