# Scan Sessions & Pulses (v0)

Sessions define **bounded execution windows** for Atlas observation.

They give Atlas a heartbeat.

## Why Sessions Exist

Without sessions:
- Scans sprawl
- Budgets blur
- Changes are hard to reason about

Sessions make observation:
- Finite
- Auditable
- Repeatable

## Session Object

A session includes:

- session_id
- start_time
- end_time
- scope (locators, sources)
- budgets
- policies
- diff_mode
- results_summary
- salience_summary

## Diff-First Design

Sessions prioritize change detection:

- Identity diff
- Structure diff
- Semantic diff
- Relationship diff
- Impact diff

Deep scans happen only when justified.

## Progressive Deepening

Typical flow:
1. Shallow scan (wide)
2. Salience ranking
3. Targeted deep scan
4. Conflict verification

## Policies

Sessions may specify:
- ignore/include patterns
- no-internet mode
- no-binary mode
- quiet vs report mode

## Guarantees

Sessions:
- Never mutate history
- Never bypass budgets
- Never suppress conflicts

They only control *when* and *how much* Atlas observes.
