"""
Atlas Thread Relation Proposer

Proposes relations between artifacts where obvious.
All outputs are proposals only - no assertions of truth.
"""

import time
import uuid
from pathlib import Path
from typing import Optional


class RelationProposer:
    """
    Proposes relations between artifacts.

    Relation types:
    - CONTAINS: Directory contains file
    - DEPENDS_ON: File imports/requires another

    Rules:
    - All outputs are proposals with confidence
    - Never overwrites existing state
    - Emits RELATION_PROPOSED events
    """

    def __init__(self, writer):
        """
        Initialize relation proposer.

        Args:
            writer: EventWriter for emitting events
        """
        self.writer = writer
        self.module_name = "RelationProposer"

    def _make_event_id(self) -> str:
        """Generate unique event ID."""
        return f"rel-{uuid.uuid4().hex[:16]}"

    def _emit_relation_proposed(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        confidence: float,
        reasoning: str,
        session_id: Optional[str] = None,
    ) -> str:
        """Emit RELATION_PROPOSED event."""
        event_id = self._make_event_id()

        event = {
            "event_id": event_id,
            "event_type": "RELATION_PROPOSED",
            "ts": time.time(),
            "actor": {"module": self.module_name},
            "artifact_id": source_id,
            "confidence": confidence,
            "evidence_refs": [],
            "payload": {
                "source_id": source_id,
                "target_id": target_id,
                "relation_type": relation_type,
                "reasoning": reasoning,
            },
        }

        if session_id:
            event["session_id"] = session_id

        self.writer.append(event)
        return event_id

    def propose_contains(
        self,
        parent_id: str,
        child_id: str,
        parent_path: str,
        child_path: str,
        session_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Propose CONTAINS relation based on path hierarchy.

        Args:
            parent_id: Parent artifact ID (directory)
            child_id: Child artifact ID (file/subdirectory)
            parent_path: Parent path
            child_path: Child path
            session_id: Optional session ID

        Returns:
            Event ID if relation proposed, None otherwise
        """
        parent_p = Path(parent_path)
        child_p = Path(child_path)

        # Verify containment
        try:
            child_p.relative_to(parent_p)
        except ValueError:
            return None

        # Direct child has higher confidence
        if child_p.parent == parent_p:
            confidence = 0.95
            reasoning = f"Direct child: {child_path} in {parent_path}"
        else:
            confidence = 0.85
            reasoning = f"Nested child: {child_path} under {parent_path}"

        return self._emit_relation_proposed(
            source_id=parent_id,
            target_id=child_id,
            relation_type="CONTAINS",
            confidence=confidence,
            reasoning=reasoning,
            session_id=session_id,
        )

    def propose_depends_on(
        self,
        source_id: str,
        target_id: str,
        source_path: str,
        target_path: str,
        dependency_type: str = "import",
        session_id: Optional[str] = None,
    ) -> str:
        """
        Propose DEPENDS_ON relation.

        Args:
            source_id: Dependent artifact ID
            target_id: Dependency artifact ID
            source_path: Source file path
            target_path: Target file path
            dependency_type: Type of dependency (import, require, etc.)
            session_id: Optional session ID

        Returns:
            Event ID
        """
        # Same directory = higher confidence
        source_p = Path(source_path)
        target_p = Path(target_path)

        if source_p.parent == target_p.parent:
            confidence = 0.85
        else:
            confidence = 0.7

        reasoning = f"{dependency_type}: {source_path} -> {target_path}"

        return self._emit_relation_proposed(
            source_id=source_id,
            target_id=target_id,
            relation_type="DEPENDS_ON",
            confidence=confidence,
            reasoning=reasoning,
            session_id=session_id,
        )

    def propose_from_imports(
        self,
        artifact_id: str,
        artifact_path: str,
        content_sample: str,
        known_artifacts: dict[str, str],
        session_id: Optional[str] = None,
    ) -> list[str]:
        """
        Propose DEPENDS_ON relations from import statements.

        Args:
            artifact_id: Source artifact ID
            artifact_path: Source file path
            content_sample: Content to analyze
            known_artifacts: Dict mapping paths to artifact IDs
            session_id: Optional session ID

        Returns:
            List of event IDs for proposed relations
        """
        event_ids = []

        # Python imports
        for line in content_sample.split("\n"):
            line = line.strip()

            # from X import Y
            if line.startswith("from "):
                parts = line.split()
                if len(parts) >= 2:
                    module = parts[1]
                    target = self._resolve_import(
                        artifact_path, module, known_artifacts
                    )
                    if target:
                        eid = self.propose_depends_on(
                            source_id=artifact_id,
                            target_id=target[0],
                            source_path=artifact_path,
                            target_path=target[1],
                            dependency_type="python-import",
                            session_id=session_id,
                        )
                        event_ids.append(eid)

            # import X
            elif line.startswith("import "):
                parts = line.split()
                if len(parts) >= 2:
                    module = parts[1].split(",")[0]
                    target = self._resolve_import(
                        artifact_path, module, known_artifacts
                    )
                    if target:
                        eid = self.propose_depends_on(
                            source_id=artifact_id,
                            target_id=target[0],
                            source_path=artifact_path,
                            target_path=target[1],
                            dependency_type="python-import",
                            session_id=session_id,
                        )
                        event_ids.append(eid)

        return event_ids

    def _resolve_import(
        self,
        source_path: str,
        module_name: str,
        known_artifacts: dict[str, str],
    ) -> Optional[tuple[str, str]]:
        """
        Resolve import to known artifact.

        Args:
            source_path: Importing file path
            module_name: Module being imported
            known_artifacts: Dict mapping paths to artifact IDs

        Returns:
            Tuple of (artifact_id, path) if found, None otherwise
        """
        # Handle relative imports
        if module_name.startswith("."):
            source_p = Path(source_path)
            dots = len(module_name) - len(module_name.lstrip("."))
            rel_module = module_name.lstrip(".")

            base = source_p.parent
            for _ in range(dots - 1):
                base = base.parent

            if rel_module:
                candidates = [
                    base / f"{rel_module.replace('.', '/')}.py",
                    base / rel_module.replace(".", "/") / "__init__.py",
                ]
            else:
                candidates = [base / "__init__.py"]

        else:
            # Absolute import - check workspace-relative
            candidates = [
                Path(f"{module_name.replace('.', '/')}.py"),
                Path(module_name.replace(".", "/")) / "__init__.py",
            ]

        for candidate in candidates:
            candidate_str = str(candidate)
            for path, aid in known_artifacts.items():
                if path.endswith(candidate_str) or candidate_str in path:
                    return (aid, path)

        return None
