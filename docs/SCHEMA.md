# Artifact Schema (v0)

An Artifact represents a unit of observed existence.

## Identity (immutable)

- artifact_id
- artifact_kind (local | remote | inferred)
- first_seen_at
- last_seen_at

## Source

- source_type (filesystem | git | database | web | api)
- source_locator
- access_scope (read-only | partial | metadata-only)

## Fingerprint

- content_hash (optional)
- structure_hash (optional)
- size_bytes
- entropy_score
- signature_tags

## Extraction

- extraction_depth
- extracted_text_ref (optional)
- extracted_schema
- extracted_metadata
- extraction_errors

## Confidence

- confidence_score
- confidence_reasoning
- evidence_refs
- ambiguity_flags

## Tags

Typed tag groups:
- structural
- semantic
- functional
- temporal
- risk

## Roles (contextual)

- source
- derived
- authoritative
- experimental
- transient

## Relationships

Typed, directional, confidence-weighted relations to other artifacts.

## Provenance (append-only)

- created
- transformed
- copied
- superseded

## Temporal Intelligence

- change_history
- freshness score
- volatility
