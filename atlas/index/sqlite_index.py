"""
Atlas SQLite Index

Fast lookup without changing the ledger truth model.
Disposable and rebuildable from snapshots.
"""

import sqlite3
from pathlib import Path
from typing import Optional


class SQLiteIndex:
    """
    SQLite-based index for fast artifact lookups.

    Stores:
    - locator -> artifact_id
    - content_hash -> artifact_id(s)
    - structure_hash -> artifact_id(s)
    - graph edges with confidence and status

    Rules:
    - Never authoritative
    - Rebuildable from snapshots
    - Uses sqlite3 only (no external deps)
    """

    def __init__(self, db_path: str = "atlas/index/atlas.db"):
        """
        Initialize SQLite index.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def initialize_schema(self) -> None:
        """Create database tables if they don't exist."""
        conn = self.connect()
        cursor = conn.cursor()

        # Artifacts table (locator -> artifact_id)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS artifacts (
                artifact_id TEXT PRIMARY KEY,
                locator TEXT,
                content_hash TEXT,
                structure_hash TEXT,
                last_seen_at REAL,
                confidence REAL
            )
        """)

        # Locator index
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_locator
            ON artifacts(locator)
        """)

        # Hash indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_content_hash
            ON artifacts(content_hash)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_structure_hash
            ON artifacts(structure_hash)
        """)

        # Relations table (graph edges)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                confidence REAL,
                status TEXT DEFAULT 'active',
                event_id TEXT,
                UNIQUE(source_id, target_id, relation_type)
            )
        """)

        # Relation indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_rel_source
            ON relations(source_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_rel_target
            ON relations(target_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_rel_type
            ON relations(relation_type)
        """)

        # Tags table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                artifact_id TEXT NOT NULL,
                tag TEXT NOT NULL,
                confidence REAL,
                event_id TEXT,
                UNIQUE(artifact_id, tag)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tags_artifact
            ON tags(artifact_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tags_tag
            ON tags(tag)
        """)

        conn.commit()

    def clear(self) -> None:
        """Clear all data from index."""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM artifacts")
        cursor.execute("DELETE FROM relations")
        cursor.execute("DELETE FROM tags")
        conn.commit()

    def upsert_artifact(
        self,
        artifact_id: str,
        locator: Optional[str] = None,
        content_hash: Optional[str] = None,
        structure_hash: Optional[str] = None,
        last_seen_at: Optional[float] = None,
        confidence: Optional[float] = None,
    ) -> None:
        """Insert or update artifact record."""
        conn = self.connect()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO artifacts
                (artifact_id, locator, content_hash, structure_hash,
                 last_seen_at, confidence)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(artifact_id) DO UPDATE SET
                locator = COALESCE(excluded.locator, artifacts.locator),
                content_hash = COALESCE(excluded.content_hash,
                                        artifacts.content_hash),
                structure_hash = COALESCE(excluded.structure_hash,
                                          artifacts.structure_hash),
                last_seen_at = COALESCE(excluded.last_seen_at,
                                        artifacts.last_seen_at),
                confidence = COALESCE(excluded.confidence,
                                      artifacts.confidence)
        """, (artifact_id, locator, content_hash, structure_hash,
              last_seen_at, confidence))

        conn.commit()

    def upsert_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        confidence: Optional[float] = None,
        status: str = "active",
        event_id: Optional[str] = None,
    ) -> None:
        """Insert or update relation record."""
        conn = self.connect()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO relations
                (source_id, target_id, relation_type, confidence,
                 status, event_id)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id, target_id, relation_type) DO UPDATE SET
                confidence = excluded.confidence,
                status = excluded.status,
                event_id = excluded.event_id
        """, (source_id, target_id, relation_type, confidence,
              status, event_id))

        conn.commit()

    def upsert_tag(
        self,
        artifact_id: str,
        tag: str,
        confidence: Optional[float] = None,
        event_id: Optional[str] = None,
    ) -> None:
        """Insert or update tag record."""
        conn = self.connect()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO tags (artifact_id, tag, confidence, event_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(artifact_id, tag) DO UPDATE SET
                confidence = excluded.confidence,
                event_id = excluded.event_id
        """, (artifact_id, tag, confidence, event_id))

        conn.commit()

    # Query methods

    def find_by_locator(self, locator: str) -> Optional[str]:
        """
        Find artifact_id by locator.

        Args:
            locator: File path or URL

        Returns:
            artifact_id if found, None otherwise
        """
        conn = self.connect()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT artifact_id FROM artifacts WHERE locator = ?",
            (locator,)
        )
        row = cursor.fetchone()

        return row["artifact_id"] if row else None

    def find_by_hash(self, hash_value: str) -> list[str]:
        """
        Find artifact_ids by content or structure hash.

        Args:
            hash_value: Hash to search for

        Returns:
            List of matching artifact_ids
        """
        conn = self.connect()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT artifact_id FROM artifacts
            WHERE content_hash = ? OR structure_hash = ?
        """, (hash_value, hash_value))

        return [row["artifact_id"] for row in cursor.fetchall()]

    def neighbors(
        self,
        artifact_id: str,
        direction: str = "out",
        type_filter: Optional[str] = None,
    ) -> list[dict]:
        """
        Find related artifacts.

        Args:
            artifact_id: Source artifact
            direction: "out" (outgoing), "in" (incoming), or "both"
            type_filter: Optional relation type to filter by

        Returns:
            List of relation dicts with target/source, type, confidence
        """
        conn = self.connect()
        cursor = conn.cursor()
        results = []

        if direction in ("out", "both"):
            if type_filter:
                cursor.execute("""
                    SELECT target_id, relation_type, confidence, status
                    FROM relations
                    WHERE source_id = ? AND relation_type = ?
                """, (artifact_id, type_filter))
            else:
                cursor.execute("""
                    SELECT target_id, relation_type, confidence, status
                    FROM relations
                    WHERE source_id = ?
                """, (artifact_id,))

            for row in cursor.fetchall():
                results.append({
                    "direction": "out",
                    "artifact_id": row["target_id"],
                    "relation_type": row["relation_type"],
                    "confidence": row["confidence"],
                    "status": row["status"],
                })

        if direction in ("in", "both"):
            if type_filter:
                cursor.execute("""
                    SELECT source_id, relation_type, confidence, status
                    FROM relations
                    WHERE target_id = ? AND relation_type = ?
                """, (artifact_id, type_filter))
            else:
                cursor.execute("""
                    SELECT source_id, relation_type, confidence, status
                    FROM relations
                    WHERE target_id = ?
                """, (artifact_id,))

            for row in cursor.fetchall():
                results.append({
                    "direction": "in",
                    "artifact_id": row["source_id"],
                    "relation_type": row["relation_type"],
                    "confidence": row["confidence"],
                    "status": row["status"],
                })

        return results

    def find_by_tag(self, tag: str) -> list[str]:
        """Find artifact_ids with given tag."""
        conn = self.connect()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT artifact_id FROM tags WHERE tag = ?",
            (tag,)
        )

        return [row["artifact_id"] for row in cursor.fetchall()]

    def get_artifact(self, artifact_id: str) -> Optional[dict]:
        """Get full artifact record."""
        conn = self.connect()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM artifacts WHERE artifact_id = ?",
            (artifact_id,)
        )
        row = cursor.fetchone()

        if not row:
            return None

        return dict(row)

    def get_tags(self, artifact_id: str) -> list[str]:
        """Get all tags for artifact."""
        conn = self.connect()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT tag FROM tags WHERE artifact_id = ?",
            (artifact_id,)
        )

        return [row["tag"] for row in cursor.fetchall()]

    def stats(self) -> dict:
        """Get index statistics."""
        conn = self.connect()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as cnt FROM artifacts")
        artifacts = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) as cnt FROM relations")
        relations = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) as cnt FROM tags")
        tags = cursor.fetchone()["cnt"]

        return {
            "artifacts": artifacts,
            "relations": relations,
            "tags": tags,
        }
