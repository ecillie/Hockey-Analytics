# Supported ingestion entrypoints

The schema-native ingestion pipeline replaces the former ORM-based `save_*`
scripts. Those scripts depend on the removed `app.models` module and are kept
under `backend/legacy_loaders/` as recovery references. They are intentionally
outside the importable application tree and are not supported entrypoints.

Supported commands, run from `backend/`, are:

```bash
python -m app.ScriptingFiles.FullDataScript.run_all
python -m app.ScriptingFiles.FullDataScript.populate_roster_status
```

`run_all` performs the full idempotent load and then refreshes roster status.
`populate_roster_status` is the supported standalone roster-status refresh.
Alembic must be at head before either command runs.

For databases populated before season-ending team assignments were persisted,
preview and apply the idempotent set-based repair from the repository root:

```bash
PYTHONPATH=backend DATABASE_URL=postgresql://localhost/hockey_analytics_dev \
  python backend/database/backfill_team_stints.py
PYTHONPATH=backend DATABASE_URL=postgresql://localhost/hockey_analytics_dev \
  python backend/database/backfill_team_stints.py --apply
```

The remaining Python modules in this directory and `roster_status/` are
implementation modules used by those commands. Required CI imports every one
of them in a fresh interpreter and compiles the complete backend application.
# Historical contract gap filling

The supported historical contract stage is `capspace.py`. It selects NHL
regular-season player-seasons with no `contract_seasons` coverage and resolves
the player's NHL external ID. CapSpace is queried first by NHL ID. When it has
no contract covering the missing seasons, the stage tries a bounded CapWages
profile fallback. Newer CapWages profiles must carry the same NHL ID; legacy
profiles without that field must match the canonical name and slug and have an
NHL stats season overlapping the missing-season target. Each source keeps its
own provenance. Auxiliary buyout, termination-fee, and cap-recapture table
sections are excluded from the signed contract's season rows.

Run locally after applying migrations:

```bash
PYTHONPATH=backend ENV=dev DATABASE_URL=postgresql://... \
  python -m app.ScriptingFiles.FullDataScript.capspace --dry-run
PYTHONPATH=backend ENV=dev DATABASE_URL=postgresql://... \
  python -m app.ScriptingFiles.FullDataScript.capspace --apply --nhl-id 8467514 --force
```

The loader is advisory-lock protected, source-provenanced, idempotent, and
capped at eight workers (four by default). It fetches and commits bounded
batches (100 players by default), uses PostgreSQL bulk inserts for source
snapshots and new contract-season rows, and retains prior committed batches if
a later batch fails. Override the batch size with `--batch-size`; smaller
batches reduce retry cost, while larger batches reduce transaction overhead.
Source failures retain the last-good database state. CapWages slug guesses are
bounded: a missing base slug is not followed by guaranteed-failing numbered
guesses, while a same-name identity mismatch can try `-1` through `-3`. Use
`coverage_report()` or the command's metrics to measure remaining gaps;
residual gaps can represent missing NHL IDs, profiles absent from both sources,
absent source seasons, or a reconciliation conflict. Neither source is claimed
to provide complete historical coverage.

The normal `run_all` order is current/recent contract ingestion, historical
two-source gap filling, then downstream schedule loading. The legacy contract
scripts are recovery references and are not part of this pipeline.
