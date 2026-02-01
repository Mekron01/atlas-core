"""
Atlas State Snapshots

Atomic snapshot writers and readers for artifact state.
Snapshots are rebuildable from ledger at any time.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Iterable


def write_snapshot(
    path: str | Path,
    artifacts: dict[str, dict],
) -> int:
    """
    Write artifacts to a JSONL snapshot file.

    Uses atomic write (temp file + replace) for safety.
    One artifact per line.

    Args:
        path: Destination file path
        artifacts: Dict mapping artifact_id to artifact state

    Returns:
        Number of artifacts written
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Get directory for temp file (same filesystem for atomic rename)
    dir_path = path.parent

    count = 0

    # Write to temp file first
    fd, tmp_path = tempfile.mkstemp(
        suffix=".tmp",
        prefix="snapshot_",
        dir=dir_path,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for artifact_id, state in artifacts.items():
                line = json.dumps(state, ensure_ascii=False)
                f.write(line + "\n")
                count += 1
            f.flush()
            os.fsync(f.fileno())

        # Atomic replace
        Path(tmp_path).replace(path)

    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return count


def read_snapshot(path: str | Path) -> dict[str, dict]:
    """
    Read artifacts from a JSONL snapshot file.

    Args:
        path: Source file path

    Returns:
        Dict mapping artifact_id to artifact state
    """
    path = Path(path)

    if not path.exists():
        return {}

    artifacts: dict[str, dict] = {}

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                state = json.loads(line)
                artifact_id = state.get("artifact_id")
                if artifact_id:
                    artifacts[artifact_id] = state
            except json.JSONDecodeError:
                # Skip malformed lines
                continue

    return artifacts


def iter_snapshot(path: str | Path) -> Iterable[dict]:
    """
    Iterate over artifacts in a snapshot file.

    Memory-efficient for large snapshots.

    Args:
        path: Source file path

    Yields:
        Artifact state dicts
    """
    path = Path(path)

    if not path.exists():
        return

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                state = json.loads(line)
                if state.get("artifact_id"):
                    yield state
            except json.JSONDecodeError:
                continue


def snapshot_path(state_dir: str | Path, name: str = "artifacts") -> Path:
    """
    Get standard snapshot file path.

    Args:
        state_dir: State directory
        name: Snapshot name (default: "artifacts")

    Returns:
        Path to snapshot file
    """
    return Path(state_dir) / f"{name}.snapshot.jsonl"
