"""
Atlas Ledger Projection System

Projections rebuild state from the event log.
They are derived views - always rebuildable from the ledger.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Generic, Optional, Protocol, TypeVar
from uuid import UUID

from .events import Event, EventType


T = TypeVar("T")


class Projector(ABC, Generic[T]):
    """
    Base class for projections.
    
    A projector processes events and maintains derived state.
    The state can always be rebuilt by replaying events.
    """
    
    @abstractmethod
    def apply(self, event: Event) -> None:
        """Apply an event to update the projection state."""
        pass
    
    @abstractmethod
    def get_state(self) -> T:
        """Get the current projected state."""
        pass
    
    @abstractmethod
    def reset(self) -> None:
        """Reset state for full rebuild."""
        pass


# -----------------------------------------------------------------------------
# Artifact State Projection
# -----------------------------------------------------------------------------

@dataclass
class ArtifactSnapshot:
    """Current state of an artifact derived from events."""
    artifact_id: UUID
    first_seen: datetime
    last_seen: datetime
    source_type: Optional[str] = None
    source_locator: Optional[str] = None
    access_scope: Optional[str] = None
    
    # Latest fingerprint
    content_hash: Optional[str] = None
    structure_hash: Optional[str] = None
    size_bytes: Optional[int] = None
    entropy_score: Optional[float] = None
    
    # Tags (most recent proposals)
    tags: dict[str, tuple[str, float]] = field(default_factory=dict)
    
    # Roles (most recent proposals)
    roles: dict[str, float] = field(default_factory=dict)
    
    # Current confidence
    confidence_score: Optional[float] = None
    confidence_reasoning: Optional[str] = None
    
    # Counters
    observation_count: int = 0
    change_count: int = 0
    error_count: int = 0


class ArtifactProjector(Projector[dict[UUID, ArtifactSnapshot]]):
    """
    Projects artifact state from events.
    
    Maintains a snapshot of each known artifact.
    """
    
    def __init__(self):
        self._snapshots: dict[UUID, ArtifactSnapshot] = {}
    
    def apply(self, event: Event) -> None:
        """Apply an event to update artifact snapshots."""
        # Handle each event type
        handler = getattr(self, f"_handle_{event.event_type.name.lower()}", None)
        if handler:
            handler(event)
    
    def _ensure_artifact(
        self, artifact_id: UUID, timestamp: datetime
    ) -> ArtifactSnapshot:
        """Get or create an artifact snapshot."""
        if artifact_id not in self._snapshots:
            self._snapshots[artifact_id] = ArtifactSnapshot(
                artifact_id=artifact_id,
                first_seen=timestamp,
                last_seen=timestamp,
            )
        return self._snapshots[artifact_id]
    
    def _handle_artifact_observed(self, event: Event) -> None:
        """Handle artifact observation event."""
        for artifact_id in event.artifact_refs:
            snapshot = self._ensure_artifact(artifact_id, event.timestamp)
            snapshot.last_seen = event.timestamp
            snapshot.observation_count += 1
            snapshot.source_type = event.payload.get("source_type")
            snapshot.source_locator = event.payload.get("source_locator")
            snapshot.access_scope = event.payload.get("access_scope")
    
    def _handle_artifact_content_extracted(self, event: Event) -> None:
        """Handle content extraction event."""
        for artifact_id in event.artifact_refs:
            snapshot = self._ensure_artifact(artifact_id, event.timestamp)
            snapshot.last_seen = event.timestamp
            snapshot.size_bytes = event.payload.get("size_bytes")
            snapshot.content_hash = event.payload.get("content_hash")
            if event.payload.get("errors"):
                snapshot.error_count += len(event.payload["errors"])
    
    def _handle_artifact_changed(self, event: Event) -> None:
        """Handle artifact change event."""
        for artifact_id in event.artifact_refs:
            snapshot = self._ensure_artifact(artifact_id, event.timestamp)
            snapshot.last_seen = event.timestamp
            snapshot.change_count += 1
            snapshot.content_hash = event.payload.get("current_hash")
    
    def _handle_fingerprint_computed(self, event: Event) -> None:
        """Handle fingerprint computation event."""
        for artifact_id in event.artifact_refs:
            snapshot = self._ensure_artifact(artifact_id, event.timestamp)
            snapshot.content_hash = event.payload.get("content_hash")
            snapshot.structure_hash = event.payload.get("structure_hash")
            snapshot.size_bytes = event.payload.get("size_bytes")
            snapshot.entropy_score = event.payload.get("entropy_score")
    
    def _handle_tag_proposed(self, event: Event) -> None:
        """Handle tag proposal event."""
        for artifact_id in event.artifact_refs:
            snapshot = self._ensure_artifact(artifact_id, event.timestamp)
            tag_group = event.payload.get("tag_group")
            tag_value = event.payload.get("tag_value")
            confidence = event.payload.get("confidence_score", 0.0)
            if tag_group:
                snapshot.tags[tag_group] = (tag_value, confidence)
    
    def _handle_role_proposed(self, event: Event) -> None:
        """Handle role proposal event."""
        for artifact_id in event.artifact_refs:
            snapshot = self._ensure_artifact(artifact_id, event.timestamp)
            role = event.payload.get("role")
            confidence = event.payload.get("confidence_score", 0.0)
            if role:
                snapshot.roles[role] = confidence
    
    def _handle_confidence_updated(self, event: Event) -> None:
        """Handle confidence update event."""
        for artifact_id in event.artifact_refs:
            snapshot = self._ensure_artifact(artifact_id, event.timestamp)
            snapshot.confidence_score = event.payload.get("new_score")
            snapshot.confidence_reasoning = event.payload.get("reasoning")
    
    def _handle_error_recorded(self, event: Event) -> None:
        """Handle error event."""
        for artifact_id in event.artifact_refs:
            snapshot = self._ensure_artifact(artifact_id, event.timestamp)
            snapshot.error_count += 1
    
    def get_state(self) -> dict[UUID, ArtifactSnapshot]:
        """Get all artifact snapshots."""
        return self._snapshots.copy()
    
    def get_artifact(self, artifact_id: UUID) -> Optional[ArtifactSnapshot]:
        """Get snapshot for a specific artifact."""
        return self._snapshots.get(artifact_id)
    
    def reset(self) -> None:
        """Clear all snapshots for rebuild."""
        self._snapshots.clear()


# -----------------------------------------------------------------------------
# Relationship Projection
# -----------------------------------------------------------------------------

@dataclass
class RelationSnapshot:
    """A projected relationship between artifacts."""
    source_id: UUID
    target_id: UUID
    relation_type: str
    confidence_score: float
    last_proposed: datetime


class RelationProjector(Projector[list[RelationSnapshot]]):
    """Projects relationships from relation proposal events."""
    
    def __init__(self):
        self._relations: list[RelationSnapshot] = []
        self._index: dict[tuple[UUID, UUID, str], int] = {}
    
    def apply(self, event: Event) -> None:
        """Apply relation proposal events."""
        if event.event_type != EventType.RELATION_PROPOSED:
            return
        
        if len(event.artifact_refs) < 2:
            return
        
        source_id = event.artifact_refs[0]
        target_id = event.artifact_refs[1]
        relation_type = event.payload.get("relation_type", "unknown")
        confidence = event.payload.get("confidence_score", 0.0)
        
        key = (source_id, target_id, relation_type)
        
        if key in self._index:
            # Update existing relation
            idx = self._index[key]
            self._relations[idx] = RelationSnapshot(
                source_id=source_id,
                target_id=target_id,
                relation_type=relation_type,
                confidence_score=confidence,
                last_proposed=event.timestamp,
            )
        else:
            # Add new relation
            self._index[key] = len(self._relations)
            self._relations.append(RelationSnapshot(
                source_id=source_id,
                target_id=target_id,
                relation_type=relation_type,
                confidence_score=confidence,
                last_proposed=event.timestamp,
            ))
    
    def get_state(self) -> list[RelationSnapshot]:
        """Get all relations."""
        return self._relations.copy()
    
    def relations_for(
        self,
        artifact_id: UUID,
        *,
        as_source: bool = True,
        as_target: bool = True,
    ) -> list[RelationSnapshot]:
        """Get relations involving an artifact."""
        results = []
        for rel in self._relations:
            if as_source and rel.source_id == artifact_id:
                results.append(rel)
            elif as_target and rel.target_id == artifact_id:
                results.append(rel)
        return results
    
    def reset(self) -> None:
        """Clear for rebuild."""
        self._relations.clear()
        self._index.clear()


# -----------------------------------------------------------------------------
# Conflict Projection
# -----------------------------------------------------------------------------

@dataclass
class ConflictRecord:
    """A recorded conflict."""
    conflict_type: str
    description: str
    artifact_ids: tuple[UUID, ...]
    detected_at: datetime
    event_id: UUID


class ConflictProjector(Projector[list[ConflictRecord]]):
    """Projects conflicts from conflict events."""
    
    def __init__(self):
        self._conflicts: list[ConflictRecord] = []
    
    def apply(self, event: Event) -> None:
        """Apply conflict detection events."""
        if event.event_type != EventType.CONFLICT_DETECTED:
            return
        
        self._conflicts.append(ConflictRecord(
            conflict_type=event.payload.get("conflict_type", "unknown"),
            description=event.payload.get("description", ""),
            artifact_ids=event.artifact_refs,
            detected_at=event.timestamp,
            event_id=event.event_id,
        ))
    
    def get_state(self) -> list[ConflictRecord]:
        """Get all conflicts."""
        return self._conflicts.copy()
    
    def conflicts_for(self, artifact_id: UUID) -> list[ConflictRecord]:
        """Get conflicts involving an artifact."""
        return [c for c in self._conflicts if artifact_id in c.artifact_ids]
    
    def reset(self) -> None:
        """Clear for rebuild."""
        self._conflicts.clear()


# -----------------------------------------------------------------------------
# Composite Projector
# -----------------------------------------------------------------------------

class ProjectionEngine:
    """
    Manages multiple projectors and rebuilds from ledger.
    """
    
    def __init__(self):
        self.artifacts = ArtifactProjector()
        self.relations = RelationProjector()
        self.conflicts = ConflictProjector()
        self._projectors = [
            self.artifacts,
            self.relations,
            self.conflicts,
        ]
        self._last_sequence: int = 0
    
    def apply(self, event: Event) -> None:
        """Apply an event to all projectors."""
        for projector in self._projectors:
            projector.apply(event)
    
    def rebuild_from(self, ledger) -> None:
        """Rebuild all projections from a ledger."""
        self.reset()
        for event in ledger.iter_events():
            self.apply(event)
    
    def reset(self) -> None:
        """Reset all projectors."""
        for projector in self._projectors:
            projector.reset()
        self._last_sequence = 0
