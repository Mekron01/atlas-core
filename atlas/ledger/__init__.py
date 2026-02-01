"""
Atlas Ledger - Append-Only Event Log

The ledger is the source of truth.
Events are never deleted or modified.
Everything else is rebuildable from the ledger.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional
from uuid import UUID

from .events import Event, EventMetadata, EventType


class Ledger:
    """
    Append-only event log backed by SQLite.
    
    Guarantees:
    - Events are never deleted
    - Events are never modified
    - Order is preserved
    - Crashes do not corrupt history
    """
    
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self._ensure_schema()
    
    def _ensure_schema(self) -> None:
        """Create tables if they don't exist."""
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS events (
                    sequence_number INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT UNIQUE NOT NULL,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    session_id TEXT,
                    correlation_id TEXT,
                    payload TEXT NOT NULL,
                    artifact_refs TEXT NOT NULL,
                    event_refs TEXT NOT NULL
                );
                
                CREATE INDEX IF NOT EXISTS idx_events_timestamp 
                    ON events(timestamp);
                CREATE INDEX IF NOT EXISTS idx_events_type 
                    ON events(event_type);
                CREATE INDEX IF NOT EXISTS idx_events_session 
                    ON events(session_id);
                CREATE INDEX IF NOT EXISTS idx_events_correlation 
                    ON events(correlation_id);
                
                -- Artifact reference lookup table
                CREATE TABLE IF NOT EXISTS event_artifact_refs (
                    event_id TEXT NOT NULL,
                    artifact_id TEXT NOT NULL,
                    PRIMARY KEY (event_id, artifact_id)
                );
                
                CREATE INDEX IF NOT EXISTS idx_artifact_refs 
                    ON event_artifact_refs(artifact_id);
            """)
    
    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Context manager for database connections."""
        conn = sqlite3.connect(
            self.db_path,
            isolation_level="IMMEDIATE",
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def append(self, event: Event) -> int:
        """
        Append an event to the ledger.
        
        Returns the sequence number assigned to the event.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO events (
                    event_id, timestamp, event_type, source,
                    session_id, correlation_id, payload,
                    artifact_refs, event_refs
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(event.metadata.event_id),
                    event.metadata.timestamp.isoformat(),
                    event.metadata.event_type.name,
                    event.metadata.source,
                    str(event.metadata.session_id)
                        if event.metadata.session_id else None,
                    str(event.metadata.correlation_id)
                        if event.metadata.correlation_id else None,
                    json.dumps(event.payload),
                    json.dumps([str(ref) for ref in event.artifact_refs]),
                    json.dumps([str(ref) for ref in event.event_refs]),
                ),
            )
            sequence_number = cursor.lastrowid
            
            # Index artifact references for fast lookup
            for artifact_id in event.artifact_refs:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO event_artifact_refs 
                        (event_id, artifact_id)
                    VALUES (?, ?)
                    """,
                    (str(event.metadata.event_id), str(artifact_id)),
                )
            
            return sequence_number
    
    def _row_to_event(self, row: sqlite3.Row) -> Event:
        """Convert a database row to an Event."""
        return Event(
            metadata=EventMetadata(
                event_id=UUID(row["event_id"]),
                timestamp=datetime.fromisoformat(row["timestamp"]),
                event_type=EventType[row["event_type"]],
                source=row["source"],
                session_id=UUID(row["session_id"])
                    if row["session_id"] else None,
                correlation_id=UUID(row["correlation_id"])
                    if row["correlation_id"] else None,
            ),
            payload=json.loads(row["payload"]),
            artifact_refs=tuple(
                UUID(ref) for ref in json.loads(row["artifact_refs"])
            ),
            event_refs=tuple(
                UUID(ref) for ref in json.loads(row["event_refs"])
            ),
        )
    
    def get_event(self, event_id: UUID) -> Optional[Event]:
        """Retrieve a single event by ID."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM events WHERE event_id = ?",
                (str(event_id),),
            ).fetchone()
            
            if row is None:
                return None
            return self._row_to_event(row)
    
    def iter_events(
        self,
        *,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        event_types: Optional[set[EventType]] = None,
        artifact_id: Optional[UUID] = None,
        session_id: Optional[UUID] = None,
    ) -> Iterator[Event]:
        """
        Iterate over events matching the given criteria.
        
        Events are yielded in chronological order (by sequence number).
        """
        query = "SELECT e.* FROM events e"
        params: list = []
        conditions: list[str] = []
        
        if artifact_id is not None:
            query += """
                JOIN event_artifact_refs ear 
                ON e.event_id = ear.event_id
            """
            conditions.append("ear.artifact_id = ?")
            params.append(str(artifact_id))
        
        if since is not None:
            conditions.append("e.timestamp >= ?")
            params.append(since.isoformat())
        
        if until is not None:
            conditions.append("e.timestamp <= ?")
            params.append(until.isoformat())
        
        if event_types is not None:
            placeholders = ",".join("?" for _ in event_types)
            conditions.append(f"e.event_type IN ({placeholders})")
            params.extend(et.name for et in event_types)
        
        if session_id is not None:
            conditions.append("e.session_id = ?")
            params.append(str(session_id))
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY e.sequence_number ASC"
        
        with self._connect() as conn:
            cursor = conn.execute(query, params)
            for row in cursor:
                yield self._row_to_event(row)
    
    def events_for_artifact(self, artifact_id: UUID) -> Iterator[Event]:
        """Get all events referencing an artifact."""
        return self.iter_events(artifact_id=artifact_id)
    
    def count(
        self,
        *,
        event_type: Optional[EventType] = None,
    ) -> int:
        """Count events in the ledger."""
        with self._connect() as conn:
            if event_type:
                row = conn.execute(
                    "SELECT COUNT(*) FROM events WHERE event_type = ?",
                    (event_type.name,),
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM events").fetchone()
            return row[0]
    
    def latest_sequence(self) -> int:
        """Get the latest sequence number."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MAX(sequence_number) FROM events"
            ).fetchone()
            return row[0] or 0


class InMemoryLedger:
    """
    In-memory ledger for testing.
    Same interface as Ledger but no persistence.
    """
    
    def __init__(self):
        self._events: list[Event] = []
        self._by_id: dict[UUID, Event] = {}
        self._by_artifact: dict[UUID, list[Event]] = {}
    
    def append(self, event: Event) -> int:
        """Append an event, return sequence number."""
        sequence = len(self._events) + 1
        self._events.append(event)
        self._by_id[event.event_id] = event
        
        for artifact_id in event.artifact_refs:
            if artifact_id not in self._by_artifact:
                self._by_artifact[artifact_id] = []
            self._by_artifact[artifact_id].append(event)
        
        return sequence
    
    def get_event(self, event_id: UUID) -> Optional[Event]:
        """Retrieve a single event by ID."""
        return self._by_id.get(event_id)
    
    def iter_events(
        self,
        *,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        event_types: Optional[set[EventType]] = None,
        artifact_id: Optional[UUID] = None,
        session_id: Optional[UUID] = None,
    ) -> Iterator[Event]:
        """Iterate over events matching criteria."""
        events = self._events
        
        if artifact_id is not None:
            events = self._by_artifact.get(artifact_id, [])
        
        for event in events:
            if since and event.timestamp < since:
                continue
            if until and event.timestamp > until:
                continue
            if event_types and event.event_type not in event_types:
                continue
            if session_id and event.metadata.session_id != session_id:
                continue
            yield event
    
    def events_for_artifact(self, artifact_id: UUID) -> Iterator[Event]:
        """Get all events referencing an artifact."""
        return iter(self._by_artifact.get(artifact_id, []))
    
    def count(self, *, event_type: Optional[EventType] = None) -> int:
        """Count events."""
        if event_type:
            return sum(
                1 for e in self._events if e.event_type == event_type
            )
        return len(self._events)
    
    def latest_sequence(self) -> int:
        """Get latest sequence number."""
        return len(self._events)
