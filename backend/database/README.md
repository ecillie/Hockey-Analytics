# TradeValue database

The complete PostgreSQL definition for the revamped backend is in `schema.sql`.
Run that file manually against an empty database to create the schema. It keeps
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
- `created_at` and `updated_at` are UTC-aware timestamps. The application or
  future migration framework is responsible for updating `updated_at`.

This directory is intentionally migration-tool agnostic. Once the initial schema
has been deployed, future database changes should be introduced as migrations.

## Initial setup

From the repository root, install the backend dependencies and create your local
environment file:

```bash
python -m pip install -r backend/requirements.txt
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

Apply `backend/database/schema.sql` manually to an empty PostgreSQL database.
The Python database module only connects to and verifies that schema; it does not
create tables.

## Roster status

`schema.sql` creates `players.roster_status` with these values:

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
