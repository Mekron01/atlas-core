"""
Atlas Archive

Soft archive for cache files.
Never touches ledger - only moves cache blobs.
"""

import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ArchiveResult:
    """Result of an archive operation."""
    source_path: str
    archive_path: str
    size_bytes: int
    success: bool
    error: Optional[str] = None


class Archive:
    """
    Implements soft archive for cache files.

    Rules:
    - Only moves cache blobs to archive folder
    - Never touches ledger
    - Never deletes without explicit confirmation
    - All actions are logged as events
    """

    def __init__(
        self,
        cache_dir: str = "atlas/cache",
        archive_subdir: str = "archive",
        writer=None,
    ):
        """
        Initialize Archive.

        Args:
            cache_dir: Path to cache directory
            archive_subdir: Subdirectory name for archives
            writer: Optional EventWriter for emitting events
        """
        self.cache_dir = Path(cache_dir)
        self.archive_dir = self.cache_dir / archive_subdir
        self.writer = writer
        self.module_name = "Archive"

    def _make_event_id(self) -> str:
        """Generate unique event ID."""
        return f"archive-{uuid.uuid4().hex[:16]}"

    def ensure_archive_dir(self) -> Path:
        """Create archive directory if needed."""
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        return self.archive_dir

    def archive_file(
        self,
        source_path: str,
        session_id: Optional[str] = None,
    ) -> ArchiveResult:
        """
        Move a single file to archive.

        Args:
            source_path: Path to file to archive
            session_id: Optional session ID

        Returns:
            ArchiveResult with operation details
        """
        source = Path(source_path)

        if not source.exists():
            return ArchiveResult(
                source_path=str(source),
                archive_path="",
                size_bytes=0,
                success=False,
                error="Source file does not exist",
            )

        if not source.is_file():
            return ArchiveResult(
                source_path=str(source),
                archive_path="",
                size_bytes=0,
                success=False,
                error="Source is not a file",
            )

        # Verify source is under cache dir
        try:
            source.resolve().relative_to(self.cache_dir.resolve())
        except ValueError:
            return ArchiveResult(
                source_path=str(source),
                archive_path="",
                size_bytes=0,
                success=False,
                error="Source not under cache directory",
            )

        # Skip if already in archive
        if "archive" in str(source):
            return ArchiveResult(
                source_path=str(source),
                archive_path=str(source),
                size_bytes=0,
                success=False,
                error="Already in archive",
            )

        try:
            size_bytes = source.stat().st_size

            # Create archive destination
            self.ensure_archive_dir()

            # Preserve relative structure
            rel_path = source.relative_to(self.cache_dir)
            dest = self.archive_dir / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)

            # Add timestamp to avoid collisions
            timestamp = int(time.time())
            final_dest = dest.with_name(f"{dest.stem}_{timestamp}{dest.suffix}")

            # Move file
            shutil.move(str(source), str(final_dest))

            # Emit event
            self._emit_file_archived(
                source_path=str(source),
                archive_path=str(final_dest),
                size_bytes=size_bytes,
                session_id=session_id,
            )

            return ArchiveResult(
                source_path=str(source),
                archive_path=str(final_dest),
                size_bytes=size_bytes,
                success=True,
            )

        except Exception as e:
            return ArchiveResult(
                source_path=str(source),
                archive_path="",
                size_bytes=0,
                success=False,
                error=str(e),
            )

    def archive_batch(
        self,
        paths: list[str],
        session_id: Optional[str] = None,
    ) -> list[ArchiveResult]:
        """
        Archive multiple files.

        Args:
            paths: List of file paths to archive
            session_id: Optional session ID

        Returns:
            List of ArchiveResults
        """
        results = []

        for path in paths:
            result = self.archive_file(path, session_id)
            results.append(result)

        return results

    def get_archive_stats(self) -> dict:
        """Get statistics about archived files."""
        if not self.archive_dir.exists():
            return {
                "total_files": 0,
                "total_bytes": 0,
                "oldest_file": None,
                "newest_file": None,
            }

        files = list(self.archive_dir.rglob("*"))
        files = [f for f in files if f.is_file()]

        if not files:
            return {
                "total_files": 0,
                "total_bytes": 0,
                "oldest_file": None,
                "newest_file": None,
            }

        total_bytes = sum(f.stat().st_size for f in files)

        # Find oldest/newest
        files_with_mtime = [(f, f.stat().st_mtime) for f in files]
        files_with_mtime.sort(key=lambda x: x[1])

        oldest = files_with_mtime[0][0]
        newest = files_with_mtime[-1][0]

        return {
            "total_files": len(files),
            "total_bytes": total_bytes,
            "oldest_file": str(oldest),
            "newest_file": str(newest),
        }

    def list_archived(self) -> list[dict]:
        """List all archived files."""
        if not self.archive_dir.exists():
            return []

        archived = []

        for f in self.archive_dir.rglob("*"):
            if not f.is_file():
                continue

            stat = f.stat()
            archived.append({
                "path": str(f),
                "size_bytes": stat.st_size,
                "archived_at": stat.st_mtime,
            })

        # Sort by archived time
        archived.sort(key=lambda x: x["archived_at"], reverse=True)

        return archived

    def _emit_file_archived(
        self,
        source_path: str,
        archive_path: str,
        size_bytes: int,
        session_id: Optional[str] = None,
    ) -> str:
        """Emit FILE_ARCHIVED event."""
        if not self.writer:
            return ""

        event_id = self._make_event_id()

        event = {
            "event_id": event_id,
            "event_type": "FILE_ARCHIVED",
            "ts": time.time(),
            "actor": {"module": self.module_name},
            "artifact_id": None,
            "confidence": 1.0,
            "evidence_refs": [],
            "payload": {
                "source_path": source_path,
                "archive_path": archive_path,
                "size_bytes": size_bytes,
            },
        }

        if session_id:
            event["session_id"] = session_id

        self.writer.append(event)
        return event_id
