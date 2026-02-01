# Atlas Core Architecture

## Layered Design

Atlas is intentionally split into strict layers:

### 1. Atlas Spine
Responsibilities:
- Event log (append-only)
- Artifact identity
- Fingerprinting
- Provenance chains
- Change history
- Confidence tracking

Rules:
- Never deletes events
- Never overwrites history
- Never infers intent

### 2. Atlas Eyes
Responsibilities:
- Observe one source type
- Enumerate artifacts
- Extract safely within budgets
- Emit observation events only

Rules:
- Read-only
- No execution
- No global state
- No cross-eye communication

### 3. Atlas Thread
Responsibilities:
- Propose tags, roles, relations
- Detect conflicts
- Form hypotheses

Rules:
- Proposals only
- Can be wrong
- Confidence required

### 4. Add-On Modules
Optional layers:
- Salience Engine (what matters)
- Session/Pulse Planner (bounded scans)
- Explainability
- Intent Hooks
- Remote (internet) Eyes

Removing add-ons never breaks the core.

## Data Flow

Eyes → Events → Ledger → Projection → Snapshots → Consumers

The ledger is the source of truth.
Everything else is rebuildable.

## Failure Model

- Partial reads are allowed
- Conflicts are recorded, not resolved
- Missing access is data, not error
- Crashes do not corrupt history
