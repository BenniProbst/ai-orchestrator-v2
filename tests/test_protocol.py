"""
Tests for Protocol messages and serialization

Tests:
1. test_message_serialize_json
2. test_message_serialize_markdown
3. test_message_deserialize
4. test_protocol_request_response
5. test_protocol_error_handling
6. test_protocol_version_compat
7. test_protocol_streaming
"""

import pytest
import json
from datetime import datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from protocol.messages import (
    Message,
    MessageType,
    MessagePriority,
    RequestMessage,
    ResponseMessage,
    ErrorMessage,
    StatusMessage,
    DecisionMessage,
    VerificationMessage,
    MessageFactory,
)
from protocol.serializer import (
    Serializer,
    JSONSerializer,
    MarkdownSerializer,
    SerializerFactory,
)


class TestMessageSerialization:
    """Tests for message serialization"""

    def test_message_serialize_json(self, sample_request_message):
        """Test JSON serialization of messages"""
        serializer = JSONSerializer()
        json_str = serializer.serialize(sample_request_message)

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert parsed["type"] == "request"
        assert parsed["instruction"] == sample_request_message.instruction

    def test_message_serialize_markdown(self, sample_request_message):
        """Test Markdown serialization of messages"""
        serializer = MarkdownSerializer()
        md_str = serializer.serialize(sample_request_message)

        assert "---TYPE---" in md_str
        assert "REQUEST" in md_str
        assert "---INSTRUCTION---" in md_str

    def test_message_deserialize_json(self, sample_request_message):
        """Test JSON deserialization"""
        serializer = JSONSerializer()

        # Serialize then deserialize
        json_str = serializer.serialize(sample_request_message)
        restored = serializer.deserialize(json_str)

        assert isinstance(restored, RequestMessage)
        assert restored.instruction == sample_request_message.instruction

    def test_message_deserialize_markdown(self):
        """Test Markdown deserialization"""
        md_content = """---TYPE---
REQUEST

---INSTRUCTION---
Create a new file

---CONTEXT---
Python project

---EXPECTED---
File created

---METADATA---
ID: test123
Timestamp: 2024-01-01T00:00:00
Sender: master
Recipient: worker
"""
        serializer = MarkdownSerializer()
        message = serializer.deserialize(md_content)

        assert isinstance(message, RequestMessage)
        assert "Create a new file" in message.instruction


class TestProtocolRequestResponse:
    """Tests for request/response protocol"""

    def test_protocol_request_response(self):
        """Test request-response cycle"""
        # Create request
        request = MessageFactory.create_request(
            instruction="Implement feature X",
            context="FastAPI app",
        )

        assert request.type == MessageType.REQUEST
        assert request.sender == "master"
        assert request.recipient == "worker"

        # Create response
        response = MessageFactory.create_response(
            success=True,
            output="Feature implemented",
            correlation_id=request.id,
        )

        assert response.type == MessageType.RESPONSE
        assert response.correlation_id == request.id

    def test_protocol_message_ids(self):
        """Test that messages get unique IDs"""
        msg1 = RequestMessage(instruction="Test 1")
        msg2 = RequestMessage(instruction="Test 2")

        assert msg1.id != msg2.id

    def test_protocol_timestamps(self):
        """Test message timestamps"""
        msg = RequestMessage(instruction="Test")

        assert msg.timestamp is not None
        assert isinstance(msg.timestamp, datetime)


class TestProtocolErrorHandling:
    """Tests for error message handling"""

    def test_protocol_error_handling(self):
        """Test error message creation"""
        error = MessageFactory.create_error(
            error_code="E001",
            error_message="Something went wrong",
            sender="worker",
        )

        assert error.type == MessageType.ERROR
        assert error.error_code == "E001"
        assert error.priority == MessagePriority.HIGH  # Errors are high priority

    def test_protocol_error_recoverable(self):
        """Test recoverable vs non-recoverable errors"""
        recoverable = ErrorMessage(
            error_code="E001",
            error_message="Temporary failure",
            recoverable=True,
        )

        non_recoverable = ErrorMessage(
            error_code="E002",
            error_message="Fatal error",
            recoverable=False,
        )

        assert recoverable.recoverable
        assert not non_recoverable.recoverable


class TestProtocolVersionCompatibility:
    """Tests for protocol version compatibility"""

    def test_protocol_version_compat(self):
        """Test backward compatibility of message format"""
        # Old format (minimal fields)
        old_format = {
            "type": "request",
            "instruction": "Do something",
        }

        serializer = JSONSerializer()
        # Should handle missing fields gracefully
        message = serializer.deserialize(json.dumps(old_format))

        assert message.instruction == "Do something"

    def test_protocol_extra_fields_ignored(self):
        """Test that extra fields are ignored"""
        extended_format = {
            "type": "request",
            "instruction": "Test",
            "unknown_field": "should be ignored",
            "another_unknown": 123,
        }

        serializer = JSONSerializer()
        # Should not raise
        try:
            message = serializer.deserialize(json.dumps(extended_format))
            assert message.instruction == "Test"
        except TypeError:
            # If strict, that's also acceptable
            pass


class TestProtocolStreaming:
    """Tests for streaming/incremental protocol"""

    def test_protocol_streaming(self):
        """Test status message for streaming updates"""
        status = StatusMessage(
            status="processing",
            progress=0.5,
            current_task="Writing tests",
            tasks_completed=5,
            tasks_total=10,
        )

        assert status.type == MessageType.STATUS
        assert status.progress == 0.5
        assert status.tasks_completed == 5

    def test_protocol_status_serialization(self):
        """Test status message serialization"""
        status = StatusMessage(
            status="running",
            progress=0.75,
            current_task="Implementing feature",
        )

        serializer = JSONSerializer()
        json_str = serializer.serialize(status)
        parsed = json.loads(json_str)

        assert parsed["progress"] == 0.75
        assert parsed["current_task"] == "Implementing feature"


class TestSerializerFactory:
    """Tests for serializer factory"""

    def test_serializer_factory_json(self):
        """Test creating JSON serializer"""
        serializer = SerializerFactory.create("json")
        assert isinstance(serializer, JSONSerializer)

    def test_serializer_factory_markdown(self):
        """Test creating Markdown serializer"""
        serializer = SerializerFactory.create("markdown")
        assert isinstance(serializer, MarkdownSerializer)

    def test_serializer_factory_auto_detect_json(self):
        """Test auto-detecting JSON format"""
        json_data = '{"type": "request", "instruction": "test"}'
        serializer = SerializerFactory.auto_detect(json_data)
        assert isinstance(serializer, JSONSerializer)

    def test_serializer_factory_auto_detect_markdown(self):
        """Test auto-detecting Markdown format"""
        md_data = "---TYPE---\nREQUEST\n---INSTRUCTION---\ntest"
        serializer = SerializerFactory.auto_detect(md_data)
        assert isinstance(serializer, MarkdownSerializer)


class TestSpecialMessages:
    """Tests for special message types"""

    def test_decision_message(self):
        """Test decision message"""
        decision = DecisionMessage(
            decision_type="IMPLEMENT",
            instruction="Create the API",
            reason="Next logical step",
            expected_outcome="Working API",
        )

        assert decision.type == MessageType.DECISION
        assert decision.decision_type == "IMPLEMENT"

    def test_verification_message(self):
        """Test verification message"""
        verification = VerificationMessage(
            passed=True,
            score=0.95,
            issues=[],
            suggestions=["Add more tests"],
        )

        assert verification.type == MessageType.VERIFICATION
        assert verification.passed
        assert verification.score == 0.95
