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

The remaining Python modules in this directory and `roster_status/` are
implementation modules used by those commands. Required CI imports every one
of them in a fresh interpreter and compiles the complete backend application.
