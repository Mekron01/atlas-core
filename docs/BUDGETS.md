# Atlas Budgets (v0)

Budgets are hard limits that prevent Atlas from becoming noisy, slow, or dangerous.

Budgets are enforced at the **Eye level** and are non-negotiable.

## Purpose

Budgets exist to:
- Prevent runaway scans
- Limit resource consumption
- Protect sensitive data
- Enforce bounded observation
- Keep Atlas predictable

Failure to fully observe is **data**, not error.

## Budget Object

A budget is passed to every Eye during observation.

### Core Fields

- max_time_ms  
- max_artifacts  
- max_bytes_per_artifact  
- max_total_bytes  
- max_depth  
- max_concurrency  

### Optional Fields

- allow_binary_extraction (bool)
- allow_sampling (bool)
- allow_remote_access (bool)
- max_remote_calls
- max_text_chars

## Budget Behavior Rules

- Budgets are **hard stops**
- Partial extraction is allowed
- Budget exhaustion emits ACCESS_LIMITATION_NOTED
- No retries without a new session

## Default Budget Profiles

### Shallow Scan
- Fast
- Wide
- Low risk

### Deep Scan
- Narrow
- Expensive
- High confidence

### Audit Scan
- Schema-only
- No content sampling
- Provenance-focused

## Non-Goals

Budgets do NOT:
- Decide importance
- Override confidence rules
- Affect truth semantics

They only limit *how much* Atlas can observe in one pulse.
