# TradeValue database

The PostgreSQL schema is managed by Alembic. `schema.sql` is the frozen input to
the initial migration and must not be edited; future changes belong in new
files under `backend/migrations/versions`. The schema keeps
player identity, performance statistics, and contracts independent. Application
queries or ML dataset builders should join those timelines by player and season;
statistics ingestion must not depend on a player having a contract row.

Conventions:

- NHL seasons are identified by their starting year (`2025` means 2025-26).
- Money is stored as integer cents.
- Percentages are ratios (`0.10` means 10%).
- NHL game types use `1` for preseason, `2` for regular season, and `3` for
  playoffs.
- Source-specific external IDs go in `player_external_ids`; names are never a
  durable ingestion key.
- Raw source payloads and hashes go in `source_records` so imports are auditable
  and replayable.
- `created_at` and `updated_at` are UTC-aware timestamps. The application or a
  migration is responsible for updating `updated_at`.

## Initial setup

From the repository root, install the backend dependencies and create your local
environment file:

```bash
python -m pip install -r backend/requirements-dev.txt
cp backend/.env.example backend/.env
```

Edit `backend/.env` with the PostgreSQL credentials for the database you intend
to populate. The real `.env` file is ignored by Git; `.env.example` documents the
required settings without storing secrets.

`ENV` is required and must be `dev`, `nonprod`, or `prod`. In development, use
the local `DB_*` settings or a URL. Nonprod and prod share the deployed connection
strategy: provide `DATABASE_URL` in each environment, or use the explicitly
scoped `NONPROD_DATABASE_URL` and `PROD_DATABASE_URL` variables. Scoped URLs take
precedence over the shared variable, preventing a local file containing several
URLs from selecting the wrong database.

Apply all migrations from the repository root:

```bash
python -m alembic -c backend/alembic.ini upgrade head
python backend/database/schema_snapshot.py
```

The application does not create or migrate tables during startup.

## Migration development

Migration history must remain linear. Create a revision from the repository
root, implement both directions, and validate it on a disposable PostgreSQL
database:

```bash
python -m alembic -c backend/alembic.ini revision -m "describe the change"
python backend/database/verify_migrations.py
python -m alembic -c backend/alembic.ini upgrade head
python backend/database/schema_snapshot.py --update
python -m alembic -c backend/alembic.ini downgrade -1
python -m alembic -c backend/alembic.ini upgrade head
python backend/database/schema_snapshot.py
```

Review the `schema.snapshot.json` diff before committing it. The snapshot is
generated from PostgreSQL catalogs and covers tables, columns, defaults,
identity properties, constraints, indexes, and enums. This replaces Alembic
autogeneration drift checks because the application intentionally uses reviewed
SQL rather than complete ORM metadata.

Migrations should be backward-compatible with the currently deployed API. Use
expand/contract changes for renamed or removed objects and correct a released
migration with a new forward revision—never edit an applied revision. CI proves
that an empty database upgrades to head, a second upgrade is a no-op, the entire
history can round-trip on disposable PostgreSQL, and the resulting catalog
matches the committed snapshot. CI also publishes the offline upgrade SQL and
actual catalog snapshots as migration diagnostics.

## Adopting an existing database

An existing database created from the original `schema.sql` has no
`alembic_version` row. Back it up or create a Neon branch first, then verify that
its catalog exactly matches the baseline before stamping it:

```bash
DATABASE_URL="$NEON_DIRECT_DATABASE_URL" \
  python backend/database/schema_snapshot.py
DATABASE_URL="$NEON_DIRECT_DATABASE_URL" \
  python -m alembic -c backend/alembic.ini stamp 20260910_0001
DATABASE_URL="$NEON_DIRECT_DATABASE_URL" \
  python -m alembic -c backend/alembic.ini current --check-heads
```

Do not stamp a database when the snapshot comparison fails. Investigate and
reconcile the drift first. The release workflow also runs a preflight that
refuses to migrate application tables without an Alembic revision, preventing
an accidental attempt to replay the baseline over an existing schema.

## Roster status

The initial migration creates `players.roster_status` with these values:

- `ACTIVE`: positively found on a current NHL roster.
- `MINORS`: positively found on a current AHL roster and the NHL roster fetch
  completed successfully.
- `LTIR`: covered by a currently active manual `ltir_overrides` row.
- `UNKNOWN`: complete NHL and AHL fetches found no roster evidence.

LTIR overrides always take precedence. An open-ended override uses a null
`end_date`. Close or delete the override when it no longer applies.

The sync uses the free NHL current-roster API and the public AHL HockeyTech
LeagueStat JSON feed. NHL matching is exclusively by NHL player ID. AHL matching
first uses a stored AHL external ID, then falls back to a unique normalized-name
plus exact-DOB match. Successful fallback matches are saved in
`player_external_ids` for subsequent ID-based syncs.

From `backend/`, run:

```bash
python -m app.ScriptingFiles.FullDataScript.populate_roster_status
```

`AHL_SEASON_ID` can override the AHL feed's current season when its automatic
selection is between seasons.

Limitations of the free-only approach:

- LTIR is manual because neither free feed provides reliable LTIR accounting.
- AHL IDs are not NHL IDs. Players without a stored AHL mapping require both a
  unique name and exact DOB; ambiguous or incomplete identities remain unknown.
- Only positively identified AHL players become `MINORS`. Absence from an NHL
  roster is never sufficient.
- If either feed is incomplete, existing statuses that depend on the missing
  negative evidence are preserved. The command returns exit code `2` so a
  scheduler can alert without corrupting roster state.
