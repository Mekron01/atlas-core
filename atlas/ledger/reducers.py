"""
Atlas Projection Reducers

Pure functions that consume event iterables and produce state.
No I/O, no side effects, deterministic.
"""

from typing import Any, Iterable


def project_artifacts(events: Iterable[dict]) -> dict[str, dict]:
    """
    Project events into artifact state keyed by artifact_id.

    Tracks per artifact:
    - last_seen_at: timestamp of most recent observation
    - locator: latest known path/URI
    - fingerprint: latest content hash
    - extraction: latest extraction summary (if present)
    - confidence: last known confidence score

    Args:
        events: Iterable of event dicts

    Returns:
        Dict mapping artifact_id to artifact state
    """
    artifacts: dict[str, dict] = {}

    for event in events:
        artifact_id = event.get("artifact_id")
        # Also check payload if not found at root level
        if not artifact_id:
            artifact_id = event.get("payload", {}).get("artifact_id")
        if not artifact_id:
            continue

        event_type = event.get("event_type", "")
        ts = event.get("ts")
        payload = event.get("payload", {})

        # Initialize artifact state if new
        if artifact_id not in artifacts:
            artifacts[artifact_id] = {
                "artifact_id": artifact_id,
                "last_seen_at": None,
                "locator": None,
                "fingerprint": None,
                "extraction": None,
                "confidence": None,
            }

        state = artifacts[artifact_id]

        # Update last_seen_at for any event
        if ts is not None:
            if state["last_seen_at"] is None or ts > state["last_seen_at"]:
                state["last_seen_at"] = ts

        # Handle known event types
        if event_type == "ARTIFACT_SEEN":
            _reduce_artifact_seen(state, payload, event)

        elif event_type == "ARTIFACT_OBSERVED":
            _reduce_artifact_observed(state, payload, event)

        elif event_type == "FINGERPRINT_COMPUTED":
            _reduce_fingerprint(state, payload)

        elif event_type == "ARTIFACT_CONTENT_EXTRACTED":
            _reduce_extraction(state, payload)
        
        elif event_type == "EXTRACTION_PERFORMED":
            _reduce_extraction(state, payload)

        elif event_type == "CONFIDENCE_UPDATED":
            _reduce_confidence(state, payload, event)

        # Unknown event types are safely ignored

    return artifacts


def _reduce_artifact_seen(
    state: dict, payload: dict, event: dict
) -> None:
    """Reduce ARTIFACT_SEEN event."""
    # Support both "path" and "locator" for location
    if "path" in payload:
        state["locator"] = payload["path"]
    elif "locator" in payload:
        state["locator"] = payload["locator"]
    
    if "content_hash" in payload:
        state["fingerprint"] = payload["content_hash"]
    if "confidence" in event:
        state["confidence"] = event["confidence"]
    
    # Store size_bytes if present in payload
    if "size_bytes" in payload:
        state["size_bytes"] = payload["size_bytes"]


def _reduce_artifact_observed(
    state: dict, payload: dict, event: dict
) -> None:
    """Reduce ARTIFACT_OBSERVED event."""
    if "locator" in payload:
        state["locator"] = payload["locator"]
    if "fingerprint" in payload:
        state["fingerprint"] = payload["fingerprint"]
    if "confidence" in event:
        state["confidence"] = event["confidence"]


def _reduce_fingerprint(state: dict, payload: dict) -> None:
    """Reduce FINGERPRINT_COMPUTED event."""
    if "hash" in payload:
        state["fingerprint"] = payload["hash"]
    elif "fingerprint" in payload:
        state["fingerprint"] = payload["fingerprint"]
    elif "content_hash" in payload:
        state["fingerprint"] = payload["content_hash"]


def _reduce_extraction(state: dict, payload: dict) -> None:
    """Reduce ARTIFACT_CONTENT_EXTRACTED or EXTRACTION_PERFORMED event."""
    extraction = {}
    
    # Handle test event structure
    if "extraction_depth" in payload:
        extraction["depth"] = payload["extraction_depth"]
    if "extracted_metadata" in payload:
        extraction["metadata"] = payload["extracted_metadata"]
    
    # Handle original event structure
    if "content_type" in payload:
        extraction["content_type"] = payload["content_type"]
    if "size" in payload:
        extraction["size"] = payload["size"]
    if "summary" in payload:
        extraction["summary"] = payload["summary"]
    if "symbols" in payload:
        extraction["symbols"] = payload["symbols"]
    
    if extraction:
        state["extraction"] = extraction


def _reduce_confidence(
    state: dict, payload: dict, event: dict
) -> None:
    """Reduce CONFIDENCE_UPDATED event."""
    if "new_confidence" in payload:
        state["confidence"] = payload["new_confidence"]
    elif "confidence" in event:
        state["confidence"] = event["confidence"]


def project_relations(events: Iterable[dict]) -> dict[str, list[dict]]:
    """
    Project events into relation state.

    Returns dict mapping source artifact_id to list of relations.
    """
    relations: dict[str, list[dict]] = {}

    for event in events:
        event_type = event.get("event_type", "")

        if event_type != "RELATION_PROPOSED":
            continue

        payload = event.get("payload", {})
        source = payload.get("source_id")
        target = payload.get("target_id")
        relation_type = payload.get("relation_type")
        confidence = event.get("confidence", payload.get("confidence"))

        if not source or not target or not relation_type:
            continue

        if source not in relations:
            relations[source] = []

        relations[source].append({
            "target_id": target,
            "relation_type": relation_type,
            "confidence": confidence,
            "event_id": event.get("event_id"),
        })

    return relations


def project_tags(events: Iterable[dict]) -> dict[str, list[dict]]:
    """
    Project events into tag state.

    Returns dict mapping artifact_id to list of proposed tags.
    """
    tags: dict[str, list[dict]] = {}

    for event in events:
        event_type = event.get("event_type", "")

        if event_type != "TAGS_PROPOSED":
            continue

        artifact_id = event.get("artifact_id")
        payload = event.get("payload", {})
        proposed_tags = payload.get("tags", [])
        confidence = event.get("confidence", payload.get("confidence"))

        if not artifact_id:
            continue

        if artifact_id not in tags:
            tags[artifact_id] = []

        for tag in proposed_tags:
            tags[artifact_id].append({
                "tag": tag,
                "confidence": confidence,
                "event_id": event.get("event_id"),
            })

    return tags


def project_conflicts(events: Iterable[dict]) -> list[dict]:
    """
    Project events into conflict list.

    Returns list of detected conflicts.
    """
    conflicts: list[dict] = []

    for event in events:
        event_type = event.get("event_type", "")

        if event_type != "CONFLICT_DETECTED":
            continue

        payload = event.get("payload", {})

        conflicts.append({
            "conflict_id": event.get("event_id"),
            "artifact_ids": payload.get("artifact_ids", []),
            "conflict_type": payload.get("conflict_type"),
            "description": payload.get("description"),
            "detected_at": event.get("ts"),
        })

    return conflicts


def aggregate_state(events: Iterable[dict]) -> dict[str, Any]:
    """
    Full state aggregation from events.

    Consumes events once and produces complete state.
    """
    # Collect all events (must materialize for multiple passes)
    event_list = list(events)

    return {
        "artifacts": project_artifacts(event_list),
        "relations": project_relations(event_list),
        "tags": project_tags(event_list),
        "conflicts": project_conflicts(event_list),
    }
