# Backbone Mode (Phase 1)

Atlas operates in **Backbone Mode** during initial deployment.

## What Backbone Mode Means

- **Manual runs only** — no daemon, no scheduler, no cron
- **Filesystem-only** — no remote Eyes (GitRepoEye, WebEye, DatabaseEye disabled)
- **Log-only observability** — salience scoring is computed but NOT acted upon
- **No belief events** — Atlas observes, it does not form beliefs yet
- **Local ledger** — append-only JSONL on local filesystem, no remote sync

## Invariants

1. Every scan **must** stay within budget (files, bytes, depth, time)
2. Every event **must** pass envelope validation before write
3. State is **rebuildable** from ledger at any time (`atlas rebuild`)
4. No network calls unless explicitly `--allow-remote` (disabled in backbone)

## Day 1 Protocol

```bash
# 1. Verify imports
python -c "import atlas; print(atlas.__version__)"

# 2. Dry-run export (safe, no side effects)
python -m atlas.cli export --json

# 3. First scan (bounded, local only)
python -m atlas.cli scan <target> \
  --max-files 50 \
  --max-depth 6 \
  --max-bytes 5000000 \
  --max-time-ms 8000 \
  --no-remote \
  --salience log-only

# 4. Verify post-run state
python -m atlas.cli export --json
```

## What Comes After Backbone

- **Phase 2**: GitRepoEye (local .git only)
- **Phase 3**: DatabaseEye (read-only, connection string required)
- **Phase 4**: RemoteRepoEye + WebEye (with explicit policy)

Each phase is additive. Backbone invariants remain enforced.
