# Salience Engine (v0)

Salience determines **what deserves attention**, not what is true.

It is an optional add-on module.

## Core Question

Out of everything Atlas knows:
> What matters *right now*?

## Inputs

- Artifact snapshots
- Event log deltas
- Relationship graph
- Confidence & freshness
- Volatility metadata
- Optional intent context

## Salience Score Components

- Novelty
- Impact
- Risk
- Uncertainty
- Recurrence
- Redundancy
- Stability Penalty

Each component is normalized (0–1) and explainable.

## Tiers

- Tier 0: Silent
- Tier 1: Logged only
- Tier 2: Surfaced
- Tier 3: Interrupt-worthy (rare)

Silence is the default.

## Guarantees

Salience:
- Never changes facts
- Never upgrades confidence
- Never deletes artifacts
- Never forces action

It only allocates attention.

## Explainability

Every salience output includes:
- Total score
- Component breakdown
- Triggering events
- Evidence references

No black boxes.
