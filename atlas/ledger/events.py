"""
Atlas Ledger Event Schema

Events are the atomic units of truth in Atlas.
All state changes are recorded as immutable events.
Events are never deleted or modified.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Optional
from uuid import UUID, uuid4


class EventType(Enum):
    """Categories of events in Atlas."""
    
    # Observation events (from Eyes)
    ARTIFACT_OBSERVED = auto()
    ARTIFACT_CONTENT_EXTRACTED = auto()
    ARTIFACT_ACCESS_DENIED = auto()
    ARTIFACT_DISAPPEARED = auto()
    ARTIFACT_CHANGED = auto()
    
    # Fingerprint events
    FINGERPRINT_COMPUTED = auto()
    FINGERPRINT_COLLISION_DETECTED = auto()
    
    # Proposal events (from Thread)
    TAG_PROPOSED = auto()
    ROLE_PROPOSED = auto()
    RELATION_PROPOSED = auto()
    
    # Conflict events
    CONFLICT_DETECTED = auto()
    CONFLICT_RECORDED = auto()
    
    # Provenance events
    PROVENANCE_CHAIN_EXTENDED = auto()
    ARTIFACT_SUPERSEDED = auto()
    
    # Confidence events
    CONFIDENCE_UPDATED = auto()
    EVIDENCE_ADDED = auto()
    
    # System events
    SESSION_STARTED = auto()
    SESSION_ENDED = auto()
    BUDGET_EXHAUSTED = auto()
    ERROR_RECORDED = auto()


@dataclass(frozen=True)
class EventMetadata:
    """Metadata attached to every event."""
    event_id: UUID
    timestamp: datetime
    event_type: EventType
    source: str  # Which component emitted this event
    session_id: Optional[UUID] = None
    correlation_id: Optional[UUID] = None  # Links related events
    
    @classmethod
    def create(
        cls,
        event_type: EventType,
        source: str,
        session_id: Optional[UUID] = None,
        correlation_id: Optional[UUID] = None,
    ) -> EventMetadata:
        return cls(
            event_id=uuid4(),
            timestamp=datetime.utcnow(),
            event_type=event_type,
            source=source,
            session_id=session_id,
            correlation_id=correlation_id,
        )


@dataclass(frozen=True)
class Event:
    """
    Base event structure.
    
    All events are immutable and carry:
    - Metadata (who, when, what type)
    - Payload (event-specific data)
    - Optional references to related artifacts/events
    """
    metadata: EventMetadata
    payload: dict[str, Any]
    artifact_refs: tuple[UUID, ...] = field(default_factory=tuple)
    event_refs: tuple[UUID, ...] = field(default_factory=tuple)
    
    @property
    def event_id(self) -> UUID:
        return self.metadata.event_id
    
    @property
    def event_type(self) -> EventType:
        return self.metadata.event_type
    
    @property
    def timestamp(self) -> datetime:
        return self.metadata.timestamp


# -----------------------------------------------------------------------------
# Event Factories - Type-safe event creation
# -----------------------------------------------------------------------------

def artifact_observed(
    source: str,
    artifact_id: UUID,
    artifact_kind: str,
    source_type: str,
    source_locator: str,
    access_scope: str,
    *,
    session_id: Optional[UUID] = None,
) -> Event:
    """Create an artifact observation event."""
    return Event(
        metadata=EventMetadata.create(
            EventType.ARTIFACT_OBSERVED,
            source=source,
            session_id=session_id,
        ),
        payload={
            "artifact_kind": artifact_kind,
            "source_type": source_type,
            "source_locator": source_locator,
            "access_scope": access_scope,
        },
        artifact_refs=(artifact_id,),
    )


def artifact_content_extracted(
    source: str,
    artifact_id: UUID,
    extraction_depth: int,
    size_bytes: int,
    content_hash: Optional[str] = None,
    extracted_text_ref: Optional[str] = None,
    errors: tuple[str, ...] = (),
    *,
    session_id: Optional[UUID] = None,
) -> Event:
    """Create a content extraction event."""
    return Event(
        metadata=EventMetadata.create(
            EventType.ARTIFACT_CONTENT_EXTRACTED,
            source=source,
            session_id=session_id,
        ),
        payload={
            "extraction_depth": extraction_depth,
            "size_bytes": size_bytes,
            "content_hash": content_hash,
            "extracted_text_ref": extracted_text_ref,
            "errors": list(errors),
        },
        artifact_refs=(artifact_id,),
    )


def artifact_access_denied(
    source: str,
    artifact_id: UUID,
    source_locator: str,
    reason: str,
    *,
    session_id: Optional[UUID] = None,
) -> Event:
    """Record that access to an artifact was denied."""
    return Event(
        metadata=EventMetadata.create(
            EventType.ARTIFACT_ACCESS_DENIED,
            source=source,
            session_id=session_id,
        ),
        payload={
            "source_locator": source_locator,
            "reason": reason,
        },
        artifact_refs=(artifact_id,),
    )


def artifact_changed(
    source: str,
    artifact_id: UUID,
    previous_hash: Optional[str],
    current_hash: str,
    change_type: str,  # "content", "metadata", "both"
    *,
    session_id: Optional[UUID] = None,
) -> Event:
    """Record that an artifact has changed since last observation."""
    return Event(
        metadata=EventMetadata.create(
            EventType.ARTIFACT_CHANGED,
            source=source,
            session_id=session_id,
        ),
        payload={
            "previous_hash": previous_hash,
            "current_hash": current_hash,
            "change_type": change_type,
        },
        artifact_refs=(artifact_id,),
    )


def fingerprint_computed(
    source: str,
    artifact_id: UUID,
    content_hash: Optional[str],
    structure_hash: Optional[str],
    size_bytes: int,
    entropy_score: Optional[float],
    *,
    session_id: Optional[UUID] = None,
) -> Event:
    """Record fingerprint computation."""
    return Event(
        metadata=EventMetadata.create(
            EventType.FINGERPRINT_COMPUTED,
            source=source,
            session_id=session_id,
        ),
        payload={
            "content_hash": content_hash,
            "structure_hash": structure_hash,
            "size_bytes": size_bytes,
            "entropy_score": entropy_score,
        },
        artifact_refs=(artifact_id,),
    )


def tag_proposed(
    source: str,
    artifact_id: UUID,
    tag_group: str,
    tag_value: str,
    confidence_score: float,
    confidence_reasoning: str,
    *,
    session_id: Optional[UUID] = None,
) -> Event:
    """Record a tag proposal from Thread."""
    return Event(
        metadata=EventMetadata.create(
            EventType.TAG_PROPOSED,
            source=source,
            session_id=session_id,
        ),
        payload={
            "tag_group": tag_group,
            "tag_value": tag_value,
            "confidence_score": confidence_score,
            "confidence_reasoning": confidence_reasoning,
        },
        artifact_refs=(artifact_id,),
    )


def role_proposed(
    source: str,
    artifact_id: UUID,
    role: str,
    confidence_score: float,
    confidence_reasoning: str,
    *,
    session_id: Optional[UUID] = None,
) -> Event:
    """Record a role proposal from Thread."""
    return Event(
        metadata=EventMetadata.create(
            EventType.ROLE_PROPOSED,
            source=source,
            session_id=session_id,
        ),
        payload={
            "role": role,
            "confidence_score": confidence_score,
            "confidence_reasoning": confidence_reasoning,
        },
        artifact_refs=(artifact_id,),
    )


def relation_proposed(
    source: str,
    source_artifact_id: UUID,
    target_artifact_id: UUID,
    relation_type: str,
    confidence_score: float,
    confidence_reasoning: str,
    *,
    session_id: Optional[UUID] = None,
) -> Event:
    """Record a relation proposal from Thread."""
    return Event(
        metadata=EventMetadata.create(
            EventType.RELATION_PROPOSED,
            source=source,
            session_id=session_id,
        ),
        payload={
            "relation_type": relation_type,
            "confidence_score": confidence_score,
            "confidence_reasoning": confidence_reasoning,
        },
        artifact_refs=(source_artifact_id, target_artifact_id),
    )


def conflict_detected(
    source: str,
    artifact_ids: tuple[UUID, ...],
    conflict_type: str,
    description: str,
    *,
    session_id: Optional[UUID] = None,
) -> Event:
    """Record detection of a conflict."""
    return Event(
        metadata=EventMetadata.create(
            EventType.CONFLICT_DETECTED,
            source=source,
            session_id=session_id,
        ),
        payload={
            "conflict_type": conflict_type,
            "description": description,
        },
        artifact_refs=artifact_ids,
    )


def confidence_updated(
    source: str,
    artifact_id: UUID,
    previous_score: Optional[float],
    new_score: float,
    reasoning: str,
    evidence_refs: tuple[UUID, ...] = (),
    *,
    session_id: Optional[UUID] = None,
) -> Event:
    """Record a confidence score update."""
    return Event(
        metadata=EventMetadata.create(
            EventType.CONFIDENCE_UPDATED,
            source=source,
            session_id=session_id,
        ),
        payload={
            "previous_score": previous_score,
            "new_score": new_score,
            "reasoning": reasoning,
        },
        artifact_refs=(artifact_id,),
        event_refs=evidence_refs,
    )


def budget_exhausted(
    source: str,
    budget_type: str,
    limit: float,
    consumed: float,
    *,
    session_id: Optional[UUID] = None,
) -> Event:
    """Record budget exhaustion."""
    return Event(
        metadata=EventMetadata.create(
            EventType.BUDGET_EXHAUSTED,
            source=source,
            session_id=session_id,
        ),
        payload={
            "budget_type": budget_type,
            "limit": limit,
            "consumed": consumed,
        },
    )


def error_recorded(
    source: str,
    error_type: str,
    message: str,
    artifact_ids: tuple[UUID, ...] = (),
    *,
    session_id: Optional[UUID] = None,
) -> Event:
    """Record an error without corrupting state."""
    return Event(
        metadata=EventMetadata.create(
            EventType.ERROR_RECORDED,
            source=source,
            session_id=session_id,
        ),
        payload={
            "error_type": error_type,
            "message": message,
        },
        artifact_refs=artifact_ids,
    )
