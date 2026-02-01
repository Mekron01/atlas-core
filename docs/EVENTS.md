# Atlas Event Types (v0)

All events are append-only and immutable.

## Observation Events (Eyes)

- ARTIFACT_SEEN
- FINGERPRINT_COMPUTED
- EXTRACTION_PERFORMED
- ACCESS_LIMITATION_NOTED

## Interpretation Events (Thread)

- TAGS_PROPOSED
- ROLES_PROPOSED
- RELATION_PROPOSED
- CONFLICT_DETECTED
- HYPOTHESIS_NOTED

## Belief Management Events (Spine)

- CONFIDENCE_UPDATED
- FRESHNESS_DECAY_APPLIED
- ARTIFACT_SUPERSEDED

## Maintenance Events (future)

- ARCHIVED
- COMPRESSED_INTO_ESSENCE

## Event Rules

- Events never delete other events
- Contradictions create new events
- Confidence changes are explicit
- History is preserved forever
