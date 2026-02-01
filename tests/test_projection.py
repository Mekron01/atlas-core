"""
Tests for ledger projection (rebuild from events).

Tests reducer functions and snapshot creation.
"""

import time

from atlas.ledger.reducers import project_artifacts


class TestProjectArtifacts:
    """Test project_artifacts reducer."""

    def test_empty_events(self):
        """Test projecting empty event list."""
        events = []
        result = project_artifacts(events)

        assert isinstance(result, dict)
        assert len(result) == 0

    def test_single_artifact_seen(self):
        """Test projecting single ARTIFACT_SEEN event."""
        events = [
            {
                "event_id": "evt-001",
                "event_type": "ARTIFACT_SEEN",
                "ts": time.time(),
                "actor": {"module": "test"},
                "payload": {
                    "artifact_id": "art-001",
                    "locator": "/test/file.txt",
                    "size_bytes": 1024,
                },
            }
        ]

        result = project_artifacts(events)

        assert "art-001" in result
        assert result["art-001"]["locator"] == "/test/file.txt"
        assert result["art-001"]["size_bytes"] == 1024

    def test_multiple_artifacts(self):
        """Test projecting multiple artifacts."""
        now = time.time()
        events = [
            {
                "event_id": "evt-001",
                "event_type": "ARTIFACT_SEEN",
                "ts": now,
                "actor": {"module": "test"},
                "payload": {
                    "artifact_id": "art-001",
                    "locator": "/test/file1.txt",
                },
            },
            {
                "event_id": "evt-002",
                "event_type": "ARTIFACT_SEEN",
                "ts": now + 1,
                "actor": {"module": "test"},
                "payload": {
                    "artifact_id": "art-002",
                    "locator": "/test/file2.txt",
                },
            },
        ]

        result = project_artifacts(events)

        assert len(result) == 2
        assert "art-001" in result
        assert "art-002" in result

    def test_fingerprint_computed(self):
        """Test FINGERPRINT_COMPUTED updates artifact."""
        now = time.time()
        events = [
            {
                "event_id": "evt-001",
                "event_type": "ARTIFACT_SEEN",
                "ts": now,
                "actor": {"module": "test"},
                "payload": {
                    "artifact_id": "art-001",
                    "locator": "/test/file.txt",
                },
            },
            {
                "event_id": "evt-002",
                "event_type": "FINGERPRINT_COMPUTED",
                "ts": now + 1,
                "actor": {"module": "test"},
                "payload": {
                    "artifact_id": "art-001",
                    "content_hash": "abc123",
                },
            },
        ]

        result = project_artifacts(events)

        assert result["art-001"]["fingerprint"] == "abc123"

    def test_extraction_performed(self):
        """Test EXTRACTION_PERFORMED updates artifact."""
        now = time.time()
        events = [
            {
                "event_id": "evt-001",
                "event_type": "ARTIFACT_SEEN",
                "ts": now,
                "actor": {"module": "test"},
                "payload": {
                    "artifact_id": "art-001",
                    "locator": "/test/file.txt",
                },
            },
            {
                "event_id": "evt-002",
                "event_type": "EXTRACTION_PERFORMED",
                "ts": now + 1,
                "actor": {"module": "test"},
                "payload": {
                    "artifact_id": "art-001",
                    "extraction_depth": 2,
                    "extracted_metadata": {"title": "Test"},
                },
            },
        ]

        result = project_artifacts(events)

        assert result["art-001"]["extraction"]["depth"] == 2
        assert result["art-001"]["extraction"]["metadata"]["title"] == "Test"

    def test_last_seen_updated(self):
        """Test last_seen_at is updated on re-observation."""
        now = time.time()
        events = [
            {
                "event_id": "evt-001",
                "event_type": "ARTIFACT_SEEN",
                "ts": now,
                "actor": {"module": "test"},
                "payload": {
                    "artifact_id": "art-001",
                    "locator": "/test/file.txt",
                },
            },
            {
                "event_id": "evt-002",
                "event_type": "ARTIFACT_SEEN",
                "ts": now + 100,
                "actor": {"module": "test"},
                "payload": {
                    "artifact_id": "art-001",
                    "locator": "/test/file.txt",
                },
            },
        ]

        result = project_artifacts(events)

        assert result["art-001"]["last_seen_at"] == now + 100

    def test_ordering_preserved(self):
        """Test events are processed in order."""
        now = time.time()
        events = [
            {
                "event_id": "evt-001",
                "event_type": "ARTIFACT_SEEN",
                "ts": now,
                "actor": {"module": "test"},
                "payload": {
                    "artifact_id": "art-001",
                    "locator": "/test/old.txt",
                },
            },
            {
                "event_id": "evt-002",
                "event_type": "ARTIFACT_SEEN",
                "ts": now + 1,
                "actor": {"module": "test"},
                "payload": {
                    "artifact_id": "art-001",
                    "locator": "/test/new.txt",
                },
            },
        ]

        result = project_artifacts(events)

        # Later event should win
        assert result["art-001"]["locator"] == "/test/new.txt"
