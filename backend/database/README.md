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

To run the complete full-data population sequence, including roster status, use:

```bash
python -m app.ScriptingFiles.FullDataScript.run_all
```

The full runner loads players and contracts before statistics because statistics
must be associated with an existing player and the legacy loaders currently use
contract-season matching.

Configure the database with `DATABASE_URL`, or with the existing `DB_USER`,
`DB_PASSWORD`, `DB_HOST`, `DB_PORT`, and `DB_NAME` variables. `AHL_SEASON_ID`
can override the AHL feed's current season when its automatic selection is
between seasons.

Limitations of the free-only approach:

- LTIR is manual because neither free feed provides reliable LTIR accounting.
- AHL IDs are not NHL IDs. Players without a stored AHL mapping require both a
  unique name and exact DOB; ambiguous or incomplete identities remain unknown.
- Only positively identified AHL players become `MINORS`. Absence from an NHL
  roster is never sufficient.
- If either feed is incomplete, existing statuses that depend on the missing
  negative evidence are preserved. The command returns exit code `2` so a
  scheduler can alert without corrupting roster state.
