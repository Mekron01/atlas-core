"""
Atlas Confidence Tracking

All claims in Atlas carry confidence scores.
Confidence is evidence-based and transparent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional
from uuid import UUID


class ConfidenceLevel(Enum):
    """Discrete confidence levels for quick assessment."""
    CERTAIN = auto()      # 0.95 - 1.00: Direct observation, verified
    HIGH = auto()         # 0.75 - 0.94: Strong evidence
    MODERATE = auto()     # 0.50 - 0.74: Reasonable inference
    LOW = auto()          # 0.25 - 0.49: Weak evidence
    SPECULATIVE = auto()  # 0.00 - 0.24: Guess or hypothesis
    
    @classmethod
    def from_score(cls, score: float) -> ConfidenceLevel:
        """Convert numeric score to level."""
        if score >= 0.95:
            return cls.CERTAIN
        elif score >= 0.75:
            return cls.HIGH
        elif score >= 0.50:
            return cls.MODERATE
        elif score >= 0.25:
            return cls.LOW
        else:
            return cls.SPECULATIVE


class AmbiguityType(Enum):
    """Types of ambiguity that reduce confidence."""
    INCOMPLETE_DATA = auto()      # Missing information
    CONFLICTING_EVIDENCE = auto() # Evidence points both ways
    STALE_OBSERVATION = auto()    # Data may be outdated
    INFERENCE_CHAIN = auto()      # Multiple inference steps
    PARTIAL_ACCESS = auto()       # Couldn't fully observe
    EXTERNAL_DEPENDENCY = auto()  # Relies on external state
    HEURISTIC_MATCH = auto()      # Pattern-based guess


@dataclass(frozen=True)
class EvidenceItem:
    """A piece of evidence supporting a claim."""
    evidence_id: UUID
    source: str
    description: str
    weight: float  # 0.0 to 1.0, how much this evidence contributes
    timestamp: datetime
    artifact_refs: tuple[UUID, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ConfidenceAssessment:
    """
    Complete confidence assessment for a claim.
    
    Confidence is:
    - Numeric (0.0 to 1.0)
    - Evidence-based (references supporting data)
    - Transparent (reasoning is always provided)
    - Degradable (ambiguity flags reduce effective confidence)
    """
    score: float
    reasoning: str
    evidence: tuple[EvidenceItem, ...] = field(default_factory=tuple)
    ambiguity_flags: tuple[AmbiguityType, ...] = field(default_factory=tuple)
    assessed_at: Optional[datetime] = None
    
    def __post_init__(self):
        if not 0.0 <= self.score <= 1.0:
            raise ValueError("score must be between 0.0 and 1.0")
    
    @property
    def level(self) -> ConfidenceLevel:
        """Get discrete confidence level."""
        return ConfidenceLevel.from_score(self.effective_score)
    
    @property
    def effective_score(self) -> float:
        """
        Score adjusted for ambiguity.
        
        Each ambiguity flag reduces effective confidence.
        """
        if not self.ambiguity_flags:
            return self.score
        
        # Each flag reduces confidence by ~10%
        penalty = len(self.ambiguity_flags) * 0.1
        return max(0.0, self.score - penalty)
    
    @property
    def is_actionable(self) -> bool:
        """Whether confidence is high enough for automated actions."""
        return self.effective_score >= 0.75
    
    @property
    def needs_review(self) -> bool:
        """Whether this assessment should be reviewed."""
        return (
            self.effective_score < 0.50
            or AmbiguityType.CONFLICTING_EVIDENCE in self.ambiguity_flags
        )


# -----------------------------------------------------------------------------
# Confidence Calculations
# -----------------------------------------------------------------------------

def combine_confidence(assessments: list[ConfidenceAssessment]) -> float:
    """
    Combine multiple confidence assessments.
    
    Uses weighted average based on evidence strength.
    """
    if not assessments:
        return 0.0
    
    total_weight = 0.0
    weighted_sum = 0.0
    
    for assessment in assessments:
        # Weight by evidence count and base score
        weight = (1 + len(assessment.evidence)) * assessment.score
        total_weight += weight
        weighted_sum += assessment.effective_score * weight
    
    if total_weight == 0:
        return 0.0
    
    return weighted_sum / total_weight


def confidence_from_observation(
    access_scope: str,
    extraction_depth: int,
    has_content_hash: bool,
) -> ConfidenceAssessment:
    """
    Calculate confidence from observation parameters.
    
    Direct observations with full access have highest confidence.
    """
    base_score = 0.5
    reasoning_parts = []
    ambiguity: list[AmbiguityType] = []
    
    # Access scope affects confidence
    if access_scope == "read-only":
        base_score += 0.3
        reasoning_parts.append("Full read access")
    elif access_scope == "partial":
        base_score += 0.15
        reasoning_parts.append("Partial access")
        ambiguity.append(AmbiguityType.PARTIAL_ACCESS)
    else:  # metadata-only
        reasoning_parts.append("Metadata only")
        ambiguity.append(AmbiguityType.INCOMPLETE_DATA)
    
    # Extraction depth affects confidence
    if extraction_depth > 0:
        base_score += min(0.1, extraction_depth * 0.02)
        reasoning_parts.append(f"Extraction depth {extraction_depth}")
    
    # Content hash provides verification
    if has_content_hash:
        base_score += 0.1
        reasoning_parts.append("Content verified by hash")
    
    return ConfidenceAssessment(
        score=min(1.0, base_score),
        reasoning="; ".join(reasoning_parts),
        ambiguity_flags=tuple(ambiguity),
        assessed_at=datetime.utcnow(),
    )


def confidence_from_inference(
    source_confidence: float,
    inference_steps: int,
    supporting_evidence: int,
) -> ConfidenceAssessment:
    """
    Calculate confidence for inferred data.
    
    Inferences lose confidence with each step.
    """
    # Each inference step reduces confidence
    decay = 0.85 ** inference_steps
    base_score = source_confidence * decay
    
    # Supporting evidence can recover some confidence
    evidence_boost = min(0.2, supporting_evidence * 0.05)
    score = min(1.0, base_score + evidence_boost)
    
    ambiguity = [AmbiguityType.INFERENCE_CHAIN]
    if inference_steps > 2:
        ambiguity.append(AmbiguityType.INCOMPLETE_DATA)
    
    return ConfidenceAssessment(
        score=score,
        reasoning=(
            f"Inferred through {inference_steps} steps from "
            f"source confidence {source_confidence:.2f}, "
            f"with {supporting_evidence} supporting evidence items"
        ),
        ambiguity_flags=tuple(ambiguity),
        assessed_at=datetime.utcnow(),
    )


def confidence_degraded_by_time(
    original: ConfidenceAssessment,
    age_hours: float,
    volatility: float = 0.5,
) -> ConfidenceAssessment:
    """
    Degrade confidence based on data age.
    
    Volatile data loses confidence faster.
    """
    # Half-life based on volatility
    # High volatility (1.0) = 24 hour half-life
    # Low volatility (0.0) = 720 hour (30 day) half-life
    half_life = 720 - (volatility * 696)
    decay = 0.5 ** (age_hours / half_life)
    
    new_score = original.score * decay
    
    ambiguity = list(original.ambiguity_flags)
    if age_hours > 24 and AmbiguityType.STALE_OBSERVATION not in ambiguity:
        ambiguity.append(AmbiguityType.STALE_OBSERVATION)
    
    return ConfidenceAssessment(
        score=new_score,
        reasoning=(
            f"{original.reasoning}; "
            f"degraded by {age_hours:.1f} hours age (volatility={volatility})"
        ),
        evidence=original.evidence,
        ambiguity_flags=tuple(ambiguity),
        assessed_at=datetime.utcnow(),
    )


# -----------------------------------------------------------------------------
# Confidence Builder
# -----------------------------------------------------------------------------

class ConfidenceBuilder:
    """Fluent builder for confidence assessments."""
    
    def __init__(self, base_score: float = 0.5):
        self._score = base_score
        self._reasoning: list[str] = []
        self._evidence: list[EvidenceItem] = []
        self._ambiguity: list[AmbiguityType] = []
    
    def with_reason(self, reason: str) -> ConfidenceBuilder:
        """Add reasoning."""
        self._reasoning.append(reason)
        return self
    
    def with_evidence(self, evidence: EvidenceItem) -> ConfidenceBuilder:
        """Add supporting evidence."""
        self._evidence.append(evidence)
        self._score = min(1.0, self._score + evidence.weight * 0.1)
        return self
    
    def with_ambiguity(self, ambiguity: AmbiguityType) -> ConfidenceBuilder:
        """Add ambiguity flag."""
        self._ambiguity.append(ambiguity)
        return self
    
    def boost(self, amount: float, reason: str) -> ConfidenceBuilder:
        """Boost confidence score."""
        self._score = min(1.0, self._score + amount)
        self._reasoning.append(f"+{amount}: {reason}")
        return self
    
    def penalize(self, amount: float, reason: str) -> ConfidenceBuilder:
        """Reduce confidence score."""
        self._score = max(0.0, self._score - amount)
        self._reasoning.append(f"-{amount}: {reason}")
        return self
    
    def build(self) -> ConfidenceAssessment:
        """Build the final assessment."""
        return ConfidenceAssessment(
            score=self._score,
            reasoning="; ".join(self._reasoning) if self._reasoning else "No reasoning provided",
            evidence=tuple(self._evidence),
            ambiguity_flags=tuple(self._ambiguity),
            assessed_at=datetime.utcnow(),
        )


# -----------------------------------------------------------------------------
# Confidence Evolution Engine
# -----------------------------------------------------------------------------

import time
import uuid


class ConfidenceEngine:
    """
    Engine for evolving confidence over time.

    Handles:
    - Reinforcement when identical proposals recur
    - Reduction on contradiction
    - Freshness decay based on volatility

    Rules:
    - Never deletes history
    - All changes are explainable
    - Old beliefs decay, they do not disappear
    - Emits CONFIDENCE_UPDATED events
    """

    def __init__(self, writer=None):
        """
        Initialize confidence engine.

        Args:
            writer: Optional EventWriter for emitting events
        """
        self.writer = writer
        self.module_name = "ConfidenceEngine"

    def _make_event_id(self) -> str:
        """Generate unique event ID."""
        return f"conf-{uuid.uuid4().hex[:16]}"

    def _emit_confidence_updated(
        self,
        artifact_id: str,
        old_confidence: float,
        new_confidence: float,
        reason: str,
        trigger_event_ids: list[str],
        session_id: str = None,
    ) -> str:
        """Emit CONFIDENCE_UPDATED event."""
        if not self.writer:
            return ""

        event_id = self._make_event_id()

        event = {
            "event_id": event_id,
            "event_type": "CONFIDENCE_UPDATED",
            "ts": time.time(),
            "actor": {"module": self.module_name},
            "artifact_id": artifact_id,
            "confidence": new_confidence,
            "evidence_refs": trigger_event_ids,
            "payload": {
                "old_confidence": old_confidence,
                "new_confidence": new_confidence,
                "delta": new_confidence - old_confidence,
                "reason": reason,
            },
        }

        if session_id:
            event["session_id"] = session_id

        self.writer.append(event)
        return event_id

    def reinforce(
        self,
        artifact_id: str,
        current_confidence: float,
        recurring_proposal_count: int,
        trigger_event_ids: list[str],
        session_id: str = None,
    ) -> tuple[float, str]:
        """
        Reinforce confidence when identical proposals recur.

        Each recurrence increases confidence asymptotically toward 1.0.
        Diminishing returns prevent over-confidence.

        Args:
            artifact_id: Artifact being reinforced
            current_confidence: Current confidence value
            recurring_proposal_count: How many times proposal recurred
            trigger_event_ids: Events that triggered reinforcement
            session_id: Optional session ID

        Returns:
            Tuple of (new_confidence, event_id)
        """
        # Asymptotic reinforcement: each recurrence adds less
        # Formula: new = old + (1 - old) * factor
        # Where factor decreases with count
        factor = 0.1 / (1 + recurring_proposal_count * 0.5)
        boost = (1.0 - current_confidence) * factor
        new_confidence = min(1.0, current_confidence + boost)

        reason = (
            f"Reinforced by {recurring_proposal_count} recurring proposals "
            f"(+{boost:.3f})"
        )

        event_id = self._emit_confidence_updated(
            artifact_id=artifact_id,
            old_confidence=current_confidence,
            new_confidence=new_confidence,
            reason=reason,
            trigger_event_ids=trigger_event_ids,
            session_id=session_id,
        )

        return new_confidence, event_id

    def reduce_on_contradiction(
        self,
        artifact_id: str,
        current_confidence: float,
        contradiction_strength: float,
        trigger_event_ids: list[str],
        session_id: str = None,
    ) -> tuple[float, str]:
        """
        Reduce confidence when contradiction detected.

        Stronger contradictions cause larger reductions.
        Confidence cannot go below 0.05 (never fully discard).

        Args:
            artifact_id: Artifact with contradiction
            current_confidence: Current confidence value
            contradiction_strength: 0.0 to 1.0, how strong the contradiction
            trigger_event_ids: Conflicting event IDs
            session_id: Optional session ID

        Returns:
            Tuple of (new_confidence, event_id)
        """
        # Reduction proportional to contradiction strength
        # Strong contradiction (1.0) reduces by up to 50%
        reduction = current_confidence * contradiction_strength * 0.5
        new_confidence = max(0.05, current_confidence - reduction)

        reason = (
            f"Reduced due to contradiction (strength={contradiction_strength:.2f}, "
            f"-{reduction:.3f})"
        )

        event_id = self._emit_confidence_updated(
            artifact_id=artifact_id,
            old_confidence=current_confidence,
            new_confidence=new_confidence,
            reason=reason,
            trigger_event_ids=trigger_event_ids,
            session_id=session_id,
        )

        return new_confidence, event_id

    def apply_freshness_decay(
        self,
        artifact_id: str,
        current_confidence: float,
        last_observed_ts: float,
        volatility: float = 0.5,
        trigger_event_ids: list[str] = None,
        session_id: str = None,
    ) -> tuple[float, str]:
        """
        Apply freshness decay based on time since observation.

        Volatile artifacts (code, configs) decay faster.
        Stable artifacts (docs, schemas) decay slower.

        Args:
            artifact_id: Artifact to decay
            current_confidence: Current confidence value
            last_observed_ts: Timestamp of last observation
            volatility: 0.0 (stable) to 1.0 (volatile)
            trigger_event_ids: Related event IDs
            session_id: Optional session ID

        Returns:
            Tuple of (new_confidence, event_id)
        """
        now = time.time()
        age_hours = (now - last_observed_ts) / 3600

        if age_hours <= 0:
            return current_confidence, ""

        # Half-life in hours based on volatility
        # High volatility (1.0) = 24 hour half-life
        # Low volatility (0.0) = 720 hour (30 day) half-life
        half_life = 720 - (volatility * 696)
        decay_factor = 0.5 ** (age_hours / half_life)

        new_confidence = max(0.05, current_confidence * decay_factor)

        # Only emit event if meaningful change
        if abs(new_confidence - current_confidence) < 0.001:
            return current_confidence, ""

        reason = (
            f"Freshness decay: {age_hours:.1f}h old, "
            f"volatility={volatility:.2f}, half-life={half_life:.0f}h"
        )

        event_id = self._emit_confidence_updated(
            artifact_id=artifact_id,
            old_confidence=current_confidence,
            new_confidence=new_confidence,
            reason=reason,
            trigger_event_ids=trigger_event_ids or [],
            session_id=session_id,
        )

        return new_confidence, event_id

    def evolve_confidence(
        self,
        artifact_id: str,
        current_confidence: float,
        last_observed_ts: float,
        recurring_count: int = 0,
        contradiction_strength: float = 0.0,
        volatility: float = 0.5,
        trigger_event_ids: list[str] = None,
        session_id: str = None,
    ) -> tuple[float, list[str]]:
        """
        Apply all confidence evolution factors.

        Order:
        1. Apply freshness decay
        2. Apply contradiction reduction (if any)
        3. Apply reinforcement (if recurring)

        Args:
            artifact_id: Artifact to evolve
            current_confidence: Starting confidence
            last_observed_ts: Last observation timestamp
            recurring_count: Number of recurring proposals
            contradiction_strength: Contradiction strength (0-1)
            volatility: Artifact volatility (0-1)
            trigger_event_ids: Related event IDs
            session_id: Optional session ID

        Returns:
            Tuple of (final_confidence, list of event_ids)
        """
        event_ids = []
        confidence = current_confidence
        triggers = trigger_event_ids or []

        # 1. Freshness decay
        confidence, eid = self.apply_freshness_decay(
            artifact_id=artifact_id,
            current_confidence=confidence,
            last_observed_ts=last_observed_ts,
            volatility=volatility,
            trigger_event_ids=triggers,
            session_id=session_id,
        )
        if eid:
            event_ids.append(eid)

        # 2. Contradiction reduction
        if contradiction_strength > 0:
            confidence, eid = self.reduce_on_contradiction(
                artifact_id=artifact_id,
                current_confidence=confidence,
                contradiction_strength=contradiction_strength,
                trigger_event_ids=triggers,
                session_id=session_id,
            )
            if eid:
                event_ids.append(eid)

        # 3. Reinforcement
        if recurring_count > 0:
            confidence, eid = self.reinforce(
                artifact_id=artifact_id,
                current_confidence=confidence,
                recurring_proposal_count=recurring_count,
                trigger_event_ids=triggers,
                session_id=session_id,
            )
            if eid:
                event_ids.append(eid)

        return confidence, event_ids
