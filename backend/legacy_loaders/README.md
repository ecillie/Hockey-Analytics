# Quarantined legacy loaders

These files are retained as historical recovery references. They document how
older TradeValue datasets were fetched and transformed, but they are not part
of the supported application or CI import surface.

Do not run them unchanged:

- most import the removed `app.models` ORM layer;
- their table mappings predate the current schema-native ingestion pipeline;
- several call live upstream services and use obsolete seasons or assumptions;
- the empty `save_previous_games_stats.py` file is retained only to preserve
  the complete historical loader set.

For reconstruction, port any still-useful source-specific logic into
`app/ScriptingFiles/FullDataScript/ingestion.py`, retaining its validation,
transaction, idempotency, and run-tracking guarantees.

These source files are not a database backup. Protect hosted data with actual
PostgreSQL backups and a tested restore procedure. A backup is only considered
usable after it has been restored into a disposable database and validated.

The historical NHL basic-stat loader now reduces the NHL API's chronological
comma-separated `teamAbbrevs` value to its final abbreviation. If data from the
retired ORM schema is translated into the current schema, run the supported
set-based repair afterward so those values become normalized season-ending
assignments:

```bash
PYTHONPATH=backend DATABASE_URL=postgresql://... \
  python backend/database/backfill_team_stints.py --apply
```

The repair never overwrites an existing `player_team_stints` season. It prefers
an NHL team-scoped row when one exists and otherwise uses MoneyPuck's canonical
season team, which represents the final team for a traded player's aggregate
season row.
