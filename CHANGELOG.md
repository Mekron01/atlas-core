# Changelog

All notable changes to Atlas Core will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2025-01-XX

### Added

#### Core Infrastructure (Phases 1-5)
- Append-only event ledger with JSONL storage
- EventWriter with fsync durability
- EventReader for ledger replay
- Event projection with reducers
- Atomic snapshot write/read

#### Observation Layer (Phases 6-7)
- FilesystemEye for local file observation
- Budget-constrained observation (time, files, bytes, depth)
- Content fingerprinting (SHA-256)

#### Interpretation Layer (Phase 8)
- Tags module for artifact tagging
- Relations module for graph edges
- Conflict detection for contradictory observations

#### Intelligence Layer (Phase 9)
- Confidence engine with evidence weighting
- Salience scoring with configurable weights
- Salience explanations

#### Remote Access (Phase 10)
- RemotePolicy with default-off access
- WebEye for URL observation
- RemoteRepoEye for GitHub repository observation
- Domain allowlisting

#### Maintenance (Phase 11)
- Janitor for staleness analysis
- Archive module for soft archiving
- CLI commands for maintenance

#### Query Acceleration (Phase 12)
- SQLite-based indexes (rebuildable from snapshots)
- IndexBuilder for deterministic rebuilds
- Locator, hash, and graph edge indexing

#### Validation (Phase 13)
- Strict event envelope validation
- Per-event-type payload validation
- EventValidator class with detailed errors
- Optional strict mode in EventWriter

#### Testing & Packaging (Phases 14-15)
- pytest test suite
- pyproject.toml for pip installation
- Version tracking (__version__)
- CLI `version` command

### Design Principles

- **Append-only ledger**: Events never deleted, contradictions create new events
- **Rebuildable views**: Snapshots and indexes are disposable, ledger is truth
- **Budget-constrained**: All observation respects explicit resource limits
- **Remote-off-by-default**: No network access without explicit opt-in
- **No external dependencies**: Pure Python stdlib (sqlite3, json, hashlib, etc.)

## [Unreleased]

### Planned
- Session management improvements
- Git eye for repository structure
- Database eye for schema observation
- Enhanced conflict resolution
- Time-based confidence decay
