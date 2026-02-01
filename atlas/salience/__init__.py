"""
Atlas Salience Engine (Add-On Module)

Determines what matters in the observed data.
This is an optional module - removing it never breaks the core.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional
from uuid import UUID


class SalienceFactor(Enum):
    """Factors that contribute to salience."""
    RECENCY = auto()          # How recently observed
    FREQUENCY = auto()        # How often referenced
    CENTRALITY = auto()       # How connected in the graph
    VOLATILITY = auto()       # How often it changes
    SIZE = auto()             # Relative size/complexity
    CONFIDENCE = auto()       # How confident we are
    USER_ATTENTION = auto()   # User has shown interest
    ANOMALY = auto()          # Unusual patterns detected


@dataclass
class SalienceScore:
    """Computed salience for an artifact."""
    artifact_id: UUID
    score: float  # 0.0 to 1.0
    factors: dict[SalienceFactor, float] = field(default_factory=dict)
    computed_at: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def is_salient(self) -> bool:
        """Whether artifact meets salience threshold."""
        return self.score >= 0.5
    
    @property
    def primary_factor(self) -> Optional[SalienceFactor]:
        """The factor contributing most to salience."""
        if not self.factors:
            return None
        return max(self.factors, key=self.factors.get)


class SalienceEngine:
    """
    Computes and tracks what matters.
    
    Salience is subjective and context-dependent.
    The engine provides rankings, not absolute truth.
    """
    
    def __init__(self):
        self._scores: dict[UUID, SalienceScore] = {}
        self._weights: dict[SalienceFactor, float] = {
            SalienceFactor.RECENCY: 0.2,
            SalienceFactor.FREQUENCY: 0.15,
            SalienceFactor.CENTRALITY: 0.2,
            SalienceFactor.VOLATILITY: 0.1,
            SalienceFactor.SIZE: 0.05,
            SalienceFactor.CONFIDENCE: 0.15,
            SalienceFactor.USER_ATTENTION: 0.1,
            SalienceFactor.ANOMALY: 0.05,
        }
    
    def compute(
        self,
        artifact_id: UUID,
        factors: dict[SalienceFactor, float],
    ) -> SalienceScore:
        """Compute salience score from factors."""
        weighted_sum = sum(
            factors.get(factor, 0.0) * weight
            for factor, weight in self._weights.items()
        )
        
        score = SalienceScore(
            artifact_id=artifact_id,
            score=min(1.0, weighted_sum),
            factors=factors,
        )
        
        self._scores[artifact_id] = score
        return score
    
    def get_score(self, artifact_id: UUID) -> Optional[SalienceScore]:
        """Get cached salience score."""
        return self._scores.get(artifact_id)
    
    def top_salient(self, n: int = 10) -> list[SalienceScore]:
        """Get top N most salient artifacts."""
        return sorted(
            self._scores.values(),
            key=lambda s: s.score,
            reverse=True,
        )[:n]
    
    def adjust_weight(self, factor: SalienceFactor, weight: float) -> None:
        """Adjust weight for a salience factor."""
        self._weights[factor] = max(0.0, min(1.0, weight))
