"""
Tests for EventWriter.

Tests ledger writer functionality including:
- Basic event writing
- File creation and naming
- Strict validation mode
"""

import json
import time

import pytest

from atlas.ledger.writer import EventWriter


class TestEventWriter:
    """Test EventWriter functionality."""

    def test_append_creates_file(self, tmp_path):
        """Test that append creates the event file."""
        writer = EventWriter(ledger_dir=str(tmp_path))

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

        writer.append(event)

        # Check file was created
        files = list(tmp_path.glob("*.jsonl"))
        assert len(files) == 1

    def test_append_writes_json_line(self, tmp_path):
        """Test that append writes valid JSON line."""
        writer = EventWriter(ledger_dir=str(tmp_path))

        event = {
            "event_id": "test-002",
            "event_type": "ARTIFACT_SEEN",
            "ts": time.time(),
            "actor": {"module": "test"},
            "payload": {
                "artifact_id": "art-002",
                "locator": "/test/file2.txt",
            },
        }

        writer.append(event)

        # Read back and verify
        files = list(tmp_path.glob("*.jsonl"))
        content = files[0].read_text()
        lines = content.strip().split("\n")

        assert len(lines) == 1

        parsed = json.loads(lines[0])
        assert parsed["event_id"] == "test-002"
        assert parsed["event_type"] == "ARTIFACT_SEEN"

    def test_append_requires_event_id(self, tmp_path):
        """Test that append rejects events without event_id."""
        writer = EventWriter(ledger_dir=str(tmp_path))

        event = {
            "event_type": "ARTIFACT_SEEN",
            "ts": time.time(),
            "actor": {"module": "test"},
            "payload": {},
        }

        with pytest.raises(ValueError) as excinfo:
            writer.append(event)

        assert "Invalid event envelope" in str(excinfo.value)

    def test_append_requires_event_type(self, tmp_path):
        """Test that append rejects events without event_type."""
        writer = EventWriter(ledger_dir=str(tmp_path))

        event = {
            "event_id": "test-003",
            "ts": time.time(),
            "actor": {"module": "test"},
            "payload": {},
        }

        with pytest.raises(ValueError) as excinfo:
            writer.append(event)

        assert "Invalid event envelope" in str(excinfo.value)

    def test_strict_mode_validates_payload(self, tmp_path):
        """Test strict mode validates event payload."""
        writer = EventWriter(ledger_dir=str(tmp_path), strict=True)

        # Missing required payload fields for ARTIFACT_SEEN
        event = {
            "event_id": "test-004",
            "event_type": "ARTIFACT_SEEN",
            "ts": time.time(),
            "actor": {"module": "test"},
            "payload": {},  # Missing artifact_id and locator
        }

        with pytest.raises(ValueError) as excinfo:
            writer.append(event)

        assert "validation failed" in str(excinfo.value).lower()

    def test_strict_mode_accepts_valid_event(self, tmp_path):
        """Test strict mode accepts valid events."""
        writer = EventWriter(ledger_dir=str(tmp_path), strict=True)

        event = {
            "event_id": "test-005",
            "event_type": "ARTIFACT_SEEN",
            "ts": time.time(),
            "actor": {"module": "test"},
            "payload": {
                "artifact_id": "art-005",
                "locator": "/test/file5.txt",
            },
        }

        # Should not raise
        writer.append(event)

        # Verify written
        files = list(tmp_path.glob("*.jsonl"))
        assert len(files) == 1

    def test_multiple_events_same_file(self, tmp_path):
        """Test multiple events are written to same daily file."""
        writer = EventWriter(ledger_dir=str(tmp_path))

        for i in range(3):
            event = {
                "event_id": f"test-{i:03d}",
                "event_type": "ARTIFACT_SEEN",
                "ts": time.time(),
                "actor": {"module": "test"},
                "payload": {
                    "artifact_id": f"art-{i:03d}",
                    "locator": f"/test/file{i}.txt",
                },
            }
            writer.append(event)

        # Should be one file
        files = list(tmp_path.glob("*.jsonl"))
        assert len(files) == 1

        # With 3 lines
        content = files[0].read_text()
        lines = [line for line in content.strip().split("\n") if line]
        assert len(lines) == 3
