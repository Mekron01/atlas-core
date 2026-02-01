"""
Atlas Index Builder

Rebuilds indexes from snapshots.
Deterministic and safe (temp + replace).
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Optional

from atlas.index.sqlite_index import SQLiteIndex


class IndexBuilder:
    """
    Rebuilds SQLite indexes from snapshot files.

    Rules:
    - Does not mutate ledger or snapshots
    - Creates/overwrites sqlite files safely (temp + replace)
    - Deterministic rebuild
    """

    def __init__(
        self,
        index_dir: str = "atlas/index",
        state_dir: str = "atlas/state",
    ):
        """
        Initialize index builder.

        Args:
            index_dir: Directory for index files
            state_dir: Directory containing snapshots
        """
        self.index_dir = Path(index_dir)
        self.state_dir = Path(state_dir)

    def rebuild(
        self,
        artifacts_snapshot: Optional[str] = None,
        relations_snapshot: Optional[str] = None,
    ) -> dict:
        """
        Rebuild all indexes from snapshots.

        Args:
            artifacts_snapshot: Path to artifacts snapshot (default: auto)
            relations_snapshot: Path to relations snapshot (default: auto)

        Returns:
            Statistics dict with counts
        """
        # Find snapshot files
        if artifacts_snapshot is None:
            artifacts_snapshot = self.state_dir / "artifacts.snapshot.jsonl"
        else:
            artifacts_snapshot = Path(artifacts_snapshot)

        if relations_snapshot is None:
            relations_snapshot = self.state_dir / "relations.snapshot.jsonl"
        else:
            relations_snapshot = Path(relations_snapshot)

        # Create temp database
        self.index_dir.mkdir(parents=True, exist_ok=True)
        final_path = self.index_dir / "atlas.db"

        fd, tmp_path = tempfile.mkstemp(
            suffix=".db",
            prefix="atlas_index_",
            dir=str(self.index_dir),
        )
        os.close(fd)

        try:
            # Build index in temp file
            index = SQLiteIndex(db_path=tmp_path)
            index.initialize_schema()

            stats = {
                "artifacts": 0,
                "relations": 0,
                "tags": 0,
            }

            # Load artifacts
            if artifacts_snapshot.exists():
                stats["artifacts"] = self._load_artifacts(
                    index, artifacts_snapshot
                )

            # Load relations
            if relations_snapshot.exists():
                stats["relations"] = self._load_relations(
                    index, relations_snapshot
                )

            # Close before replacing
            index.close()

            # Atomic replace
            Path(tmp_path).replace(final_path)

        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        return stats

    def _load_artifacts(
        self,
        index: SQLiteIndex,
        snapshot_path: Path,
    ) -> int:
        """Load artifacts from snapshot into index."""
        count = 0

        with open(snapshot_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    artifact = json.loads(line)
                except json.JSONDecodeError:
                    continue

                artifact_id = artifact.get("artifact_id")
                if not artifact_id:
                    continue

                # Upsert artifact
                index.upsert_artifact(
                    artifact_id=artifact_id,
                    locator=artifact.get("locator"),
                    content_hash=artifact.get("fingerprint"),
                    structure_hash=artifact.get("structure_hash"),
                    last_seen_at=artifact.get("last_seen_at"),
                    confidence=artifact.get("confidence"),
                )

                # Load tags if present
                tags = artifact.get("tags", [])
                for tag in tags:
                    if isinstance(tag, dict):
                        index.upsert_tag(
                            artifact_id=artifact_id,
                            tag=tag.get("tag", ""),
                            confidence=tag.get("confidence"),
                            event_id=tag.get("event_id"),
                        )
                    elif isinstance(tag, str):
                        index.upsert_tag(
                            artifact_id=artifact_id,
                            tag=tag,
                        )

                count += 1

        return count

    def _load_relations(
        self,
        index: SQLiteIndex,
        snapshot_path: Path,
    ) -> int:
        """Load relations from snapshot into index."""
        count = 0

        with open(snapshot_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    relation = json.loads(line)
                except json.JSONDecodeError:
                    continue

                source_id = relation.get("source_id")
                target_id = relation.get("target_id")
                rel_type = relation.get("relation_type")

                if not source_id or not target_id or not rel_type:
                    continue

                index.upsert_relation(
                    source_id=source_id,
                    target_id=target_id,
                    relation_type=rel_type,
                    confidence=relation.get("confidence"),
                    status=relation.get("status", "active"),
                    event_id=relation.get("event_id"),
                )

                count += 1

        return count

    def rebuild_from_projected(
        self,
        artifacts: dict[str, dict],
        relations: dict[str, list[dict]],
        tags: dict[str, list[dict]],
    ) -> dict:
        """
        Rebuild index from already-projected data.

        Args:
            artifacts: Dict mapping artifact_id to state
            relations: Dict mapping source_id to relations list
            tags: Dict mapping artifact_id to tags list

        Returns:
            Statistics dict
        """
        self.index_dir.mkdir(parents=True, exist_ok=True)
        final_path = self.index_dir / "atlas.db"

        fd, tmp_path = tempfile.mkstemp(
            suffix=".db",
            prefix="atlas_index_",
            dir=str(self.index_dir),
        )
        os.close(fd)

        try:
            index = SQLiteIndex(db_path=tmp_path)
            index.initialize_schema()

            stats = {"artifacts": 0, "relations": 0, "tags": 0}

            # Load artifacts
            for artifact_id, artifact in artifacts.items():
                index.upsert_artifact(
                    artifact_id=artifact_id,
                    locator=artifact.get("locator"),
                    content_hash=artifact.get("fingerprint"),
                    structure_hash=artifact.get("structure_hash"),
                    last_seen_at=artifact.get("last_seen_at"),
                    confidence=artifact.get("confidence"),
                )
                stats["artifacts"] += 1

            # Load relations
            for source_id, rels in relations.items():
                for rel in rels:
                    index.upsert_relation(
                        source_id=source_id,
                        target_id=rel.get("target_id", ""),
                        relation_type=rel.get("relation_type", ""),
                        confidence=rel.get("confidence"),
                        event_id=rel.get("event_id"),
                    )
                    stats["relations"] += 1

            # Load tags
            for artifact_id, tag_list in tags.items():
                for tag_info in tag_list:
                    index.upsert_tag(
                        artifact_id=artifact_id,
                        tag=tag_info.get("tag", ""),
                        confidence=tag_info.get("confidence"),
                        event_id=tag_info.get("event_id"),
                    )
                    stats["tags"] += 1

            index.close()
            Path(tmp_path).replace(final_path)

        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        return stats
