"""
Atlas Core - Knowledge Infrastructure

Atlas is a layered system for observing, recording, and reasoning
about artifacts across diverse sources.

Layers:
1. Spine (Ledger) - Event log, identity, provenance
2. Eyes - Observers for different source types
3. Thread - Proposals, hypotheses, conflict detection

Add-ons:
- Salience - What matters
- Session - Bounded observation contexts

The ledger is the source of truth. Everything else is rebuildable.
"""

__version__ = "0.1.0"

# Core schema
from .schema import (
    Artifact,
    ArtifactIdentity,
    ArtifactKind,
    ArtifactRole,
    Source,
    SourceType,
    AccessScope,
    Fingerprint,
    ExtractionResult,
    Tag,
    TagGroup,
    Relation,
    ProvenanceEntry,
    ProvenanceAction,
    TemporalIntelligence,
    create_artifact,
)

# Confidence system
from .confidence import (
    ConfidenceAssessment,
    ConfidenceLevel,
    ConfidenceBuilder,
    AmbiguityType,
    combine_confidence,
    confidence_from_observation,
    confidence_from_inference,
)

# Budget system
from .budgets import (
    Budget,
    BudgetLimit,
    BudgetType,
    BudgetGuard,
    BudgetPresets,
)

# Relations
from .relations import (
    RelationType,
    RelationEdge,
    RelationGraph,
)

__all__ = [
    # Version
    "__version__",
    # Schema
    "Artifact",
    "ArtifactIdentity",
    "ArtifactKind",
    "ArtifactRole",
    "Source",
    "SourceType",
    "AccessScope",
    "Fingerprint",
    "ExtractionResult",
    "Tag",
    "TagGroup",
    "Relation",
    "ProvenanceEntry",
    "ProvenanceAction",
    "TemporalIntelligence",
    "create_artifact",
    # Confidence
    "ConfidenceAssessment",
    "ConfidenceLevel",
    "ConfidenceBuilder",
    "AmbiguityType",
    "combine_confidence",
    "confidence_from_observation",
    "confidence_from_inference",
    # Budget
    "Budget",
    "BudgetLimit",
    "BudgetType",
    "BudgetGuard",
    "BudgetPresets",
    # Relations
    "RelationType",
    "RelationEdge",
    "RelationGraph",
]
