"""
Atlas Janitor

Analyzes system state and recommends maintenance actions.
Never deletes anything by default - only recommends.
"""

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class MaintenanceRecommendation:
    """A maintenance action recommendation."""
    recommendation_id: str
    action_type: str  # "archive" or "prune_cache"
    artifact_id: Optional[str]
    path: Optional[str]
    reason: str
    staleness_score: float  # 0.0 (fresh) to 1.0 (very stale)
    priority: str  # "low", "medium", "high"


@dataclass
class StalenessAnalysis:
    """Analysis of artifact staleness."""
    artifact_id: str
    last_seen_at: Optional[float]
    age_hours: float
    volatility: float
    freshness_score: float  # 0.0 (stale) to 1.0 (fresh)
    staleness_score: float  # inverse of freshness
    recommendation: Optional[str]


class Janitor:
    """
    Analyzes snapshots and recommends maintenance.

    Rules:
    - Never deletes anything by default
    - Only produces recommendations
    - Emits events documenting analysis
    """

    def __init__(self, writer=None):
        """
        Initialize Janitor.

        Args:
            writer: Optional EventWriter for emitting events
        """
        self.writer = writer
        self.module_name = "Janitor"

    def _make_event_id(self) -> str:
        """Generate unique event ID."""
        return f"janitor-{uuid.uuid4().hex[:16]}"

    def analyze_staleness(
        self,
        artifact: dict,
        now: Optional[float] = None,
    ) -> StalenessAnalysis:
        """
        Analyze staleness of a single artifact.

        Args:
            artifact: Artifact state dict
            now: Current timestamp (default: time.time())

        Returns:
            StalenessAnalysis with freshness metrics
        """
        now = now or time.time()

        artifact_id = artifact.get("artifact_id", "unknown")
        last_seen_at = artifact.get("last_seen_at")

        # Calculate age
        if last_seen_at:
            age_hours = (now - last_seen_at) / 3600
        else:
            age_hours = float("inf")

        # Get volatility hint if present
        extraction = artifact.get("extraction") or {}
        volatility = extraction.get("volatility", 0.5)

        # Calculate freshness score
        # Based on age relative to expected freshness window
        # High volatility = shorter freshness window
        half_life_hours = 720 - (volatility * 696)  # 24h to 720h

        if age_hours == float("inf"):
            freshness_score = 0.0
        else:
            freshness_score = 0.5 ** (age_hours / half_life_hours)

        staleness_score = 1.0 - freshness_score

        # Determine recommendation
        recommendation = None
        if staleness_score > 0.9:
            recommendation = "archive"
        elif staleness_score > 0.7:
            recommendation = "review"

        return StalenessAnalysis(
            artifact_id=artifact_id,
            last_seen_at=last_seen_at,
            age_hours=age_hours,
            volatility=volatility,
            freshness_score=freshness_score,
            staleness_score=staleness_score,
            recommendation=recommendation,
        )

    def analyze_snapshot(
        self,
        artifacts: dict[str, dict],
        archive_threshold: float = 0.9,
        review_threshold: float = 0.7,
        session_id: Optional[str] = None,
    ) -> list[MaintenanceRecommendation]:
        """
        Analyze all artifacts in a snapshot.

        Args:
            artifacts: Dict mapping artifact_id to state
            archive_threshold: Staleness above this recommends archive
            review_threshold: Staleness above this recommends review
            session_id: Optional session ID

        Returns:
            List of maintenance recommendations
        """
        now = time.time()
        recommendations = []

        for artifact_id, artifact in artifacts.items():
            analysis = self.analyze_staleness(artifact, now)

            if analysis.staleness_score >= archive_threshold:
                rec = MaintenanceRecommendation(
                    recommendation_id=self._make_event_id(),
                    action_type="archive",
                    artifact_id=artifact_id,
                    path=artifact.get("locator"),
                    reason=(
                        f"Staleness {analysis.staleness_score:.0%}, "
                        f"last seen {analysis.age_hours:.1f}h ago"
                    ),
                    staleness_score=analysis.staleness_score,
                    priority="high" if analysis.staleness_score > 0.95 else "medium",
                )
                recommendations.append(rec)

                # Emit event
                self._emit_archive_recommended(
                    artifact_id=artifact_id,
                    staleness_score=analysis.staleness_score,
                    age_hours=analysis.age_hours,
                    session_id=session_id,
                )

        return recommendations

    def analyze_cache(
        self,
        cache_dir: str,
        max_age_days: int = 30,
        session_id: Optional[str] = None,
    ) -> list[MaintenanceRecommendation]:
        """
        Analyze cache directory for pruning candidates.

        Args:
            cache_dir: Path to cache directory
            max_age_days: Files older than this are candidates
            session_id: Optional session ID

        Returns:
            List of prune recommendations
        """
        cache_path = Path(cache_dir)
        if not cache_path.exists():
            return []

        now = time.time()
        max_age_seconds = max_age_days * 86400
        recommendations = []

        for item in cache_path.rglob("*"):
            if not item.is_file():
                continue

            # Skip archive directory
            if "archive" in str(item):
                continue

            try:
                mtime = item.stat().st_mtime
                age_seconds = now - mtime

                if age_seconds > max_age_seconds:
                    age_days = age_seconds / 86400
                    staleness = min(1.0, age_seconds / (max_age_seconds * 2))

                    rec = MaintenanceRecommendation(
                        recommendation_id=self._make_event_id(),
                        action_type="prune_cache",
                        artifact_id=None,
                        path=str(item),
                        reason=f"Cache file {age_days:.0f} days old",
                        staleness_score=staleness,
                        priority="low",
                    )
                    recommendations.append(rec)

                    self._emit_prune_cache_recommended(
                        path=str(item),
                        age_days=age_days,
                        session_id=session_id,
                    )

            except Exception:
                continue

        return recommendations

    def run(
        self,
        artifacts: dict[str, dict],
        cache_dir: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> list[MaintenanceRecommendation]:
        """
        Run full maintenance analysis.

        Args:
            artifacts: Snapshot artifacts dict
            cache_dir: Optional cache directory to analyze
            session_id: Optional session ID

        Returns:
            Combined list of all recommendations
        """
        recommendations = []

        # Analyze snapshots
        snapshot_recs = self.analyze_snapshot(
            artifacts,
            session_id=session_id,
        )
        recommendations.extend(snapshot_recs)

        # Analyze cache if provided
        if cache_dir:
            cache_recs = self.analyze_cache(
                cache_dir,
                session_id=session_id,
            )
            recommendations.extend(cache_recs)

        # Sort by staleness
        recommendations.sort(
            key=lambda r: r.staleness_score,
            reverse=True,
        )

        return recommendations

    def _emit_archive_recommended(
        self,
        artifact_id: str,
        staleness_score: float,
        age_hours: float,
        session_id: Optional[str] = None,
    ) -> str:
        """Emit ARCHIVE_RECOMMENDED event."""
        if not self.writer:
            return ""

        event_id = self._make_event_id()

        event = {
            "event_id": event_id,
            "event_type": "ARCHIVE_RECOMMENDED",
            "ts": time.time(),
            "actor": {"module": self.module_name},
            "artifact_id": artifact_id,
            "confidence": staleness_score,
            "evidence_refs": [],
            "payload": {
                "staleness_score": staleness_score,
                "age_hours": age_hours,
                "action": "archive",
            },
        }

        if session_id:
            event["session_id"] = session_id

        self.writer.append(event)
        return event_id

    def _emit_prune_cache_recommended(
        self,
        path: str,
        age_days: float,
        session_id: Optional[str] = None,
    ) -> str:
        """Emit PRUNE_CACHE_RECOMMENDED event."""
        if not self.writer:
            return ""

        event_id = self._make_event_id()

        event = {
            "event_id": event_id,
            "event_type": "PRUNE_CACHE_RECOMMENDED",
            "ts": time.time(),
            "actor": {"module": self.module_name},
            "artifact_id": None,
            "confidence": 0.9,
            "evidence_refs": [],
            "payload": {
                "path": path,
                "age_days": age_days,
                "action": "prune_cache",
            },
        }

        if session_id:
            event["session_id"] = session_id

        self.writer.append(event)
        return event_id

    def format_report(
        self,
        recommendations: list[MaintenanceRecommendation],
    ) -> str:
        """Format recommendations as text report."""
        if not recommendations:
            return "No maintenance recommendations."

        lines = [
            "MAINTENANCE RECOMMENDATIONS",
            "=" * 40,
            "",
        ]

        archive_recs = [r for r in recommendations if r.action_type == "archive"]
        cache_recs = [r for r in recommendations if r.action_type == "prune_cache"]

        if archive_recs:
            lines.append(f"Archive Candidates ({len(archive_recs)}):")
            for rec in archive_recs[:10]:
                lines.append(
                    f"  [{rec.priority.upper()}] {rec.artifact_id[:16]}... "
                    f"- {rec.reason}"
                )
            if len(archive_recs) > 10:
                lines.append(f"  ... and {len(archive_recs) - 10} more")
            lines.append("")

        if cache_recs:
            lines.append(f"Cache Prune Candidates ({len(cache_recs)}):")
            for rec in cache_recs[:10]:
                lines.append(f"  {rec.path} - {rec.reason}")
            if len(cache_recs) > 10:
                lines.append(f"  ... and {len(cache_recs) - 10} more")
            lines.append("")

        return "\n".join(lines)
