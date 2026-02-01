"""
Atlas CLI Runner

Command-line interface for Atlas operations.
No hidden state. Deterministic behavior. Clear logging.
"""

import argparse
import sys
import time
import uuid
from pathlib import Path


def get_ledger_dir() -> Path:
    """Get ledger directory path."""
    return Path("atlas/ledger/events")


def get_state_dir() -> Path:
    """Get state directory path."""
    return Path("atlas/state")


def cmd_scan(args) -> int:
    """
    Scan a directory and emit observation events.

    Creates a session, runs FilesystemEye, writes events.
    """
    from atlas.eyes.filesystem import FilesystemEye
    from atlas.ledger.writer import EventWriter

    target = Path(args.path).resolve()

    if not target.exists():
        print(f"ERROR: Path does not exist: {target}", file=sys.stderr)
        return 1

    if not target.is_dir():
        print(f"ERROR: Path is not a directory: {target}", file=sys.stderr)
        return 1

    # Create session
    session_id = f"session-{uuid.uuid4().hex[:12]}"
    start_time = time.time()

    print(f"[atlas] Starting scan session: {session_id}")
    print(f"[atlas] Target: {target}")

    # Initialize components
    ledger_dir = args.ledger_dir or get_ledger_dir()
    writer = EventWriter(ledger_dir=str(ledger_dir))

    # Emit session start event
    writer.append({
        "event_id": f"sess-{uuid.uuid4().hex[:12]}",
        "event_type": "SESSION_STARTED",
        "ts": start_time,
        "actor": {"module": "CLI"},
        "artifact_id": None,
        "confidence": 1.0,
        "evidence_refs": [],
        "session_id": session_id,
        "payload": {
            "target": str(target),
            "command": "scan",
        },
    })

    # FilesystemEye expects direct attributes, so create a simple object
    class SimpleBudget:
        def __init__(self, max_time_ms, max_files, max_bytes, max_depth):
            self.max_time_ms = max_time_ms
            self.max_files = max_files
            self.max_bytes = max_bytes
            self.max_depth = max_depth

    budget = SimpleBudget(
        max_time_ms=args.max_time * 1000 if args.max_time else None,
        max_files=args.max_files,
        max_bytes=args.max_bytes,
        max_depth=args.max_depth,
    )

    print(f"[atlas] Budget: files={args.max_files}, "
          f"bytes={args.max_bytes}, depth={args.max_depth}")

    # Run filesystem eye
    eye = FilesystemEye(writer)
    result = eye.observe(
        root=str(target),
        budget=budget,
        session_id=session_id,
    )

    # Emit session end event
    end_time = time.time()
    writer.append({
        "event_id": f"sess-{uuid.uuid4().hex[:12]}",
        "event_type": "SESSION_ENDED",
        "ts": end_time,
        "actor": {"module": "CLI"},
        "artifact_id": None,
        "confidence": 1.0,
        "evidence_refs": [],
        "session_id": session_id,
        "payload": {
            "duration_ms": (end_time - start_time) * 1000,
            "files_seen": result["files_seen"],
            "bytes_accounted": result["bytes_accounted"],
            "stopped_reason": result.get("stopped_reason"),
        },
    })

    # Report results
    print(f"[atlas] Scan complete:")
    print(f"        Files observed: {result['files_seen']}")
    print(f"        Bytes accounted: {result['bytes_accounted']}")
    print(f"        Duration: {(end_time - start_time) * 1000:.0f}ms")

    if result.get("stopped_reason"):
        print(f"        Stopped: {result['stopped_reason']}")

    return 0


def cmd_rebuild(args) -> int:
    """
    Rebuild state from ledger.

    Replays all events and rebuilds snapshots.
    """
    from atlas.ledger.reader import EventReader
    from atlas.ledger.reducers import project_artifacts
    from atlas.state.snapshots import write_snapshot, snapshot_path

    print("[atlas] Starting rebuild")

    # Initialize reader
    ledger_dir = args.ledger_dir or get_ledger_dir()
    reader = EventReader(ledger_dir=str(ledger_dir))

    # Count events
    events = list(reader.read_all())
    print(f"[atlas] Found {len(events)} events in ledger")

    if not events:
        print("[atlas] No events to process")
        return 0

    # Project artifacts
    print("[atlas] Projecting artifact state...")
    artifacts = project_artifacts(events)
    print(f"[atlas] Projected {len(artifacts)} artifacts")

    # Write snapshot
    state_dir = args.state_dir or get_state_dir()
    snap_path = snapshot_path(state_dir)

    print(f"[atlas] Writing snapshot to {snap_path}")
    count = write_snapshot(snap_path, artifacts)
    print(f"[atlas] Wrote {count} artifacts to snapshot")

    print("[atlas] Rebuild complete")
    return 0


def main(argv=None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="atlas",
        description="Atlas Core - Universal observation ledger",
    )

    parser.add_argument(
        "--ledger-dir",
        type=str,
        help="Ledger directory (default: atlas/ledger/events)",
    )

    parser.add_argument(
        "--state-dir",
        type=str,
        help="State directory (default: atlas/state)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # scan command
    scan_parser = subparsers.add_parser(
        "scan",
        help="Scan a directory and emit observation events",
    )
    scan_parser.add_argument(
        "path",
        type=str,
        help="Directory to scan",
    )
    scan_parser.add_argument(
        "--max-time",
        type=float,
        default=None,
        help="Maximum time in seconds",
    )
    scan_parser.add_argument(
        "--max-files",
        type=int,
        default=1000,
        help="Maximum files to observe (default: 1000)",
    )
    scan_parser.add_argument(
        "--max-bytes",
        type=int,
        default=100_000_000,
        help="Maximum bytes to account (default: 100MB)",
    )
    scan_parser.add_argument(
        "--max-depth",
        type=int,
        default=10,
        help="Maximum directory depth (default: 10)",
    )
    scan_parser.set_defaults(func=cmd_scan)

    # rebuild command
    rebuild_parser = subparsers.add_parser(
        "rebuild",
        help="Rebuild state from ledger events",
    )
    rebuild_parser.set_defaults(func=cmd_rebuild)

    # Parse and dispatch
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
