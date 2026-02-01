"""
Atlas Thread Conflict Detector

Detects contradictory claims in observation payloads.
All outputs are proposals only - no assertions of truth.
"""

import time
import uuid
from typing import Optional


class ConflictDetector:
    """
    Detects conflicts between observations.

    Conflict types:
    - HASH_MISMATCH: Same path, different content hash
    - SIZE_MISMATCH: Same artifact, different sizes
    - TYPE_MISMATCH: Same artifact, different inferred types
    - TAG_CONTRADICTION: Mutually exclusive tags proposed

    Rules:
    - All outputs are proposals with confidence
    - Never overwrites existing state
    - Emits CONFLICT_DETECTED events
    """

    def __init__(self, writer):
        """
        Initialize conflict detector.

        Args:
            writer: EventWriter for emitting events
        """
        self.writer = writer
        self.module_name = "ConflictDetector"

        # Mutually exclusive tag pairs
        self.exclusive_tags = [
            ("test", "production"),
            ("deprecated", "active"),
            ("public", "private"),
            ("stable", "experimental"),
        ]

    def _make_event_id(self) -> str:
        """Generate unique event ID."""
        return f"conflict-{uuid.uuid4().hex[:16]}"

    def _emit_conflict_detected(
        self,
        artifact_ids: list[str],
        conflict_type: str,
        description: str,
        evidence_event_ids: list[str],
        confidence: float,
        session_id: Optional[str] = None,
    ) -> str:
        """Emit CONFLICT_DETECTED event."""
        event_id = self._make_event_id()

        event = {
            "event_id": event_id,
            "event_type": "CONFLICT_DETECTED",
            "ts": time.time(),
            "actor": {"module": self.module_name},
            "artifact_id": artifact_ids[0] if artifact_ids else None,
            "confidence": confidence,
            "evidence_refs": evidence_event_ids,
            "payload": {
                "artifact_ids": artifact_ids,
                "conflict_type": conflict_type,
                "description": description,
            },
        }

        if session_id:
            event["session_id"] = session_id

        self.writer.append(event)
        return event_id

    def detect_hash_mismatch(
        self,
        artifact_id: str,
        observations: list[dict],
        session_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Detect hash mismatches for same artifact.

        Args:
            artifact_id: Artifact to check
            observations: List of observation events
            session_id: Optional session ID

        Returns:
            Event ID if conflict detected, None otherwise
        """
        hashes = {}

        for obs in observations:
            payload = obs.get("payload", {})
            content_hash = payload.get("content_hash") or payload.get("hash")
            path = payload.get("path", "unknown")
            event_id = obs.get("event_id")

            if content_hash:
                if content_hash not in hashes:
                    hashes[content_hash] = []
                hashes[content_hash].append((path, event_id))

        if len(hashes) <= 1:
            return None

        # Multiple different hashes = conflict
        hash_list = list(hashes.keys())
        evidence_ids = []
        paths = []

        for h, entries in hashes.items():
            for path, eid in entries:
                evidence_ids.append(eid)
                paths.append(f"{path}:{h[:8]}")

        return self._emit_conflict_detected(
            artifact_ids=[artifact_id],
            conflict_type="HASH_MISMATCH",
            description=f"Same artifact has different hashes: {', '.join(paths)}",
            evidence_event_ids=evidence_ids,
            confidence=0.95,
            session_id=session_id,
        )

    def detect_size_mismatch(
        self,
        artifact_id: str,
        observations: list[dict],
        threshold: float = 0.1,
        session_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Detect significant size changes for same artifact.

        Args:
            artifact_id: Artifact to check
            observations: List of observation events
            threshold: Relative size difference threshold (0.1 = 10%)
            session_id: Optional session ID

        Returns:
            Event ID if conflict detected, None otherwise
        """
        sizes = []

        for obs in observations:
            payload = obs.get("payload", {})
            size = payload.get("size")
            event_id = obs.get("event_id")

            if size is not None:
                sizes.append((size, event_id))

        if len(sizes) < 2:
            return None

        sizes.sort(key=lambda x: x[0])
        min_size, min_eid = sizes[0]
        max_size, max_eid = sizes[-1]

        if min_size == 0:
            if max_size > 0:
                return self._emit_conflict_detected(
                    artifact_ids=[artifact_id],
                    conflict_type="SIZE_MISMATCH",
                    description=f"Size changed from 0 to {max_size} bytes",
                    evidence_event_ids=[min_eid, max_eid],
                    confidence=0.9,
                    session_id=session_id,
                )
            return None

        relative_diff = (max_size - min_size) / min_size

        if relative_diff > threshold:
            return self._emit_conflict_detected(
                artifact_ids=[artifact_id],
                conflict_type="SIZE_MISMATCH",
                description=f"Size varies: {min_size} to {max_size} bytes "
                            f"({relative_diff:.1%} difference)",
                evidence_event_ids=[min_eid, max_eid],
                confidence=0.8,
                session_id=session_id,
            )

        return None

    def detect_tag_contradiction(
        self,
        artifact_id: str,
        tag_events: list[dict],
        session_id: Optional[str] = None,
    ) -> list[str]:
        """
        Detect mutually exclusive tags on same artifact.

        Args:
            artifact_id: Artifact to check
            tag_events: List of TAGS_PROPOSED events
            session_id: Optional session ID

        Returns:
            List of conflict event IDs
        """
        all_tags = set()
        tag_sources: dict[str, str] = {}

        for event in tag_events:
            payload = event.get("payload", {})
            tags = payload.get("tags", [])
            event_id = event.get("event_id")

            for tag in tags:
                all_tags.add(tag)
                tag_sources[tag] = event_id

        conflicts = []

        for tag_a, tag_b in self.exclusive_tags:
            if tag_a in all_tags and tag_b in all_tags:
                eid = self._emit_conflict_detected(
                    artifact_ids=[artifact_id],
                    conflict_type="TAG_CONTRADICTION",
                    description=f"Mutually exclusive tags: {tag_a} and {tag_b}",
                    evidence_event_ids=[
                        tag_sources.get(tag_a, ""),
                        tag_sources.get(tag_b, ""),
                    ],
                    confidence=0.85,
                    session_id=session_id,
                )
                conflicts.append(eid)

        return conflicts

    def detect_all(
        self,
        artifact_id: str,
        observations: list[dict],
        tag_events: list[dict],
        session_id: Optional[str] = None,
    ) -> list[str]:
        """
        Run all conflict detection on an artifact.

        Args:
            artifact_id: Artifact to check
            observations: List of observation events
            tag_events: List of TAGS_PROPOSED events
            session_id: Optional session ID

        Returns:
            List of all conflict event IDs
        """
        conflicts = []

        hash_conflict = self.detect_hash_mismatch(
            artifact_id, observations, session_id
        )
        if hash_conflict:
            conflicts.append(hash_conflict)

        size_conflict = self.detect_size_mismatch(
            artifact_id, observations, session_id=session_id
        )
        if size_conflict:
            conflicts.append(size_conflict)

        tag_conflicts = self.detect_tag_contradiction(
            artifact_id, tag_events, session_id
        )
        conflicts.extend(tag_conflicts)

        return conflicts
