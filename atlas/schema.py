"""
Atlas Artifact Schema (v0)

An Artifact represents a unit of observed existence.
All identity fields are immutable. Provenance is append-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional
from uuid import UUID, uuid4


# -----------------------------------------------------------------------------
# Enumerations
# -----------------------------------------------------------------------------

class ArtifactKind(Enum):
    """How the artifact came to be known."""
    LOCAL = auto()      # Observed directly on local system
    REMOTE = auto()     # Observed from remote source
    INFERRED = auto()   # Existence inferred from references


class SourceType(Enum):
    """The type of source where artifact was observed."""
    FILESYSTEM = auto()
    GIT = auto()
    DATABASE = auto()
    WEB = auto()
    API = auto()


class AccessScope(Enum):
    """What level of access was available during observation."""
    READ_ONLY = auto()
    PARTIAL = auto()
    METADATA_ONLY = auto()


class TagGroup(Enum):
    """Typed tag categories."""
    STRUCTURAL = auto()   # Shape, format, structure
    SEMANTIC = auto()     # Meaning, content type
    FUNCTIONAL = auto()   # Purpose, role in system
    TEMPORAL = auto()     # Time-related characteristics
    RISK = auto()         # Security, sensitivity


class ArtifactRole(Enum):
    """Contextual roles an artifact can hold."""
    SOURCE = auto()        # Origin of derived artifacts
    DERIVED = auto()       # Created from other artifacts
    AUTHORITATIVE = auto()  # Canonical/trusted version
    EXPERIMENTAL = auto()   # Tentative, unverified
    TRANSIENT = auto()      # Expected to change/disappear


class ProvenanceAction(Enum):
    """Actions recorded in provenance chain."""
    CREATED = auto()
    TRANSFORMED = auto()
    COPIED = auto()
    SUPERSEDED = auto()


# -----------------------------------------------------------------------------
# Component Dataclasses
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class ArtifactIdentity:
    """
    Immutable identity of an artifact.
    Once assigned, these fields never change.
    """
    artifact_id: UUID
    artifact_kind: ArtifactKind
    first_seen_at: datetime

    @classmethod
    def create(cls, kind: ArtifactKind) -> ArtifactIdentity:
        """Create a new artifact identity with generated ID and timestamp."""
        return cls(
            artifact_id=uuid4(),
            artifact_kind=kind,
            first_seen_at=datetime.utcnow(),
        )


@dataclass(frozen=True)
class Source:
    """Where and how the artifact was observed."""
    source_type: SourceType
    source_locator: str  # URI, path, or identifier
    access_scope: AccessScope


@dataclass(frozen=True)
class Fingerprint:
    """
    Content-derived identity markers.
    Used for deduplication and change detection.
    """
    size_bytes: int
    content_hash: Optional[str] = None    # SHA-256 of content
    structure_hash: Optional[str] = None  # Hash of structural representation
    entropy_score: Optional[float] = None
    signature_tags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self):
        # Validate entropy is in valid range if provided
        if self.entropy_score is not None:
            if not 0.0 <= self.entropy_score <= 8.0:
                raise ValueError("entropy_score must be between 0.0 and 8.0")


@dataclass(frozen=True)
class ExtractionResult:
    """
    Results of content extraction within budget.
    """
    extraction_depth: int  # How deep extraction went (0 = metadata only)
    extracted_text_ref: Optional[str] = None  # Reference to extracted text
    extracted_schema: Optional[dict] = None   # Structural schema if applicable
    extracted_metadata: dict = field(default_factory=dict)
    extraction_errors: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Confidence:
    """
    Confidence assessment for artifact data.
    All claims should carry confidence.
    """
    score: float  # 0.0 to 1.0
    reasoning: str
    evidence_refs: tuple[UUID, ...] = field(default_factory=tuple)
    ambiguity_flags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self):
        if not 0.0 <= self.score <= 1.0:
            raise ValueError("confidence score must be between 0.0 and 1.0")

    @classmethod
    def certain(cls, reasoning: str = "Direct observation") -> Confidence:
        """Create high-confidence assessment."""
        return cls(score=1.0, reasoning=reasoning)

    @classmethod
    def uncertain(
        cls, reasoning: str, flags: tuple[str, ...] = ()
    ) -> Confidence:
        """Create low-confidence assessment with ambiguity flags."""
        return cls(score=0.3, reasoning=reasoning, ambiguity_flags=flags)


@dataclass(frozen=True)
class Tag:
    """A typed tag with confidence."""
    group: TagGroup
    value: str
    confidence: Confidence


@dataclass(frozen=True)
class Relation:
    """
    Typed, directional, confidence-weighted relation to another artifact.
    """
    relation_type: str        # e.g., "imports", "derives_from", "references"
    target_id: UUID           # The related artifact
    confidence: Confidence
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ProvenanceEntry:
    """
    Single entry in append-only provenance chain.
    """
    action: ProvenanceAction
    timestamp: datetime
    actor: str  # What/who performed the action
    source_refs: tuple[UUID, ...] = field(default_factory=tuple)
    details: dict = field(default_factory=dict)


@dataclass(frozen=True)
class TemporalIntelligence:
    """
    Time-based understanding of artifact behavior.
    """
    last_seen_at: datetime
    change_count: int = 0
    freshness_score: float = 1.0  # 0.0 = stale, 1.0 = fresh
    volatility: float = 0.0       # 0.0 = stable, 1.0 = highly volatile

    def __post_init__(self):
        if not 0.0 <= self.freshness_score <= 1.0:
            raise ValueError("freshness_score must be between 0.0 and 1.0")
        if not 0.0 <= self.volatility <= 1.0:
            raise ValueError("volatility must be between 0.0 and 1.0")


# -----------------------------------------------------------------------------
# Main Artifact
# -----------------------------------------------------------------------------

@dataclass
class Artifact:
    """
    A unit of observed existence in Atlas.
    
    Identity is immutable. Provenance is append-only.
    Other fields may be updated through proper events.
    """
    # Immutable identity
    identity: ArtifactIdentity

    # Source information
    source: Source

    # Content fingerprint
    fingerprint: Optional[Fingerprint] = None

    # Extraction results
    extraction: Optional[ExtractionResult] = None

    # Overall confidence in this artifact's data
    confidence: Optional[Confidence] = None

    # Typed tags
    tags: tuple[Tag, ...] = field(default_factory=tuple)

    # Contextual roles
    roles: frozenset[ArtifactRole] = field(default_factory=frozenset)

    # Relations to other artifacts
    relations: tuple[Relation, ...] = field(default_factory=tuple)

    # Append-only provenance chain
    provenance: tuple[ProvenanceEntry, ...] = field(default_factory=tuple)

    # Temporal intelligence
    temporal: Optional[TemporalIntelligence] = None

    @property
    def artifact_id(self) -> UUID:
        """Convenience accessor for artifact ID."""
        return self.identity.artifact_id

    @property
    def kind(self) -> ArtifactKind:
        """Convenience accessor for artifact kind."""
        return self.identity.artifact_kind

    def with_provenance(self, entry: ProvenanceEntry) -> Artifact:
        """Return new artifact with provenance entry appended."""
        return Artifact(
            identity=self.identity,
            source=self.source,
            fingerprint=self.fingerprint,
            extraction=self.extraction,
            confidence=self.confidence,
            tags=self.tags,
            roles=self.roles,
            relations=self.relations,
            provenance=self.provenance + (entry,),
            temporal=self.temporal,
        )

    def with_tag(self, tag: Tag) -> Artifact:
        """Return new artifact with tag added."""
        return Artifact(
            identity=self.identity,
            source=self.source,
            fingerprint=self.fingerprint,
            extraction=self.extraction,
            confidence=self.confidence,
            tags=self.tags + (tag,),
            roles=self.roles,
            relations=self.relations,
            provenance=self.provenance,
            temporal=self.temporal,
        )

    def with_relation(self, relation: Relation) -> Artifact:
        """Return new artifact with relation added."""
        return Artifact(
            identity=self.identity,
            source=self.source,
            fingerprint=self.fingerprint,
            extraction=self.extraction,
            confidence=self.confidence,
            tags=self.tags,
            roles=self.roles,
            relations=self.relations + (relation,),
            provenance=self.provenance,
            temporal=self.temporal,
        )


# -----------------------------------------------------------------------------
# Factory Functions
# -----------------------------------------------------------------------------

def create_artifact(
    kind: ArtifactKind,
    source: Source,
    *,
    fingerprint: Optional[Fingerprint] = None,
    confidence: Optional[Confidence] = None,
) -> Artifact:
    """
    Create a new artifact with generated identity and initial provenance.
    """
    identity = ArtifactIdentity.create(kind)
    
    initial_provenance = ProvenanceEntry(
        action=ProvenanceAction.CREATED,
        timestamp=identity.first_seen_at,
        actor="atlas.spine",
    )

    temporal = TemporalIntelligence(
        last_seen_at=identity.first_seen_at,
    )

    return Artifact(
        identity=identity,
        source=source,
        fingerprint=fingerprint,
        confidence=confidence or Confidence.certain("Initial observation"),
        provenance=(initial_provenance,),
        temporal=temporal,
    )
