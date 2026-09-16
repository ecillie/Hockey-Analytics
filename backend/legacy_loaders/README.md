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
