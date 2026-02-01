"""
Atlas Event Validator

Strict JSON-schema-like validation for event envelopes and payloads.
No external dependencies - pure stdlib.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class EventType(Enum):
    """All valid event types."""

    # Observation Events (Eyes)
    ARTIFACT_SEEN = "ARTIFACT_SEEN"
    FINGERPRINT_COMPUTED = "FINGERPRINT_COMPUTED"
    EXTRACTION_PERFORMED = "EXTRACTION_PERFORMED"
    ACCESS_LIMITATION_NOTED = "ACCESS_LIMITATION_NOTED"
    REMOTE_LOOKUP_DECLINED = "REMOTE_LOOKUP_DECLINED"

    # Interpretation Events (Thread)
    TAGS_PROPOSED = "TAGS_PROPOSED"
    ROLES_PROPOSED = "ROLES_PROPOSED"
    RELATION_PROPOSED = "RELATION_PROPOSED"
    CONFLICT_DETECTED = "CONFLICT_DETECTED"
    HYPOTHESIS_NOTED = "HYPOTHESIS_NOTED"

    # Belief Management Events (Spine)
    CONFIDENCE_UPDATED = "CONFIDENCE_UPDATED"
    FRESHNESS_DECAY_APPLIED = "FRESHNESS_DECAY_APPLIED"
    ARTIFACT_SUPERSEDED = "ARTIFACT_SUPERSEDED"

    # Maintenance Events
    ARCHIVE_RECOMMENDED = "ARCHIVE_RECOMMENDED"
    PRUNE_CACHE_RECOMMENDED = "PRUNE_CACHE_RECOMMENDED"
    FILE_ARCHIVED = "FILE_ARCHIVED"

    # Session Events
    SESSION_STARTED = "SESSION_STARTED"
    SESSION_ENDED = "SESSION_ENDED"


@dataclass(frozen=True)
class ValidationError:
    """A single validation error."""

    path: str
    message: str
    value: Any = None


@dataclass
class ValidationResult:
    """Result of validation."""

    valid: bool
    errors: list[ValidationError]

    @classmethod
    def ok(cls) -> "ValidationResult":
        """Return valid result."""
        return cls(valid=True, errors=[])

    @classmethod
    def fail(
        cls, path: str, message: str, value: Any = None
    ) -> "ValidationResult":
        """Return single error result."""
        return cls(
            valid=False,
            errors=[ValidationError(path=path, message=message, value=value)],
        )

    def merge(self, other: "ValidationResult") -> "ValidationResult":
        """Merge another result into this one."""
        if other.valid:
            return self
        return ValidationResult(
            valid=False,
            errors=self.errors + other.errors,
        )


class EventValidator:
    """
    Validates event envelopes and payloads.

    Rules:
    - Envelope has required fields
    - event_type is known
    - Payload matches event_type requirements
    - Types are correct (str, float, dict, etc.)
    """

    # Required envelope fields
    ENVELOPE_REQUIRED = {
        "event_id": str,
        "event_type": str,
        "ts": (int, float),
        "actor": dict,
        "payload": dict,
    }

    # Optional envelope fields
    ENVELOPE_OPTIONAL = {
        "artifact_id": (str, type(None)),
        "confidence": (int, float, type(None)),
        "evidence_refs": list,
        "session_id": (str, type(None)),
    }

    # Actor required fields
    ACTOR_REQUIRED = {
        "module": str,
    }

    # Per-event-type payload schemas
    # Format: {field: (types, required)}
    PAYLOAD_SCHEMAS: dict[str, dict[str, tuple[tuple, bool]]] = {
        "ARTIFACT_SEEN": {
            "artifact_id": ((str,), True),
            "locator": ((str,), True),
            "artifact_kind": ((str,), False),
            "size_bytes": ((int,), False),
            "mtime": ((int, float), False),
        },
        "FINGERPRINT_COMPUTED": {
            "artifact_id": ((str,), True),
            "content_hash": ((str,), True),
            "structure_hash": ((str, type(None)), False),
            "entropy_score": ((int, float, type(None)), False),
        },
        "EXTRACTION_PERFORMED": {
            "artifact_id": ((str,), True),
            "extraction_depth": ((int,), False),
            "extracted_metadata": ((dict,), False),
            "extraction_errors": ((list,), False),
        },
        "ACCESS_LIMITATION_NOTED": {
            "artifact_id": ((str,), True),
            "limitation_type": ((str,), True),
            "reason": ((str,), False),
        },
        "REMOTE_LOOKUP_DECLINED": {
            "url": ((str,), True),
            "reason": ((str,), True),
        },
        "TAGS_PROPOSED": {
            "artifact_id": ((str,), True),
            "tags": ((list,), True),
            "tag_type": ((str,), False),
        },
        "ROLES_PROPOSED": {
            "artifact_id": ((str,), True),
            "roles": ((list,), True),
        },
        "RELATION_PROPOSED": {
            "source_id": ((str,), True),
            "target_id": ((str,), True),
            "relation_type": ((str,), True),
            "directional": ((bool,), False),
        },
        "CONFLICT_DETECTED": {
            "artifact_ids": ((list,), True),
            "conflict_type": ((str,), True),
            "description": ((str,), False),
        },
        "HYPOTHESIS_NOTED": {
            "hypothesis": ((str,), True),
            "supporting_evidence": ((list,), False),
        },
        "CONFIDENCE_UPDATED": {
            "artifact_id": ((str,), True),
            "old_confidence": ((int, float, type(None)), False),
            "new_confidence": ((int, float), True),
            "reason": ((str,), False),
        },
        "FRESHNESS_DECAY_APPLIED": {
            "artifact_id": ((str,), True),
            "decay_factor": ((int, float), True),
        },
        "ARTIFACT_SUPERSEDED": {
            "old_artifact_id": ((str,), True),
            "new_artifact_id": ((str,), True),
            "reason": ((str,), False),
        },
        "ARCHIVE_RECOMMENDED": {
            "artifact_id": ((str,), True),
            "reason": ((str,), True),
            "staleness_days": ((int, float), False),
        },
        "PRUNE_CACHE_RECOMMENDED": {
            "path": ((str,), True),
            "reason": ((str,), True),
            "age_days": ((int, float), False),
        },
        "FILE_ARCHIVED": {
            "original_path": ((str,), True),
            "archive_path": ((str,), True),
        },
        "SESSION_STARTED": {
            "target": ((str,), False),
            "command": ((str,), False),
        },
        "SESSION_ENDED": {
            "duration_ms": ((int, float), False),
            "files_seen": ((int,), False),
            "bytes_accounted": ((int,), False),
            "stopped_reason": ((str, type(None)), False),
        },
    }

    def validate(self, event: dict) -> ValidationResult:
        """
        Validate a complete event.

        Args:
            event: Event dictionary to validate

        Returns:
            ValidationResult with any errors
        """
        result = ValidationResult.ok()

        # Validate envelope
        result = result.merge(self._validate_envelope(event))

        # If envelope is bad, stop here
        if not result.valid:
            return result

        # Validate event_type is known
        event_type = event["event_type"]
        result = result.merge(self._validate_event_type(event_type))

        # Validate actor
        result = result.merge(self._validate_actor(event.get("actor", {})))

        # Validate payload for event type
        if event_type in self.PAYLOAD_SCHEMAS:
            result = result.merge(
                self._validate_payload(event_type, event.get("payload", {}))
            )

        return result

    def _validate_envelope(self, event: dict) -> ValidationResult:
        """Validate envelope structure."""
        result = ValidationResult.ok()

        # Check required fields
        for field, expected_types in self.ENVELOPE_REQUIRED.items():
            if field not in event:
                result = result.merge(
                    ValidationResult.fail(
                        path=field,
                        message=f"Missing required field: {field}",
                    )
                )
            else:
                if not isinstance(expected_types, tuple):
                    expected_types = (expected_types,)
                if not isinstance(event[field], expected_types):
                    result = result.merge(
                        ValidationResult.fail(
                            path=field,
                            message=(
                                f"Expected {expected_types}, "
                                f"got {type(event[field])}"
                            ),
                            value=event[field],
                        )
                    )

        # Check optional fields types
        for field, expected_types in self.ENVELOPE_OPTIONAL.items():
            if field in event and event[field] is not None:
                if not isinstance(expected_types, tuple):
                    expected_types = (expected_types,)
                if not isinstance(event[field], expected_types):
                    result = result.merge(
                        ValidationResult.fail(
                            path=field,
                            message=(
                                f"Expected {expected_types}, "
                                f"got {type(event[field])}"
                            ),
                            value=event[field],
                        )
                    )

        return result

    def _validate_event_type(self, event_type: str) -> ValidationResult:
        """Validate event_type is known."""
        try:
            EventType(event_type)
            return ValidationResult.ok()
        except ValueError:
            return ValidationResult.fail(
                path="event_type",
                message=f"Unknown event type: {event_type}",
                value=event_type,
            )

    def _validate_actor(self, actor: dict) -> ValidationResult:
        """Validate actor structure."""
        result = ValidationResult.ok()

        for field, expected_type in self.ACTOR_REQUIRED.items():
            if field not in actor:
                result = result.merge(
                    ValidationResult.fail(
                        path=f"actor.{field}",
                        message=f"Missing required actor field: {field}",
                    )
                )
            elif not isinstance(actor[field], expected_type):
                result = result.merge(
                    ValidationResult.fail(
                        path=f"actor.{field}",
                        message=(
                            f"Expected {expected_type}, "
                            f"got {type(actor[field])}"
                        ),
                        value=actor[field],
                    )
                )

        return result

    def _validate_payload(
        self,
        event_type: str,
        payload: dict,
    ) -> ValidationResult:
        """Validate payload for specific event type."""
        result = ValidationResult.ok()

        schema = self.PAYLOAD_SCHEMAS.get(event_type, {})

        for field, (expected_types, required) in schema.items():
            if field not in payload:
                if required:
                    result = result.merge(
                        ValidationResult.fail(
                            path=f"payload.{field}",
                            message=(
                                f"Missing required payload field: {field} "
                                f"for event type {event_type}"
                            ),
                        )
                    )
            else:
                value = payload[field]
                if value is not None and not isinstance(value, expected_types):
                    result = result.merge(
                        ValidationResult.fail(
                            path=f"payload.{field}",
                            message=(
                                f"Expected {expected_types}, "
                                f"got {type(value)}"
                            ),
                            value=value,
                        )
                    )

        return result


# Legacy compatibility function
REQUIRED_KEYS = {"event_id", "event_type", "ts", "actor", "payload"}


def validate_event(event: dict) -> bool:
    """
    Legacy validation function.

    For strict validation, use EventValidator class.

    Args:
        event: Event dictionary

    Returns:
        True if valid

    Raises:
        ValueError: If validation fails
    """
    missing = REQUIRED_KEYS - event.keys()
    if missing:
        raise ValueError(f"Missing event keys: {missing}")
    return True


def validate_strict(event: dict) -> ValidationResult:
    """
    Strict validation with detailed errors.

    Args:
        event: Event dictionary

    Returns:
        ValidationResult with all errors
    """
    validator = EventValidator()
    return validator.validate(event)
