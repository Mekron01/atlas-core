"""
Atlas Thread - Proposal and Hypothesis System

Thread proposes interpretations of observed data.
It can be wrong. All proposals carry confidence scores.

Rules:
- Proposals only: Thread suggests, never asserts
- Can be wrong: Proposals may be incorrect
- Confidence required: Every proposal has a confidence score
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional, Protocol
from uuid import UUID, uuid4

from ..confidence import (
    ConfidenceAssessment,
    ConfidenceBuilder,
    AmbiguityType,
)
from ..ledger.events import (
    Event,
    tag_proposed,
    role_proposed,
    relation_proposed,
    conflict_detected,
)
from ..schema import (
    TagGroup,
    ArtifactRole,
)


class ProposalStatus(Enum):
    """Status of a proposal."""
    PENDING = auto()      # Awaiting review/acceptance
    ACCEPTED = auto()     # Accepted into knowledge base
    REJECTED = auto()     # Rejected by review
    SUPERSEDED = auto()   # Replaced by newer proposal
    CONFLICTING = auto()  # Conflicts with other proposals


@dataclass
class Proposal:
    """Base class for all proposals."""
    proposal_id: UUID
    artifact_id: UUID
    confidence: ConfidenceAssessment
    proposed_by: str
    proposed_at: datetime
    status: ProposalStatus = ProposalStatus.PENDING
    
    @property
    def is_actionable(self) -> bool:
        """Whether confidence is high enough for auto-acceptance."""
        return self.confidence.is_actionable


@dataclass
class TagProposal(Proposal):
    """Proposal to add a tag to an artifact."""
    tag_group: TagGroup = None  # type: ignore[assignment]
    tag_value: str = ""
    
    def to_event(self, session_id: Optional[UUID] = None) -> Event:
        """Convert to ledger event."""
        return tag_proposed(
            source=self.proposed_by,
            artifact_id=self.artifact_id,
            tag_group=self.tag_group.name.lower(),
            tag_value=self.tag_value,
            confidence_score=self.confidence.score,
            confidence_reasoning=self.confidence.reasoning,
            session_id=session_id,
        )


@dataclass
class RoleProposal(Proposal):
    """Proposal to assign a role to an artifact."""
    role: ArtifactRole = None  # type: ignore[assignment]
    context: Optional[str] = None  # Why this role applies
    
    def to_event(self, session_id: Optional[UUID] = None) -> Event:
        """Convert to ledger event."""
        return role_proposed(
            source=self.proposed_by,
            artifact_id=self.artifact_id,
            role=self.role.name.lower(),
            confidence_score=self.confidence.score,
            confidence_reasoning=self.confidence.reasoning,
            session_id=session_id,
        )


@dataclass
class RelationProposal(Proposal):
    """Proposal of a relationship between artifacts."""
    target_artifact_id: UUID = None  # type: ignore[assignment]
    relation_type: str = ""
    bidirectional: bool = False
    
    def to_event(self, session_id: Optional[UUID] = None) -> Event:
        """Convert to ledger event."""
        return relation_proposed(
            source=self.proposed_by,
            source_artifact_id=self.artifact_id,
            target_artifact_id=self.target_artifact_id,
            relation_type=self.relation_type,
            confidence_score=self.confidence.score,
            confidence_reasoning=self.confidence.reasoning,
            session_id=session_id,
        )


# -----------------------------------------------------------------------------
# Conflict Detection
# -----------------------------------------------------------------------------

class ConflictType(Enum):
    """Types of conflicts that can be detected."""
    DUPLICATE_IDENTITY = auto()    # Same artifact, different IDs
    CONTRADICTORY_TAGS = auto()    # Incompatible tags
    CONTRADICTORY_ROLES = auto()   # Incompatible roles
    CIRCULAR_RELATION = auto()     # A -> B -> A
    ORPHANED_RELATION = auto()     # Relation to non-existent artifact
    CONFIDENCE_DISAGREEMENT = auto()  # High-confidence contradictions


@dataclass
class Conflict:
    """A detected conflict between proposals or data."""
    conflict_id: UUID
    conflict_type: ConflictType
    description: str
    artifact_ids: tuple[UUID, ...]
    proposals: tuple[UUID, ...] = field(default_factory=tuple)
    detected_at: datetime = field(default_factory=datetime.utcnow)
    resolved: bool = False
    
    def to_event(
        self,
        source: str,
        session_id: Optional[UUID] = None,
    ) -> Event:
        """Convert to ledger event."""
        return conflict_detected(
            source=source,
            artifact_ids=self.artifact_ids,
            conflict_type=self.conflict_type.name.lower(),
            description=self.description,
            session_id=session_id,
        )


class ConflictDetector:
    """Detects conflicts in proposals."""
    
    def __init__(self):
        self._tag_rules: dict[TagGroup, set[str]] = {}
        self._exclusive_roles: set[frozenset[ArtifactRole]] = set()
    
    def add_exclusive_tags(
        self,
        group: TagGroup,
        *values: str,
    ) -> None:
        """Define mutually exclusive tag values."""
        if group not in self._tag_rules:
            self._tag_rules[group] = set()
        self._tag_rules[group].update(values)
    
    def add_exclusive_roles(self, *roles: ArtifactRole) -> None:
        """Define mutually exclusive roles."""
        self._exclusive_roles.add(frozenset(roles))
    
    def check_tag_conflict(
        self,
        artifact_id: UUID,
        existing_tags: dict[TagGroup, str],
        new_proposal: TagProposal,
    ) -> Optional[Conflict]:
        """Check if a tag proposal conflicts with existing tags."""
        group = new_proposal.tag_group
        value = new_proposal.tag_value
        
        if group not in existing_tags:
            return None
        
        existing_value = existing_tags[group]
        if existing_value == value:
            return None  # Same tag, no conflict
        
        # Check if they're mutually exclusive
        if group in self._tag_rules:
            exclusive = self._tag_rules[group]
            if existing_value in exclusive and value in exclusive:
                return Conflict(
                    conflict_id=uuid4(),
                    conflict_type=ConflictType.CONTRADICTORY_TAGS,
                    description=(
                        f"Tag group {group.name}: "
                        f"'{existing_value}' conflicts with '{value}'"
                    ),
                    artifact_ids=(artifact_id,),
                    proposals=(new_proposal.proposal_id,),
                )
        
        return None
    
    def check_role_conflict(
        self,
        artifact_id: UUID,
        existing_roles: set[ArtifactRole],
        new_proposal: RoleProposal,
    ) -> Optional[Conflict]:
        """Check if a role proposal conflicts with existing roles."""
        new_role = new_proposal.role
        
        if new_role in existing_roles:
            return None  # Already has this role
        
        for exclusive_set in self._exclusive_roles:
            if new_role in exclusive_set:
                conflicting = existing_roles & exclusive_set
                if conflicting:
                    return Conflict(
                        conflict_id=uuid4(),
                        conflict_type=ConflictType.CONTRADICTORY_ROLES,
                        description=(
                            f"Role {new_role.name} is exclusive with "
                            f"{[r.name for r in conflicting]}"
                        ),
                        artifact_ids=(artifact_id,),
                        proposals=(new_proposal.proposal_id,),
                    )
        
        return None


# -----------------------------------------------------------------------------
# Hypothesis System
# -----------------------------------------------------------------------------

@dataclass
class Hypothesis:
    """
    A hypothesis about artifact relationships or meanings.
    
    Hypotheses are formed from multiple observations and
    can be strengthened or weakened by evidence.
    """
    hypothesis_id: UUID
    description: str
    confidence: ConfidenceAssessment
    supporting_artifacts: tuple[UUID, ...]
    supporting_proposals: tuple[UUID, ...] = field(default_factory=tuple)
    contradicting_evidence: tuple[str, ...] = field(default_factory=tuple)
    formed_at: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def is_strong(self) -> bool:
        """Whether hypothesis has strong support."""
        return (
            self.confidence.effective_score >= 0.75
            and len(self.contradicting_evidence) == 0
        )
    
    def strengthen(
        self,
        evidence: str,
        boost: float = 0.1,
    ) -> Hypothesis:
        """Return hypothesis with increased confidence."""
        new_confidence = ConfidenceBuilder(
            min(1.0, self.confidence.score + boost)
        ).with_reason(
            f"{self.confidence.reasoning}; strengthened by: {evidence}"
        ).build()
        
        return Hypothesis(
            hypothesis_id=self.hypothesis_id,
            description=self.description,
            confidence=new_confidence,
            supporting_artifacts=self.supporting_artifacts,
            supporting_proposals=self.supporting_proposals,
            contradicting_evidence=self.contradicting_evidence,
            formed_at=self.formed_at,
        )
    
    def weaken(
        self,
        evidence: str,
        penalty: float = 0.15,
    ) -> Hypothesis:
        """Return hypothesis with decreased confidence."""
        new_confidence = ConfidenceBuilder(
            max(0.0, self.confidence.score - penalty)
        ).with_reason(
            f"{self.confidence.reasoning}; weakened by: {evidence}"
        ).with_ambiguity(
            AmbiguityType.CONFLICTING_EVIDENCE
        ).build()
        
        return Hypothesis(
            hypothesis_id=self.hypothesis_id,
            description=self.description,
            confidence=new_confidence,
            supporting_artifacts=self.supporting_artifacts,
            supporting_proposals=self.supporting_proposals,
            contradicting_evidence=self.contradicting_evidence + (evidence,),
            formed_at=self.formed_at,
        )


class HypothesisEngine:
    """Forms and tracks hypotheses."""
    
    def __init__(self, thread_id: str = "atlas.thread"):
        self.thread_id = thread_id
        self._hypotheses: dict[UUID, Hypothesis] = {}
    
    def form_hypothesis(
        self,
        description: str,
        supporting_artifacts: tuple[UUID, ...],
        initial_confidence: float = 0.5,
        reasoning: str = "Initial hypothesis",
    ) -> Hypothesis:
        """Form a new hypothesis."""
        confidence = ConfidenceBuilder(initial_confidence).with_reason(
            reasoning
        ).with_ambiguity(
            AmbiguityType.INFERENCE_CHAIN
        ).build()
        
        hypothesis = Hypothesis(
            hypothesis_id=uuid4(),
            description=description,
            confidence=confidence,
            supporting_artifacts=supporting_artifacts,
        )
        
        self._hypotheses[hypothesis.hypothesis_id] = hypothesis
        return hypothesis
    
    def get_hypothesis(self, hypothesis_id: UUID) -> Optional[Hypothesis]:
        """Retrieve a hypothesis."""
        return self._hypotheses.get(hypothesis_id)
    
    def update_hypothesis(self, hypothesis: Hypothesis) -> None:
        """Update a hypothesis in the engine."""
        self._hypotheses[hypothesis.hypothesis_id] = hypothesis
    
    def strong_hypotheses(self) -> list[Hypothesis]:
        """Get all hypotheses with strong support."""
        return [h for h in self._hypotheses.values() if h.is_strong]
    
    def weak_hypotheses(self) -> list[Hypothesis]:
        """Get all hypotheses needing more evidence."""
        return [
            h for h in self._hypotheses.values()
            if h.confidence.effective_score < 0.5
        ]


# -----------------------------------------------------------------------------
# Thread Processor
# -----------------------------------------------------------------------------

class Thread:
    """
    Main Thread processor for proposals and hypotheses.
    
    Thread analyzes artifacts and proposes interpretations.
    All outputs are proposals with confidence - never assertions.
    """
    
    def __init__(self, thread_id: str = "atlas.thread"):
        self.thread_id = thread_id
        self.conflict_detector = ConflictDetector()
        self.hypothesis_engine = HypothesisEngine(thread_id)
        
        # Set up default exclusive rules
        self.conflict_detector.add_exclusive_roles(
            ArtifactRole.AUTHORITATIVE,
            ArtifactRole.EXPERIMENTAL,
        )
        self.conflict_detector.add_exclusive_roles(
            ArtifactRole.SOURCE,
            ArtifactRole.DERIVED,
        )
    
    def propose_tag(
        self,
        artifact_id: UUID,
        group: TagGroup,
        value: str,
        confidence: ConfidenceAssessment,
    ) -> TagProposal:
        """Create a tag proposal."""
        return TagProposal(
            proposal_id=uuid4(),
            artifact_id=artifact_id,
            confidence=confidence,
            proposed_by=self.thread_id,
            proposed_at=datetime.utcnow(),
            tag_group=group,
            tag_value=value,
        )
    
    def propose_role(
        self,
        artifact_id: UUID,
        role: ArtifactRole,
        confidence: ConfidenceAssessment,
        context: Optional[str] = None,
    ) -> RoleProposal:
        """Create a role proposal."""
        return RoleProposal(
            proposal_id=uuid4(),
            artifact_id=artifact_id,
            confidence=confidence,
            proposed_by=self.thread_id,
            proposed_at=datetime.utcnow(),
            role=role,
            context=context,
        )
    
    def propose_relation(
        self,
        source_artifact_id: UUID,
        target_artifact_id: UUID,
        relation_type: str,
        confidence: ConfidenceAssessment,
        bidirectional: bool = False,
    ) -> RelationProposal:
        """Create a relation proposal."""
        return RelationProposal(
            proposal_id=uuid4(),
            artifact_id=source_artifact_id,
            confidence=confidence,
            proposed_by=self.thread_id,
            proposed_at=datetime.utcnow(),
            target_artifact_id=target_artifact_id,
            relation_type=relation_type,
            bidirectional=bidirectional,
        )
    
    def form_hypothesis(
        self,
        description: str,
        supporting_artifacts: tuple[UUID, ...],
        initial_confidence: float = 0.5,
        reasoning: str = "Pattern detected",
    ) -> Hypothesis:
        """Form a new hypothesis."""
        return self.hypothesis_engine.form_hypothesis(
            description,
            supporting_artifacts,
            initial_confidence,
            reasoning,
        )
