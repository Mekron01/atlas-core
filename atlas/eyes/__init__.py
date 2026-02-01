"""
Atlas Eyes - Observer Framework

Eyes observe sources and emit observation events.
They are read-only, stateless, and budget-aware.

Rules:
- Read-only: Eyes never modify sources
- No execution: Eyes never run code from sources
- No global state: Each Eye is independent
- No cross-eye communication: Eyes don't talk to each other
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Iterator, Optional, Protocol
from uuid import UUID, uuid4

from ..budgets import Budget, BudgetGuard, BudgetType
from ..ledger.events import (
    Event,
    artifact_observed,
    artifact_content_extracted,
    artifact_access_denied,
    artifact_changed,
    fingerprint_computed,
    budget_exhausted,
    error_recorded,
)
from ..schema import (
    AccessScope,
    ArtifactKind,
    SourceType,
)


class ObservationStatus(Enum):
    """Result status of an observation attempt."""
    SUCCESS = auto()
    PARTIAL = auto()
    ACCESS_DENIED = auto()
    NOT_FOUND = auto()
    ERROR = auto()
    BUDGET_EXHAUSTED = auto()


@dataclass
class ObservationResult:
    """Result of observing a single artifact."""
    status: ObservationStatus
    artifact_id: UUID
    source_locator: str
    events: list[Event] = field(default_factory=list)
    error_message: Optional[str] = None
    
    @property
    def success(self) -> bool:
        return self.status in (ObservationStatus.SUCCESS, ObservationStatus.PARTIAL)


@dataclass
class ScanResult:
    """Result of a complete scan operation."""
    source_type: SourceType
    started_at: datetime
    ended_at: Optional[datetime] = None
    observations: list[ObservationResult] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    budget_exhausted: bool = False
    exhausted_budgets: list[BudgetType] = field(default_factory=list)
    
    @property
    def artifact_count(self) -> int:
        return len(self.observations)
    
    @property
    def success_count(self) -> int:
        return sum(1 for o in self.observations if o.success)
    
    @property
    def all_events(self) -> Iterator[Event]:
        """Iterate all events from this scan."""
        yield from self.events
        for obs in self.observations:
            yield from obs.events


class Eye(ABC):
    """
    Abstract base class for Atlas Eyes.
    
    Each Eye observes one type of source and emits events.
    Eyes are stateless - all state flows through events.
    """
    
    def __init__(self, eye_id: Optional[str] = None):
        self.eye_id = eye_id or f"{self.__class__.__name__}-{uuid4().hex[:8]}"
    
    @property
    @abstractmethod
    def source_type(self) -> SourceType:
        """The type of source this Eye observes."""
        pass
    
    @abstractmethod
    def scan(
        self,
        root: str,
        budget: Budget,
        *,
        session_id: Optional[UUID] = None,
    ) -> ScanResult:
        """
        Scan a source for artifacts.
        
        Must respect budget limits.
        Must emit only observation events.
        Must not modify the source.
        """
        pass
    
    def _emit_observation(
        self,
        artifact_id: UUID,
        kind: ArtifactKind,
        source_locator: str,
        access_scope: AccessScope,
        session_id: Optional[UUID] = None,
    ) -> Event:
        """Helper to emit an artifact observation event."""
        return artifact_observed(
            source=self.eye_id,
            artifact_id=artifact_id,
            artifact_kind=kind.name.lower(),
            source_type=self.source_type.name.lower(),
            source_locator=source_locator,
            access_scope=access_scope.name.lower(),
            session_id=session_id,
        )
    
    def _emit_extraction(
        self,
        artifact_id: UUID,
        depth: int,
        size_bytes: int,
        content_hash: Optional[str] = None,
        extracted_text_ref: Optional[str] = None,
        errors: tuple[str, ...] = (),
        session_id: Optional[UUID] = None,
    ) -> Event:
        """Helper to emit a content extraction event."""
        return artifact_content_extracted(
            source=self.eye_id,
            artifact_id=artifact_id,
            extraction_depth=depth,
            size_bytes=size_bytes,
            content_hash=content_hash,
            extracted_text_ref=extracted_text_ref,
            errors=errors,
            session_id=session_id,
        )
    
    def _emit_access_denied(
        self,
        artifact_id: UUID,
        source_locator: str,
        reason: str,
        session_id: Optional[UUID] = None,
    ) -> Event:
        """Helper to emit an access denied event."""
        return artifact_access_denied(
            source=self.eye_id,
            artifact_id=artifact_id,
            source_locator=source_locator,
            reason=reason,
            session_id=session_id,
        )
    
    def _emit_fingerprint(
        self,
        artifact_id: UUID,
        content_hash: Optional[str],
        structure_hash: Optional[str],
        size_bytes: int,
        entropy_score: Optional[float],
        session_id: Optional[UUID] = None,
    ) -> Event:
        """Helper to emit a fingerprint event."""
        return fingerprint_computed(
            source=self.eye_id,
            artifact_id=artifact_id,
            content_hash=content_hash,
            structure_hash=structure_hash,
            size_bytes=size_bytes,
            entropy_score=entropy_score,
            session_id=session_id,
        )
    
    def _emit_budget_exhausted(
        self,
        budget_type: BudgetType,
        limit: float,
        consumed: float,
        session_id: Optional[UUID] = None,
    ) -> Event:
        """Helper to emit budget exhaustion event."""
        return budget_exhausted(
            source=self.eye_id,
            budget_type=budget_type.name.lower(),
            limit=limit,
            consumed=consumed,
            session_id=session_id,
        )
    
    def _emit_error(
        self,
        error_type: str,
        message: str,
        artifact_ids: tuple[UUID, ...] = (),
        session_id: Optional[UUID] = None,
    ) -> Event:
        """Helper to emit an error event."""
        return error_recorded(
            source=self.eye_id,
            error_type=error_type,
            message=message,
            artifact_ids=artifact_ids,
            session_id=session_id,
        )


# -----------------------------------------------------------------------------
# Filesystem Eye Implementation
# -----------------------------------------------------------------------------

class FilesystemEye(Eye):
    """
    Eye for observing filesystem artifacts.
    
    Scans directories and files, respecting budget constraints.
    """
    
    @property
    def source_type(self) -> SourceType:
        return SourceType.FILESYSTEM
    
    def scan(
        self,
        root: str,
        budget: Budget,
        *,
        session_id: Optional[UUID] = None,
        include_hidden: bool = False,
        file_patterns: Optional[list[str]] = None,
    ) -> ScanResult:
        """
        Scan filesystem starting from root.
        
        Args:
            root: Directory path to scan
            budget: Resource constraints
            session_id: Optional session identifier
            include_hidden: Whether to include hidden files
            file_patterns: Optional glob patterns to match
        """
        result = ScanResult(
            source_type=self.source_type,
            started_at=datetime.utcnow(),
        )
        
        root_path = Path(root)
        if not root_path.exists():
            result.events.append(self._emit_error(
                "NOT_FOUND",
                f"Root path does not exist: {root}",
                session_id=session_id,
            ))
            result.ended_at = datetime.utcnow()
            return result
        
        with BudgetGuard(budget) as guard:
            self._scan_directory(
                root_path,
                depth=0,
                guard=guard,
                result=result,
                session_id=session_id,
                include_hidden=include_hidden,
            )
            
            if budget.any_exhausted:
                result.budget_exhausted = True
                result.exhausted_budgets = budget.exhausted_budgets
                for bt in result.exhausted_budgets:
                    limit = budget.limits.get(bt)
                    if limit:
                        result.events.append(self._emit_budget_exhausted(
                            bt,
                            limit.limit,
                            limit.consumed,
                            session_id=session_id,
                        ))
        
        result.ended_at = datetime.utcnow()
        return result
    
    def _scan_directory(
        self,
        path: Path,
        depth: int,
        guard: BudgetGuard,
        result: ScanResult,
        session_id: Optional[UUID],
        include_hidden: bool,
    ) -> None:
        """Recursively scan a directory."""
        if not guard.can_continue():
            return
        
        if not guard.at_depth(depth):
            return
        
        try:
            entries = list(path.iterdir())
        except PermissionError:
            artifact_id = uuid4()
            result.observations.append(ObservationResult(
                status=ObservationStatus.ACCESS_DENIED,
                artifact_id=artifact_id,
                source_locator=str(path),
                events=[self._emit_access_denied(
                    artifact_id,
                    str(path),
                    "Permission denied",
                    session_id=session_id,
                )],
            ))
            return
        except Exception as e:
            result.events.append(self._emit_error(
                "SCAN_ERROR",
                f"Error scanning {path}: {e}",
                session_id=session_id,
            ))
            return
        
        for entry in entries:
            if not guard.can_continue():
                return
            
            # Skip hidden files unless requested
            if not include_hidden and entry.name.startswith('.'):
                continue
            
            if entry.is_file():
                self._observe_file(
                    entry, guard, result, session_id
                )
            elif entry.is_dir():
                self._scan_directory(
                    entry,
                    depth + 1,
                    guard,
                    result,
                    session_id,
                    include_hidden,
                )
    
    def _observe_file(
        self,
        path: Path,
        guard: BudgetGuard,
        result: ScanResult,
        session_id: Optional[UUID],
    ) -> None:
        """Observe a single file."""
        artifact_id = uuid4()
        events: list[Event] = []
        
        try:
            stat = path.stat()
            size_bytes = stat.st_size
            
            # Check budget before reading
            if not guard.can_consume(BudgetType.BYTES_READ, size_bytes):
                # Record but don't read
                events.append(self._emit_observation(
                    artifact_id,
                    ArtifactKind.LOCAL,
                    str(path),
                    AccessScope.METADATA_ONLY,
                    session_id=session_id,
                ))
                guard.consume_file(0)
                result.observations.append(ObservationResult(
                    status=ObservationStatus.PARTIAL,
                    artifact_id=artifact_id,
                    source_locator=str(path),
                    events=events,
                ))
                return
            
            # Full observation
            events.append(self._emit_observation(
                artifact_id,
                ArtifactKind.LOCAL,
                str(path),
                AccessScope.READ_ONLY,
                session_id=session_id,
            ))
            
            # Compute fingerprint
            content_hash = self._compute_hash(path)
            events.append(self._emit_fingerprint(
                artifact_id,
                content_hash=content_hash,
                structure_hash=None,  # Could add structure hashing
                size_bytes=size_bytes,
                entropy_score=None,  # Could add entropy calculation
                session_id=session_id,
            ))
            
            guard.consume_file(size_bytes)
            
            result.observations.append(ObservationResult(
                status=ObservationStatus.SUCCESS,
                artifact_id=artifact_id,
                source_locator=str(path),
                events=events,
            ))
            
        except PermissionError:
            events.append(self._emit_access_denied(
                artifact_id,
                str(path),
                "Permission denied",
                session_id=session_id,
            ))
            result.observations.append(ObservationResult(
                status=ObservationStatus.ACCESS_DENIED,
                artifact_id=artifact_id,
                source_locator=str(path),
                events=events,
            ))
        except Exception as e:
            events.append(self._emit_error(
                "OBSERVATION_ERROR",
                str(e),
                artifact_ids=(artifact_id,),
                session_id=session_id,
            ))
            result.observations.append(ObservationResult(
                status=ObservationStatus.ERROR,
                artifact_id=artifact_id,
                source_locator=str(path),
                events=events,
                error_message=str(e),
            ))
    
    def _compute_hash(self, path: Path) -> str:
        """Compute SHA-256 hash of file contents."""
        import hashlib
        
        hasher = hashlib.sha256()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                hasher.update(chunk)
        return hasher.hexdigest()


# -----------------------------------------------------------------------------
# Eye Registry
# -----------------------------------------------------------------------------

class EyeRegistry:
    """Registry of available Eyes."""
    
    def __init__(self):
        self._eyes: dict[SourceType, type[Eye]] = {}
    
    def register(self, source_type: SourceType, eye_class: type[Eye]) -> None:
        """Register an Eye class for a source type."""
        self._eyes[source_type] = eye_class
    
    def get(self, source_type: SourceType) -> Optional[type[Eye]]:
        """Get Eye class for a source type."""
        return self._eyes.get(source_type)
    
    def create(
        self,
        source_type: SourceType,
        **kwargs,
    ) -> Optional[Eye]:
        """Create an Eye instance for a source type."""
        eye_class = self.get(source_type)
        if eye_class is None:
            return None
        return eye_class(**kwargs)


# Default registry with filesystem eye
default_registry = EyeRegistry()
default_registry.register(SourceType.FILESYSTEM, FilesystemEye)
