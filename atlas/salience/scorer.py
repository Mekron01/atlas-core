"""
Atlas Salience Scorer

Scores artifacts by what matters, not what is true.
Salience is about attention, not truth.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class SalienceScore:
    """
    Complete salience score with breakdown.

    Total score combines multiple factors.
    Each factor is independently explainable.
    """
    total: float
    novelty: float = 0.0
    impact: float = 0.0
    risk: float = 0.0
    uncertainty: float = 0.0
    recurrence: float = 0.0
    triggering_event_ids: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self):
        if not 0.0 <= self.total <= 1.0:
            object.__setattr__(
                self, "total", max(0.0, min(1.0, self.total))
            )


class SalienceScorer:
    """
    Scores artifacts for salience.

    Factors:
    - novelty: How new/unseen is this?
    - impact: How many things depend on it?
    - risk: Are there risk-related tags?
    - uncertainty: Low confidence or conflicts?
    - recurrence: How often does it appear?

    Rules:
    - Salience never mutates truth
    - Silent by default (no alerts without explanation)
    - All scores are between 0.0 and 1.0
    """

    # Tags that indicate risk
    RISK_TAGS = frozenset([
        "security",
        "auth",
        "authentication",
        "password",
        "secret",
        "credential",
        "api-key",
        "private",
        "sensitive",
        "deprecated",
        "experimental",
        "unstable",
        "todo",
        "fixme",
        "hack",
        "bug",
    ])

    def __init__(
        self,
        novelty_weight: float = 0.25,
        impact_weight: float = 0.25,
        risk_weight: float = 0.20,
        uncertainty_weight: float = 0.15,
        recurrence_weight: float = 0.15,
    ):
        """
        Initialize scorer with factor weights.

        Weights should sum to 1.0.
        """
        self.weights = {
            "novelty": novelty_weight,
            "impact": impact_weight,
            "risk": risk_weight,
            "uncertainty": uncertainty_weight,
            "recurrence": recurrence_weight,
        }

    def score_novelty(
        self,
        artifact_id: str,
        first_seen_ts: Optional[float],
        total_artifacts: int,
        seen_count: int = 1,
    ) -> float:
        """
        Score novelty based on how new the artifact is.

        Args:
            artifact_id: Artifact being scored
            first_seen_ts: When first observed (None = brand new)
            total_artifacts: Total artifacts in system
            seen_count: How many times seen before

        Returns:
            Novelty score 0.0 to 1.0
        """
        if first_seen_ts is None:
            return 1.0  # Brand new = maximum novelty

        if seen_count <= 1:
            return 0.9  # First occurrence

        # Novelty decays with exposure
        decay = 0.9 ** (seen_count - 1)
        return max(0.1, decay)

    def score_impact(
        self,
        artifact_id: str,
        dependent_count: int,
        dependency_count: int,
        total_artifacts: int,
    ) -> float:
        """
        Score impact based on dependency relationships.

        Artifacts with many dependents are more impactful.

        Args:
            artifact_id: Artifact being scored
            dependent_count: How many things depend on this
            dependency_count: How many things this depends on
            total_artifacts: Total artifacts in system

        Returns:
            Impact score 0.0 to 1.0
        """
        if total_artifacts == 0:
            return 0.0

        # Dependents matter more than dependencies
        dependent_ratio = dependent_count / max(1, total_artifacts)
        dependency_ratio = dependency_count / max(1, total_artifacts)

        # Weighted combination
        impact = (dependent_ratio * 0.7) + (dependency_ratio * 0.3)

        # Normalize to 0-1 range with soft cap
        return min(1.0, impact * 5)

    def score_risk(
        self,
        artifact_id: str,
        tags: list[str],
        path: Optional[str] = None,
    ) -> float:
        """
        Score risk based on tags and path patterns.

        Args:
            artifact_id: Artifact being scored
            tags: Tags associated with artifact
            path: Optional file path

        Returns:
            Risk score 0.0 to 1.0
        """
        risk = 0.0
        risk_factors = 0

        # Tag-based risk
        tag_set = set(t.lower() for t in tags)
        risk_tag_count = len(tag_set & self.RISK_TAGS)

        if risk_tag_count > 0:
            risk += min(0.6, risk_tag_count * 0.2)
            risk_factors += risk_tag_count

        # Path-based risk
        if path:
            path_lower = path.lower()
            risky_paths = [
                "secret", "password", "credential", "auth",
                "config", "env", ".env", "key", "token",
            ]
            for risky in risky_paths:
                if risky in path_lower:
                    risk += 0.15
                    risk_factors += 1
                    break

        return min(1.0, risk)

    def score_uncertainty(
        self,
        artifact_id: str,
        confidence: Optional[float],
        conflict_count: int,
        ambiguity_count: int = 0,
    ) -> float:
        """
        Score uncertainty from low confidence and conflicts.

        Uncertain things deserve attention.

        Args:
            artifact_id: Artifact being scored
            confidence: Current confidence (None = unknown)
            conflict_count: Number of active conflicts
            ambiguity_count: Number of ambiguity flags

        Returns:
            Uncertainty score 0.0 to 1.0
        """
        uncertainty = 0.0

        # Low confidence = high uncertainty
        if confidence is None:
            uncertainty += 0.5
        elif confidence < 0.5:
            uncertainty += (0.5 - confidence)
        elif confidence < 0.75:
            uncertainty += (0.75 - confidence) * 0.5

        # Conflicts add uncertainty
        if conflict_count > 0:
            uncertainty += min(0.4, conflict_count * 0.15)

        # Ambiguity adds uncertainty
        if ambiguity_count > 0:
            uncertainty += min(0.2, ambiguity_count * 0.05)

        return min(1.0, uncertainty)

    def score_recurrence(
        self,
        artifact_id: str,
        observation_count: int,
        unique_sessions: int,
        time_span_hours: float,
    ) -> float:
        """
        Score recurrence based on observation patterns.

        Frequently recurring artifacts may be important.

        Args:
            artifact_id: Artifact being scored
            observation_count: Total observations
            unique_sessions: Distinct sessions that observed it
            time_span_hours: Time span of observations

        Returns:
            Recurrence score 0.0 to 1.0
        """
        if observation_count <= 1:
            return 0.0

        # Multiple sessions observing = more salient
        session_factor = min(1.0, unique_sessions / 5)

        # High frequency = more salient
        if time_span_hours > 0:
            freq = observation_count / time_span_hours
            freq_factor = min(1.0, freq / 10)
        else:
            freq_factor = 0.5

        return (session_factor * 0.6) + (freq_factor * 0.4)

    def compute(
        self,
        artifact_id: str,
        first_seen_ts: Optional[float] = None,
        total_artifacts: int = 1,
        seen_count: int = 1,
        dependent_count: int = 0,
        dependency_count: int = 0,
        tags: Optional[list[str]] = None,
        path: Optional[str] = None,
        confidence: Optional[float] = None,
        conflict_count: int = 0,
        ambiguity_count: int = 0,
        observation_count: int = 1,
        unique_sessions: int = 1,
        time_span_hours: float = 0.0,
        triggering_event_ids: Optional[list[str]] = None,
    ) -> SalienceScore:
        """
        Compute complete salience score.

        Args:
            artifact_id: Artifact to score
            ... (see individual score methods for param docs)

        Returns:
            SalienceScore with total and component breakdown
        """
        tags = tags or []
        triggering_event_ids = triggering_event_ids or []

        # Compute individual factors
        novelty = self.score_novelty(
            artifact_id, first_seen_ts, total_artifacts, seen_count
        )
        impact = self.score_impact(
            artifact_id, dependent_count, dependency_count, total_artifacts
        )
        risk = self.score_risk(artifact_id, tags, path)
        uncertainty = self.score_uncertainty(
            artifact_id, confidence, conflict_count, ambiguity_count
        )
        recurrence = self.score_recurrence(
            artifact_id, observation_count, unique_sessions, time_span_hours
        )

        # Weighted total
        total = (
            novelty * self.weights["novelty"]
            + impact * self.weights["impact"]
            + risk * self.weights["risk"]
            + uncertainty * self.weights["uncertainty"]
            + recurrence * self.weights["recurrence"]
        )

        return SalienceScore(
            total=total,
            novelty=novelty,
            impact=impact,
            risk=risk,
            uncertainty=uncertainty,
            recurrence=recurrence,
            triggering_event_ids=tuple(triggering_event_ids),
        )
