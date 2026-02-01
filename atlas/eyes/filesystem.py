"""
Atlas FilesystemEye

Read-only observer for filesystem artifacts.
Enforces budget limits and emits observation events.

Rules:
- Read-only (never modifies files)
- Never executes files
- Respects all budget constraints
- Emits ACCESS_LIMITATION_NOTED when budgets exceeded
"""

import hashlib
import time
import uuid
from pathlib import Path
from typing import Optional

from atlas.budgets import Budget
from atlas.ledger.writer import EventWriter


class FilesystemEye:
    """
    Filesystem observer that emits ARTIFACT_SEEN events.

    Enforces budget limits:
    - max_time_ms: Wall-clock time limit
    - max_files: Maximum files to observe
    - max_bytes: Maximum total bytes to account
    - max_depth: Maximum directory depth from root
    """

    def __init__(self, writer: EventWriter):
        self.writer = writer
        self.module_name = "FilesystemEye"

    def _make_event_id(self) -> str:
        """Generate unique event ID."""
        return f"fs-{uuid.uuid4().hex[:16]}"

    def _compute_hash(self, path: Path) -> Optional[str]:
        """Compute SHA-256 hash of first 4096 bytes."""
        try:
            with open(path, "rb") as f:
                data = f.read(4096)
                return hashlib.sha256(data).hexdigest()
        except Exception:
            return None

    def _get_depth(self, path: Path, root: Path) -> int:
        """Calculate depth relative to root path."""
        try:
            rel = path.relative_to(root)
            return len(rel.parts) - 1  # -1 because file itself doesn't count as depth
        except ValueError:
            return 0

    def _emit_artifact_seen(
        self,
        path: Path,
        size: int,
        content_hash: Optional[str],
        session_id: Optional[str] = None,
    ) -> None:
        """Emit ARTIFACT_SEEN event."""
        artifact_id = content_hash or self._make_event_id()

        event = {
            "event_id": self._make_event_id(),
            "event_type": "ARTIFACT_SEEN",
            "ts": time.time(),
            "actor": {"module": self.module_name},
            "artifact_id": artifact_id,
            "confidence": 0.95 if content_hash else 0.5,
            "evidence_refs": [],
            "payload": {
                "path": str(path),
                "size": size,
                "content_hash": content_hash,
                "access_scope": "read-only",
            },
        }

        if session_id:
            event["session_id"] = session_id

        self.writer.append(event)

    def _emit_access_limitation(
        self,
        reason: str,
        limit_type: str,
        limit_value: float,
        current_value: float,
        session_id: Optional[str] = None,
    ) -> None:
        """Emit ACCESS_LIMITATION_NOTED event when budget exceeded."""
        event = {
            "event_id": self._make_event_id(),
            "event_type": "ACCESS_LIMITATION_NOTED",
            "ts": time.time(),
            "actor": {"module": self.module_name},
            "artifact_id": None,
            "confidence": 1.0,
            "evidence_refs": [],
            "payload": {
                "reason": reason,
                "limit_type": limit_type,
                "limit_value": limit_value,
                "current_value": current_value,
                "access_scope": "read-only",
            },
        }

        if session_id:
            event["session_id"] = session_id

        self.writer.append(event)

    def observe(
        self,
        root: str,
        budget: Budget,
        session_id: Optional[str] = None,
    ) -> dict:
        """
        Observe filesystem starting from root path.

        Args:
            root: Root directory path to scan
            budget: Budget constraints to enforce
            session_id: Optional session identifier

        Returns:
            Summary dict with files_seen, bytes_accounted, stopped_reason
        """
        root_path = Path(root).resolve()

        if not root_path.exists():
            return {
                "files_seen": 0,
                "bytes_accounted": 0,
                "stopped_reason": "root_not_found",
            }

        start_time = time.time()
        files_seen = 0
        bytes_accounted = 0
        stopped_reason = None

        # Extract budget limits with defaults
        max_time_ms = getattr(budget, "max_time_ms", None) or float("inf")
        max_files = getattr(budget, "max_files", None) or float("inf")
        max_bytes = getattr(budget, "max_bytes", None) or float("inf")
        max_depth = getattr(budget, "max_depth", None) or float("inf")

        def check_time_budget() -> bool:
            elapsed_ms = (time.time() - start_time) * 1000
            return elapsed_ms < max_time_ms

        # Walk directory tree
        try:
            for path in root_path.rglob("*"):
                # Skip non-files
                if not path.is_file():
                    continue

                # Check time budget
                if not check_time_budget():
                    elapsed_ms = (time.time() - start_time) * 1000
                    self._emit_access_limitation(
                        reason="Time budget exceeded",
                        limit_type="max_time_ms",
                        limit_value=max_time_ms,
                        current_value=elapsed_ms,
                        session_id=session_id,
                    )
                    stopped_reason = "time_budget_exceeded"
                    break

                # Check file count budget
                if files_seen >= max_files:
                    self._emit_access_limitation(
                        reason="File count budget exceeded",
                        limit_type="max_files",
                        limit_value=max_files,
                        current_value=files_seen,
                        session_id=session_id,
                    )
                    stopped_reason = "file_budget_exceeded"
                    break

                # Check depth (skip silently if too deep)
                depth = self._get_depth(path, root_path)
                if depth > max_depth:
                    continue

                # Get file size
                try:
                    size = path.stat().st_size
                except Exception:
                    continue

                # Check byte budget before accounting
                if bytes_accounted + size > max_bytes:
                    self._emit_access_limitation(
                        reason="Byte budget would be exceeded",
                        limit_type="max_bytes",
                        limit_value=max_bytes,
                        current_value=bytes_accounted,
                        session_id=session_id,
                    )
                    stopped_reason = "byte_budget_exceeded"
                    break

                # Compute hash (first 4096 bytes only)
                content_hash = self._compute_hash(path)

                # Emit observation event
                self._emit_artifact_seen(
                    path=path,
                    size=size,
                    content_hash=content_hash,
                    session_id=session_id,
                )

                # Update counters
                files_seen += 1
                bytes_accounted += size

        except PermissionError:
            self._emit_access_limitation(
                reason="Permission denied during traversal",
                limit_type="access",
                limit_value=0,
                current_value=0,
                session_id=session_id,
            )
            stopped_reason = "permission_denied"

        return {
            "files_seen": files_seen,
            "bytes_accounted": bytes_accounted,
            "stopped_reason": stopped_reason,
        }
