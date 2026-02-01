"""
Atlas Session Management (Add-On Module)

Sessions provide bounded observation contexts.
This is an optional module - removing it never breaks the core.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional
from uuid import UUID, uuid4

from ..budgets import Budget, BudgetPresets


class SessionState(Enum):
    """State of a session."""
    CREATED = auto()
    RUNNING = auto()
    PAUSED = auto()
    COMPLETED = auto()
    ABORTED = auto()


@dataclass
class Session:
    """
    A bounded observation context.
    
    Sessions track:
    - What was observed
    - What budgets were used
    - What events were emitted
    """
    session_id: UUID
    name: str
    budget: Budget
    state: SessionState = SessionState.CREATED
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    artifact_ids: list[UUID] = field(default_factory=list)
    event_count: int = 0
    error_count: int = 0
    
    @classmethod
    def create(
        cls,
        name: str,
        budget: Optional[Budget] = None,
    ) -> Session:
        """Create a new session."""
        return cls(
            session_id=uuid4(),
            name=name,
            budget=budget or BudgetPresets.standard(),
        )
    
    def start(self) -> None:
        """Start the session."""
        if self.state != SessionState.CREATED:
            raise RuntimeError(f"Cannot start session in state {self.state}")
        self.state = SessionState.RUNNING
        self.started_at = datetime.utcnow()
        self.budget.start()
    
    def pause(self) -> None:
        """Pause the session."""
        if self.state != SessionState.RUNNING:
            raise RuntimeError(f"Cannot pause session in state {self.state}")
        self.state = SessionState.PAUSED
    
    def resume(self) -> None:
        """Resume a paused session."""
        if self.state != SessionState.PAUSED:
            raise RuntimeError(f"Cannot resume session in state {self.state}")
        self.state = SessionState.RUNNING
    
    def complete(self) -> None:
        """Mark session as completed."""
        if self.state not in (SessionState.RUNNING, SessionState.PAUSED):
            raise RuntimeError(f"Cannot complete session in state {self.state}")
        self.state = SessionState.COMPLETED
        self.ended_at = datetime.utcnow()
        self.budget.stop()
    
    def abort(self, reason: str = "") -> None:
        """Abort the session."""
        self.state = SessionState.ABORTED
        self.ended_at = datetime.utcnow()
        self.budget.stop()
    
    def record_artifact(self, artifact_id: UUID) -> None:
        """Record an artifact observed in this session."""
        self.artifact_ids.append(artifact_id)
    
    def record_event(self) -> None:
        """Record an event emitted in this session."""
        self.event_count += 1
    
    def record_error(self) -> None:
        """Record an error in this session."""
        self.error_count += 1
    
    @property
    def is_active(self) -> bool:
        """Whether session is currently active."""
        return self.state in (SessionState.RUNNING, SessionState.PAUSED)
    
    @property
    def duration_seconds(self) -> Optional[float]:
        """Duration of the session in seconds."""
        if self.started_at is None:
            return None
        end = self.ended_at or datetime.utcnow()
        return (end - self.started_at).total_seconds()
    
    @property
    def summary(self) -> dict:
        """Get session summary."""
        return {
            "session_id": str(self.session_id),
            "name": self.name,
            "state": self.state.name,
            "artifacts_observed": len(self.artifact_ids),
            "events_emitted": self.event_count,
            "errors": self.error_count,
            "duration_seconds": self.duration_seconds,
            "budget": self.budget.summary(),
        }


class SessionManager:
    """Manages session lifecycle."""
    
    def __init__(self):
        self._sessions: dict[UUID, Session] = {}
        self._active_session: Optional[UUID] = None
    
    def create(
        self,
        name: str,
        budget: Optional[Budget] = None,
    ) -> Session:
        """Create a new session."""
        session = Session.create(name, budget)
        self._sessions[session.session_id] = session
        return session
    
    def get(self, session_id: UUID) -> Optional[Session]:
        """Get a session by ID."""
        return self._sessions.get(session_id)
    
    @property
    def active(self) -> Optional[Session]:
        """Get the currently active session."""
        if self._active_session is None:
            return None
        return self._sessions.get(self._active_session)
    
    def start(self, session_id: UUID) -> Session:
        """Start a session and make it active."""
        session = self._sessions.get(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")
        
        # End any currently active session
        if self._active_session is not None:
            active = self._sessions.get(self._active_session)
            if active and active.is_active:
                active.complete()
        
        session.start()
        self._active_session = session_id
        return session
    
    def end_active(self) -> Optional[Session]:
        """End the currently active session."""
        if self._active_session is None:
            return None
        
        session = self._sessions.get(self._active_session)
        if session and session.is_active:
            session.complete()
        
        self._active_session = None
        return session
    
    def list_sessions(
        self,
        state: Optional[SessionState] = None,
    ) -> list[Session]:
        """List sessions, optionally filtered by state."""
        sessions = list(self._sessions.values())
        if state is not None:
            sessions = [s for s in sessions if s.state == state]
        return sorted(sessions, key=lambda s: s.created_at, reverse=True)
