"""
Atlas Salience Explainer

Produces human-readable explanations for salience scores.
No alerts without explanation.
"""

from dataclasses import dataclass, field
from typing import Optional

from atlas.salience.scorer import SalienceScore


@dataclass(frozen=True)
class SalienceExplanation:
    """
    Human-readable salience explanation.

    Includes:
    - Summary sentence
    - Factor-by-factor breakdown
    - Triggering events
    - Suggested actions (optional)
    """
    artifact_id: str
    score: SalienceScore
    summary: str
    factor_explanations: tuple[str, ...] = field(default_factory=tuple)
    suggested_actions: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_high_salience(self) -> bool:
        """Whether this warrants attention."""
        return self.score.total >= 0.6

    @property
    def is_critical(self) -> bool:
        """Whether this needs immediate attention."""
        return self.score.total >= 0.8


class SalienceExplainer:
    """
    Generates explanations for salience scores.

    Rules:
    - Every score gets an explanation
    - Explanations are actionable
    - Silent by default (no alerts without cause)
    """

    def __init__(
        self,
        novelty_threshold: float = 0.7,
        impact_threshold: float = 0.5,
        risk_threshold: float = 0.4,
        uncertainty_threshold: float = 0.5,
        recurrence_threshold: float = 0.6,
    ):
        """Initialize with factor thresholds for highlighting."""
        self.thresholds = {
            "novelty": novelty_threshold,
            "impact": impact_threshold,
            "risk": risk_threshold,
            "uncertainty": uncertainty_threshold,
            "recurrence": recurrence_threshold,
        }

    def explain(
        self,
        artifact_id: str,
        score: SalienceScore,
        path: Optional[str] = None,
        tags: Optional[list[str]] = None,
        confidence: Optional[float] = None,
    ) -> SalienceExplanation:
        """
        Generate explanation for a salience score.

        Args:
            artifact_id: Artifact being explained
            score: Computed salience score
            path: Optional artifact path for context
            tags: Optional tags for context
            confidence: Optional confidence for context

        Returns:
            SalienceExplanation with full breakdown
        """
        tags = tags or []
        factor_explanations = []
        suggested_actions = []
        highlights = []

        # Explain novelty
        if score.novelty >= self.thresholds["novelty"]:
            highlights.append("new")
            factor_explanations.append(
                f"Novelty ({score.novelty:.0%}): Recently discovered artifact"
            )
            suggested_actions.append("Review new artifact for classification")

        # Explain impact
        if score.impact >= self.thresholds["impact"]:
            highlights.append("impactful")
            factor_explanations.append(
                f"Impact ({score.impact:.0%}): Many artifacts depend on this"
            )
            suggested_actions.append("Changes here may cascade widely")

        # Explain risk
        if score.risk >= self.thresholds["risk"]:
            highlights.append("risky")
            risk_tags = [t for t in tags if t.lower() in {
                "security", "auth", "password", "secret", "credential",
                "deprecated", "experimental", "todo", "fixme",
            }]
            if risk_tags:
                factor_explanations.append(
                    f"Risk ({score.risk:.0%}): "
                    f"Tagged with risk indicators: {', '.join(risk_tags)}"
                )
            else:
                factor_explanations.append(
                    f"Risk ({score.risk:.0%}): "
                    "Path or content suggests sensitive material"
                )
            suggested_actions.append("Review for security or stability concerns")

        # Explain uncertainty
        if score.uncertainty >= self.thresholds["uncertainty"]:
            highlights.append("uncertain")
            if confidence is not None and confidence < 0.5:
                factor_explanations.append(
                    f"Uncertainty ({score.uncertainty:.0%}): "
                    f"Low confidence ({confidence:.0%})"
                )
            else:
                factor_explanations.append(
                    f"Uncertainty ({score.uncertainty:.0%}): "
                    "Conflicts or ambiguity detected"
                )
            suggested_actions.append("Gather more evidence to resolve uncertainty")

        # Explain recurrence
        if score.recurrence >= self.thresholds["recurrence"]:
            highlights.append("recurring")
            factor_explanations.append(
                f"Recurrence ({score.recurrence:.0%}): "
                "Frequently observed across sessions"
            )
            suggested_actions.append("Consider adding to watch list")

        # Build summary
        if not highlights:
            summary = f"Low salience ({score.total:.0%}): No notable factors"
        elif score.total >= 0.8:
            summary = (
                f"CRITICAL salience ({score.total:.0%}): "
                f"Artifact is {', '.join(highlights)}"
            )
        elif score.total >= 0.6:
            summary = (
                f"High salience ({score.total:.0%}): "
                f"Artifact is {', '.join(highlights)}"
            )
        else:
            summary = (
                f"Moderate salience ({score.total:.0%}): "
                f"Artifact is {', '.join(highlights)}"
            )

        # Add path context if available
        if path:
            summary = f"{summary} [{path}]"

        return SalienceExplanation(
            artifact_id=artifact_id,
            score=score,
            summary=summary,
            factor_explanations=tuple(factor_explanations),
            suggested_actions=tuple(suggested_actions),
        )

    def explain_batch(
        self,
        scores: list[tuple[str, SalienceScore]],
        min_salience: float = 0.0,
    ) -> list[SalienceExplanation]:
        """
        Explain multiple scores, filtering by minimum salience.

        Args:
            scores: List of (artifact_id, score) tuples
            min_salience: Minimum total score to include

        Returns:
            List of explanations, sorted by salience descending
        """
        explanations = []

        for artifact_id, score in scores:
            if score.total >= min_salience:
                explanation = self.explain(artifact_id, score)
                explanations.append(explanation)

        # Sort by total salience descending
        explanations.sort(key=lambda e: e.score.total, reverse=True)

        return explanations

    def format_report(
        self,
        explanations: list[SalienceExplanation],
        max_items: int = 10,
    ) -> str:
        """
        Format explanations as a text report.

        Args:
            explanations: List of explanations
            max_items: Maximum items to include

        Returns:
            Formatted text report
        """
        if not explanations:
            return "No salient artifacts to report."

        lines = ["SALIENCE REPORT", "=" * 40, ""]

        for i, exp in enumerate(explanations[:max_items]):
            lines.append(f"{i+1}. {exp.summary}")

            for factor in exp.factor_explanations:
                lines.append(f"   - {factor}")

            if exp.suggested_actions:
                lines.append("   Actions:")
                for action in exp.suggested_actions:
                    lines.append(f"     • {action}")

            lines.append("")

        if len(explanations) > max_items:
            lines.append(
                f"... and {len(explanations) - max_items} more artifacts"
            )

        return "\n".join(lines)
