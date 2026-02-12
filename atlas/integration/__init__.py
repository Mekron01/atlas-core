"""
Atlas Integration Module

Public API for external consumers.
"""

from __future__ import annotations

import json
import uuid
import time
from pathlib import Path
from typing import Any, Optional


def export_api(
    ledger_dir: str = "atlas/ledger/events",
    state_dir: str = "atlas/state",
) -> dict[str, Any]:
    """
    Export current Atlas state as a JSON-serializable dict.

    Returns a snapshot of:
    - state_id: unique identifier for this export
    - schema_version: current schema version
    - version: atlas-core version
    - artifacts: list of known artifacts (from last snapshot)
    - relations: list of known relations (from last snapshot)
    - ledger_stats: event counts and date range

    This is a read-only operation with no side effects.
    """
    from atlas import __version__, __ATLAS_SCHEMA_VERSION__
    from atlas.ledger.reader import EventReader
    from atlas.state.snapshots import read_snapshot, snapshot_path

    # Generate export ID
    state_id = f"export-{uuid.uuid4().hex[:12]}"

    # Read artifacts from snapshot
    snap_path = snapshot_path(state_dir)
    artifacts = {}
    if snap_path.exists():
        artifacts = read_snapshot(snap_path)

    # Read relations snapshot if it exists
    relations_path = snapshot_path(state_dir, name="relations")
    relations = {}
    if relations_path.exists():
        relations = read_snapshot(relations_path)

    # Ledger stats
    reader = EventReader(ledger_dir=ledger_dir)
    event_count = 0
    event_types: dict[str, int] = {}
    first_ts: Optional[float] = None
    last_ts: Optional[float] = None

    for event in reader.read_all():
        event_count += 1
        et = event.get("event_type", "UNKNOWN")
        event_types[et] = event_types.get(et, 0) + 1

        ts = event.get("ts")
        if ts is not None:
            if first_ts is None or ts < first_ts:
                first_ts = ts
            if last_ts is None or ts > last_ts:
                last_ts = ts

    return {
        "state_id": state_id,
        "schema_version": __ATLAS_SCHEMA_VERSION__,
        "version": __version__,
        "exported_at": time.time(),
        "artifacts": list(artifacts.values()),
        "artifact_count": len(artifacts),
        "relations": list(relations.values()),
        "relation_count": len(relations),
        "ledger_stats": {
            "event_count": event_count,
            "event_types": event_types,
            "first_ts": first_ts,
            "last_ts": last_ts,
        },
    }
