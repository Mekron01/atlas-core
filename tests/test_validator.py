"""
Tests for EventValidator.

Tests event validation including:
- Envelope validation
- Event type validation
- Payload validation per event type
"""

import time

import pytest

from atlas.ledger.validator import (
    ValidationResult,
    validate_event,
    validate_strict,
)


class TestEventValidator:
    """Test EventValidator functionality."""

    def test_valid_artifact_seen_event(self):
        """Test valid ARTIFACT_SEEN event passes validation."""
        event = {
            "event_id": "test-001",
            "event_type": "ARTIFACT_SEEN",
            "ts": time.time(),
            "actor": {"module": "test"},
            "payload": {
                "artifact_id": "art-001",
                "locator": "/test/file.txt",
            },
        }

        result = validate_strict(event)
        assert result.valid
        assert len(result.errors) == 0

    def test_missing_event_id(self):
        """Test missing event_id fails validation."""
        event = {
            "event_type": "ARTIFACT_SEEN",
            "ts": time.time(),
            "actor": {"module": "test"},
            "payload": {},
        }

        result = validate_strict(event)
        assert not result.valid
        assert any("event_id" in e.path for e in result.errors)

    def test_missing_event_type(self):
        """Test missing event_type fails validation."""
        event = {
            "event_id": "test-002",
            "ts": time.time(),
            "actor": {"module": "test"},
            "payload": {},
        }

        result = validate_strict(event)
        assert not result.valid
        assert any("event_type" in e.path for e in result.errors)

    def test_invalid_event_type(self):
        """Test unknown event_type fails validation."""
        event = {
            "event_id": "test-003",
            "event_type": "UNKNOWN_EVENT",
            "ts": time.time(),
            "actor": {"module": "test"},
            "payload": {},
        }

        result = validate_strict(event)
        assert not result.valid
        assert any("event_type" in e.path for e in result.errors)

    def test_missing_actor_module(self):
        """Test missing actor.module fails validation."""
        event = {
            "event_id": "test-004",
            "event_type": "ARTIFACT_SEEN",
            "ts": time.time(),
            "actor": {},  # Missing module
            "payload": {
                "artifact_id": "art-004",
                "locator": "/test/file.txt",
            },
        }

        result = validate_strict(event)
        assert not result.valid
        assert any("actor.module" in e.path for e in result.errors)

    def test_missing_required_payload_field(self):
        """Test missing required payload field fails validation."""
        event = {
            "event_id": "test-005",
            "event_type": "ARTIFACT_SEEN",
            "ts": time.time(),
            "actor": {"module": "test"},
            "payload": {
                "artifact_id": "art-005",
                # Missing locator
            },
        }

        result = validate_strict(event)
        assert not result.valid
        assert any("payload.locator" in e.path for e in result.errors)

    def test_wrong_payload_field_type(self):
        """Test wrong payload field type fails validation."""
        event = {
            "event_id": "test-006",
            "event_type": "FINGERPRINT_COMPUTED",
            "ts": time.time(),
            "actor": {"module": "test"},
            "payload": {
                "artifact_id": "art-006",
                "content_hash": 12345,  # Should be string
            },
        }

        result = validate_strict(event)
        assert not result.valid
        assert any("payload.content_hash" in e.path for e in result.errors)

    def test_valid_relation_proposed_event(self):
        """Test valid RELATION_PROPOSED event passes validation."""
        event = {
            "event_id": "test-007",
            "event_type": "RELATION_PROPOSED",
            "ts": time.time(),
            "actor": {"module": "test"},
            "payload": {
                "source_id": "art-001",
                "target_id": "art-002",
                "relation_type": "DEPENDS_ON",
            },
        }

        result = validate_strict(event)
        assert result.valid

    def test_valid_confidence_updated_event(self):
        """Test valid CONFIDENCE_UPDATED event passes validation."""
        event = {
            "event_id": "test-008",
            "event_type": "CONFIDENCE_UPDATED",
            "ts": time.time(),
            "actor": {"module": "test"},
            "payload": {
                "artifact_id": "art-001",
                "new_confidence": 0.85,
                "old_confidence": 0.7,
                "reason": "New evidence",
            },
        }

        result = validate_strict(event)
        assert result.valid

    def test_valid_session_events(self):
        """Test SESSION_STARTED and SESSION_ENDED events pass validation."""
        start_event = {
            "event_id": "test-009",
            "event_type": "SESSION_STARTED",
            "ts": time.time(),
            "actor": {"module": "CLI"},
            "payload": {
                "target": "/test/path",
                "command": "scan",
            },
        }

        end_event = {
            "event_id": "test-010",
            "event_type": "SESSION_ENDED",
            "ts": time.time(),
            "actor": {"module": "CLI"},
            "payload": {
                "duration_ms": 1234.5,
                "files_seen": 100,
            },
        }

        assert validate_strict(start_event).valid
        assert validate_strict(end_event).valid


class TestValidationResult:
    """Test ValidationResult functionality."""

    def test_ok_result(self):
        """Test ValidationResult.ok() returns valid result."""
        result = ValidationResult.ok()
        assert result.valid
        assert len(result.errors) == 0

    def test_fail_result(self):
        """Test ValidationResult.fail() returns invalid result."""
        result = ValidationResult.fail("field", "error message", "value")
        assert not result.valid
        assert len(result.errors) == 1
        assert result.errors[0].path == "field"
        assert result.errors[0].message == "error message"

    def test_merge_valid_results(self):
        """Test merging two valid results stays valid."""
        result1 = ValidationResult.ok()
        result2 = ValidationResult.ok()

        merged = result1.merge(result2)
        assert merged.valid

    def test_merge_invalid_results(self):
        """Test merging invalid results combines errors."""
        result1 = ValidationResult.fail("field1", "error1")
        result2 = ValidationResult.fail("field2", "error2")

        merged = result1.merge(result2)
        assert not merged.valid
        assert len(merged.errors) == 2


class TestLegacyValidation:
    """Test legacy validate_event function."""

    def test_valid_event(self):
        """Test valid event returns True."""
        event = {
            "event_id": "test-001",
            "event_type": "ARTIFACT_SEEN",
            "ts": time.time(),
            "actor": {"module": "test"},
            "payload": {},
        }

        assert validate_event(event) is True

    def test_missing_keys_raises(self):
        """Test missing keys raises ValueError."""
        event = {
            "event_id": "test-001",
            # Missing event_type, ts, actor, payload
        }

        with pytest.raises(ValueError) as excinfo:
            validate_event(event)

        assert "Missing event keys" in str(excinfo.value)
