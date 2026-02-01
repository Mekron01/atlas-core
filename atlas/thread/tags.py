"""
Atlas Thread Tag Proposer

Proposes structural tags based on payload patterns.
All outputs are proposals only - no assertions of truth.
"""

import time
import uuid
from pathlib import Path
from typing import Optional


class TagProposer:
    """
    Proposes tags for artifacts based on observation patterns.

    Rules:
    - All outputs are proposals with confidence
    - Never overwrites existing state
    - Emits TAGS_PROPOSED events
    """

    def __init__(self, writer):
        """
        Initialize tag proposer.

        Args:
            writer: EventWriter for emitting events
        """
        self.writer = writer
        self.module_name = "TagProposer"

    def _make_event_id(self) -> str:
        """Generate unique event ID."""
        return f"tag-{uuid.uuid4().hex[:16]}"

    def _emit_tags_proposed(
        self,
        artifact_id: str,
        tags: list[str],
        confidence: float,
        reasoning: str,
        session_id: Optional[str] = None,
    ) -> str:
        """Emit TAGS_PROPOSED event."""
        event_id = self._make_event_id()

        event = {
            "event_id": event_id,
            "event_type": "TAGS_PROPOSED",
            "ts": time.time(),
            "actor": {"module": self.module_name},
            "artifact_id": artifact_id,
            "confidence": confidence,
            "evidence_refs": [],
            "payload": {
                "tags": tags,
                "reasoning": reasoning,
            },
        }

        if session_id:
            event["session_id"] = session_id

        self.writer.append(event)
        return event_id

    def propose_from_path(
        self,
        artifact_id: str,
        path: str,
        session_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Propose tags based on file path patterns.

        Args:
            artifact_id: Artifact to tag
            path: File path to analyze
            session_id: Optional session ID

        Returns:
            Event ID if tags proposed, None otherwise
        """
        p = Path(path)
        tags = []
        confidence = 0.7

        # Extension-based tags
        ext = p.suffix.lower()
        ext_tags = {
            ".py": ["python", "source-code"],
            ".js": ["javascript", "source-code"],
            ".ts": ["typescript", "source-code"],
            ".json": ["json", "data"],
            ".yaml": ["yaml", "config"],
            ".yml": ["yaml", "config"],
            ".md": ["markdown", "documentation"],
            ".txt": ["text", "documentation"],
            ".toml": ["toml", "config"],
            ".ini": ["ini", "config"],
            ".cfg": ["config"],
            ".sh": ["shell", "script"],
            ".bat": ["batch", "script"],
            ".ps1": ["powershell", "script"],
            ".sql": ["sql", "database"],
            ".html": ["html", "web"],
            ".css": ["css", "web"],
            ".xml": ["xml", "data"],
            ".csv": ["csv", "data"],
        }

        if ext in ext_tags:
            tags.extend(ext_tags[ext])
            confidence = 0.85

        # Path pattern tags
        path_lower = str(p).lower()

        if "test" in path_lower or "spec" in path_lower:
            tags.append("test")
            confidence = min(confidence, 0.8)

        if "config" in path_lower or "settings" in path_lower:
            tags.append("configuration")

        if "doc" in path_lower or "readme" in path_lower:
            tags.append("documentation")

        if ".github" in path_lower:
            tags.append("ci-cd")

        if "requirements" in path_lower or "package.json" in p.name.lower():
            tags.append("dependencies")
            confidence = 0.9

        if "__init__" in p.name:
            tags.append("module-init")

        # No tags to propose
        if not tags:
            return None

        # Deduplicate
        tags = list(dict.fromkeys(tags))

        return self._emit_tags_proposed(
            artifact_id=artifact_id,
            tags=tags,
            confidence=confidence,
            reasoning=f"Inferred from path pattern: {path}",
            session_id=session_id,
        )

    def propose_from_content(
        self,
        artifact_id: str,
        content_sample: str,
        session_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Propose tags based on content patterns.

        Args:
            artifact_id: Artifact to tag
            content_sample: First N bytes of content
            session_id: Optional session ID

        Returns:
            Event ID if tags proposed, None otherwise
        """
        tags = []
        confidence = 0.6

        content_lower = content_sample.lower()

        # Shebang detection
        if content_sample.startswith("#!"):
            tags.append("executable")
            if "python" in content_sample[:100]:
                tags.append("python")
            elif "bash" in content_sample[:100] or "sh" in content_sample[:100]:
                tags.append("shell")
            confidence = 0.9

        # License detection
        license_markers = ["mit license", "apache license", "gpl", "bsd"]
        if any(m in content_lower[:500] for m in license_markers):
            tags.append("license")
            confidence = 0.95

        # TODO/FIXME detection
        if "todo" in content_lower or "fixme" in content_lower:
            tags.append("has-todos")
            confidence = 0.85

        # Import detection (Python)
        if "import " in content_sample or "from " in content_sample:
            tags.append("has-imports")

        # Class/function detection
        if "class " in content_sample:
            tags.append("has-classes")
        if "def " in content_sample or "function " in content_sample:
            tags.append("has-functions")

        if not tags:
            return None

        tags = list(dict.fromkeys(tags))

        return self._emit_tags_proposed(
            artifact_id=artifact_id,
            tags=tags,
            confidence=confidence,
            reasoning="Inferred from content patterns",
            session_id=session_id,
        )
