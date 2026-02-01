# Atlas Core

Atlas Core is a **universal ingestion, observation, and epistemic ledger system**.

It is not a crawler.
It is not a tagger.
It is not an AI.

Atlas observes artifacts, records what was seen, tracks uncertainty, and preserves provenance over time.  
It is designed to be **honest, auditable, and resilient to change**.

## Core Principles

- Append-only event ledger (truth is never overwritten)
- Explicit uncertainty and confidence
- Provenance-first design
- Rebuildable state (snapshots are projections)
- Silence by default (attention is earned)

## What Atlas Does

- Discovers artifacts (files, repos, databases, remote sources)
- Fingerprints and extracts safely
- Proposes meaning (tags, roles, relations) without asserting truth
- Tracks change, conflict, and decay over time
- Surfaces what matters via optional salience logic

## What Atlas Does NOT Do

- Execute code
- Make plans or decisions
- Generate goals
- Assume correctness
- Hide uncertainty

## Architecture

Atlas is composed of:
- **Spine** – immutable ledger, identity, provenance
- **Eyes** – pluggable scanners (read-only observers)
- **Thread** – meaning proposals (tags, relations)
- **Add-ons** – salience, sessions, explainability (optional)

## Consumers

Atlas Core is designed to be consumed by higher-level systems (e.g. reasoning engines, planners, world models).  
Atlas never depends on its consumers.

## Status

This repository contains the build-ready v0 architecture and reference implementations.

Stability > speed.
