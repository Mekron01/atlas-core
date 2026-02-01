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
