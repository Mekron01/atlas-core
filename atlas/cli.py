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


def cmd_remote_scan(args) -> int:
    """
    Scan a remote URL and emit observation events.

    Requires explicit --allow-remote flag.
    """
    from atlas.eyes.web import WebEye
    from atlas.eyes.remote_repo import RemoteRepoEye
    from atlas.ledger.writer import EventWriter
    from atlas.remote.policy import RemotePolicy

    url = args.url

    # Remote access is OFF by default
    if not args.allow_remote:
        print("[atlas] ERROR: Remote access disabled by default")
        print("[atlas] Use --allow-remote to enable")
        return 1

    # Create session
    session_id = f"session-{uuid.uuid4().hex[:12]}"
    start_time = time.time()

    print(f"[atlas] Starting remote scan session: {session_id}")
    print(f"[atlas] Target: {url}")

    # Initialize writer
    ledger_dir = args.ledger_dir or get_ledger_dir()
    writer = EventWriter(ledger_dir=str(ledger_dir))

    # Emit session start
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
            "target": url,
            "command": "remote-scan",
        },
    })

    # Create policy
    domains = args.domains.split(",") if args.domains else None
    policy = RemotePolicy(
        allow_remote_access=True,
        max_remote_calls=args.max_calls,
        freshness_window_seconds=args.freshness,
        required_domains_allowlist=domains,
    )

    print(f"[atlas] Policy: max_calls={policy.max_remote_calls}, "
          f"freshness={policy.freshness_window_seconds}s")

    # Create budget
    class SimpleBudget:
        def __init__(self, max_time_ms, max_bytes):
            self.max_time_ms = max_time_ms
            self.max_bytes = max_bytes
            self.max_bytes_per_artifact = max_bytes

    budget = SimpleBudget(
        max_time_ms=args.max_time * 1000 if args.max_time else 60000,
        max_bytes=args.max_bytes,
    )

    # Choose eye based on URL
    results = []

    if "github.com" in url or url.startswith("git+"):
        print("[atlas] Using RemoteRepoEye")
        eye = RemoteRepoEye(writer)
        results = eye.observe_repo(
            repo_url=url,
            budget=budget,
            remote_policy=policy,
            session_id=session_id,
        )
    else:
        print("[atlas] Using WebEye")
        eye = WebEye(writer)
        result = eye.observe(
            url=url,
            budget=budget,
            remote_policy=policy,
            session_id=session_id,
        )
        results = [{"url": url, **result}]

    # Emit session end
    end_time = time.time()
    successful = sum(1 for r in results if r.get("status") == "success")

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
            "urls_attempted": len(results),
            "urls_successful": successful,
            "remote_calls_made": policy.calls_made,
        },
    })

    # Report
    print("[atlas] Remote scan complete:")
    print(f"        URLs attempted: {len(results)}")
    print(f"        URLs successful: {successful}")
    print(f"        Remote calls: {policy.calls_made}")
    print(f"        Duration: {(end_time - start_time) * 1000:.0f}ms")

    for r in results:
        status = r.get("status", "unknown")
        if status == "success":
            print(f"        ✓ {r['url'][:60]}...")
        elif status == "not_found":
            pass  # Skip 404s silently
        else:
            reason = r.get("reason", "")
            print(f"        ✗ {r['url'][:40]}... ({status}: {reason})")

    return 0


def cmd_janitor(args) -> int:
    """
    Analyze system state and print maintenance recommendations.
    """
    from atlas.ledger.writer import EventWriter
    from atlas.maintenance.janitor import Janitor
    from atlas.state.snapshots import read_snapshot, snapshot_path

    print("[atlas] Running janitor analysis")

    # Load snapshot
    state_dir = args.state_dir or get_state_dir()
    snap_path = snapshot_path(state_dir)

    if not snap_path.exists():
        print("[atlas] No snapshot found. Run 'atlas rebuild' first.")
        return 1

    artifacts = read_snapshot(snap_path)
    print(f"[atlas] Loaded {len(artifacts)} artifacts from snapshot")

    # Initialize janitor with writer
    ledger_dir = args.ledger_dir or get_ledger_dir()
    writer = EventWriter(ledger_dir=str(ledger_dir))
    janitor = Janitor(writer=writer)

    # Create session
    session_id = f"session-{uuid.uuid4().hex[:12]}"

    # Run analysis
    cache_dir = "atlas/cache" if Path("atlas/cache").exists() else None
    recommendations = janitor.run(
        artifacts=artifacts,
        cache_dir=cache_dir,
        session_id=session_id,
    )

    # Print report
    report = janitor.format_report(recommendations)
    print(report)

    print(f"[atlas] Total recommendations: {len(recommendations)}")
    print("[atlas] Events written to ledger")

    return 0


def cmd_archive(args) -> int:
    """
    Archive old cache files.

    Does nothing without --apply flag.
    """
    from atlas.ledger.writer import EventWriter
    from atlas.maintenance.archive import Archive
    from atlas.maintenance.janitor import Janitor
    from atlas.state.snapshots import read_snapshot, snapshot_path

    cache_dir = Path("atlas/cache")

    if not cache_dir.exists():
        print("[atlas] No cache directory found")
        return 0

    # Initialize
    ledger_dir = args.ledger_dir or get_ledger_dir()
    writer = EventWriter(ledger_dir=str(ledger_dir))

    archive = Archive(
        cache_dir=str(cache_dir),
        writer=writer,
    )

    # Show current archive stats
    stats = archive.get_archive_stats()
    print(f"[atlas] Archive stats:")
    print(f"        Files: {stats['total_files']}")
    print(f"        Size: {stats['total_bytes']} bytes")

    if not args.apply:
        print("[atlas] Dry run mode (use --apply to execute)")

        # Get recommendations
        janitor = Janitor()
        cache_recs = janitor.analyze_cache(
            cache_dir=str(cache_dir),
            max_age_days=args.max_age_days,
        )

        if cache_recs:
            print(f"[atlas] Would archive {len(cache_recs)} files:")
            for rec in cache_recs[:5]:
                print(f"        {rec.path}")
            if len(cache_recs) > 5:
                print(f"        ... and {len(cache_recs) - 5} more")
        else:
            print("[atlas] No files to archive")

        return 0

    # Apply mode - actually archive
    print("[atlas] Applying archive...")

    session_id = f"session-{uuid.uuid4().hex[:12]}"

    # Get files to archive
    janitor = Janitor()
    cache_recs = janitor.analyze_cache(
        cache_dir=str(cache_dir),
        max_age_days=args.max_age_days,
    )

    if not cache_recs:
        print("[atlas] No files to archive")
        return 0

    paths = [rec.path for rec in cache_recs]
    results = archive.archive_batch(paths, session_id=session_id)

    successful = sum(1 for r in results if r.success)
    failed = len(results) - successful

    print(f"[atlas] Archive complete:")
    print(f"        Archived: {successful}")
    print(f"        Failed: {failed}")

    return 0


def cmd_index_rebuild(args) -> int:
    """
    Rebuild SQLite index from snapshots.

    Creates fast-lookup indexes (disposable, rebuildable).
    """
    from atlas.index.build import IndexBuilder

    print("[atlas] Starting index rebuild")

    state_dir = args.state_dir or get_state_dir()
    builder = IndexBuilder(state_dir=str(state_dir))

    # Determine snapshot paths
    artifacts_path = args.artifacts
    relations_path = args.relations

    print(f"[atlas] State dir: {state_dir}")

    # Rebuild
    stats = builder.rebuild(
        artifacts_snapshot=artifacts_path,
        relations_snapshot=relations_path,
    )

    print("[atlas] Index rebuild complete:")
    print(f"        Artifacts: {stats['artifacts']}")
    print(f"        Relations: {stats['relations']}")
    print(f"        Tags: {stats['tags']}")

    return 0


def cmd_version(args) -> int:
    """Print version information."""
    from atlas import __version__

    print(f"atlas-core {__version__}")
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

    # remote-scan command
    remote_parser = subparsers.add_parser(
        "remote-scan",
        help="Scan a remote URL (disabled by default)",
    )
    remote_parser.add_argument(
        "url",
        type=str,
        help="URL to scan",
    )
    remote_parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Enable remote access (required)",
    )
    remote_parser.add_argument(
        "--max-calls",
        type=int,
        default=10,
        help="Maximum remote calls (default: 10)",
    )
    remote_parser.add_argument(
        "--max-bytes",
        type=int,
        default=1_000_000,
        help="Maximum bytes per artifact (default: 1MB)",
    )
    remote_parser.add_argument(
        "--max-time",
        type=float,
        default=60,
        help="Maximum time in seconds (default: 60)",
    )
    remote_parser.add_argument(
        "--freshness",
        type=int,
        default=86400,
        help="Freshness window in seconds (default: 86400)",
    )
    remote_parser.add_argument(
        "--domains",
        type=str,
        default=None,
        help="Comma-separated domain allowlist",
    )
    remote_parser.set_defaults(func=cmd_remote_scan)

    # janitor command
    janitor_parser = subparsers.add_parser(
        "janitor",
        help="Analyze and recommend maintenance",
    )
    janitor_parser.set_defaults(func=cmd_janitor)

    # archive command
    archive_parser = subparsers.add_parser(
        "archive",
        help="Archive old cache files",
    )
    archive_parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually perform archive (default: dry run)",
    )
    archive_parser.add_argument(
        "--max-age-days",
        type=int,
        default=30,
        help="Archive files older than N days (default: 30)",
    )
    archive_parser.set_defaults(func=cmd_archive)

    # index command
    index_parser = subparsers.add_parser(
        "index",
        help="Manage SQLite index",
    )
    index_sub = index_parser.add_subparsers(
        dest="index_command", required=True
    )

    # index rebuild subcommand
    index_rebuild_parser = index_sub.add_parser(
        "rebuild",
        help="Rebuild index from snapshots",
    )
    index_rebuild_parser.add_argument(
        "--artifacts",
        type=str,
        default=None,
        help="Path to artifacts snapshot",
    )
    index_rebuild_parser.add_argument(
        "--relations",
        type=str,
        default=None,
        help="Path to relations snapshot",
    )
    index_rebuild_parser.set_defaults(func=cmd_index_rebuild)

    # version command
    version_parser = subparsers.add_parser(
        "version",
        help="Print version information",
    )
    version_parser.set_defaults(func=cmd_version)

    # Parse and dispatch
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
