# TradeValue backend API

The backend is a read-only FastAPI service backed by an Alembic-managed
PostgreSQL schema. It implements every route in `docs/api-contract.md`,
including player and team browsing, Hockey Value, contracts, cap estimates,
search, overview aggregates, and comparison.

## Local development

From the repository root:

```bash
python -m pip install -r backend/requirements-dev.txt
cp backend/.env.example backend/.env
python -m alembic -c backend/alembic.ini upgrade head
cd backend
uvicorn app.main:app --reload
```

If you use the individual `DB_*` variables instead of `DATABASE_URL`, apply the
schema with the equivalent connection arguments. The API is available at
`http://localhost:8000`; interactive OpenAPI documentation is at
`http://localhost:8000/docs`.

Health check:

```bash
curl http://localhost:8000/api/health
```

The health endpoint checks database connectivity. A database failure returns a
shared `DATABASE_UNAVAILABLE` error with HTTP 503.

Hockey Value is calculated from the canonical all-situations advanced-stat row
using the repository's position/season replacement-level definition. A stored
next-season projection is returned only when a prediction payload explicitly
contains `predicted_hockey_value`; otherwise that field remains `null`.

## Frontend connection

Create `frontend/.env.local`:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
VITE_USE_MOCK_API=false
```

Set `CORS_ORIGINS` in `backend/.env` to a comma-separated list of actual browser
origins. Do not use `*` when credentials are introduced later.

## Tests

```bash
PYTHONPATH=backend pytest -q backend/tests ml/tests
```

HTTP and service tests verify response contracts, validation errors, route
coverage, CORS, and service-layer branching. PostgreSQL integration tests run
when `TEST_DATABASE_URL` is set; the target database must be disposable because
the tests truncate application tables. CI provisions a dedicated PostgreSQL
service, migrates an empty database to Alembic head, verifies the catalog and a
downgrade/re-upgrade cycle, then runs the integration suite automatically.

The ingestion gate uses small checked-in MoneyPuck and CapWages-shaped fixtures;
it never calls live NHL, MoneyPuck, or CapWages services. It validates source
schemas and required values, season coverage, player/season/stat deduplication,
idempotent typed-field upserts, salary-cap reference data, foreign-key behavior,
and transaction rollback after a failed batch.

Every schema-native ingestion stage records `running`, `succeeded`, `failed`, or
`cancelled` state in `ingestion_runs`. PostgreSQL advisory locks reject a second
copy of the same stage while one is active. Successful rows are upserted and
source rows absent from a later snapshot are deliberately retained; loaders do
not infer deletion from absence. MoneyPuck coverage, volume, and duplicate-ratio
thresholds, NHL roster and schedule minimums, NHL stat invariants, and CapWages
profile-success thresholds fail before writes. An incomplete roster feed rolls
back the entire roster-status update.

The production defaults expect MoneyPuck seasons 2008 through 2025, at least 30
NHL teams, 500 active NHL players, 100 regular-season schedule games, and a 98%
CapWages profile success rate. Tests override only the volume values so tiny
fixtures exercise the identical validation and persistence paths.

To run the integration tests against a dedicated local test database:

```bash
createdb tradevalue_test
DATABASE_URL=postgresql://localhost/tradevalue_test \
  python -m alembic -c backend/alembic.ini upgrade head
TEST_DATABASE_URL=postgresql://localhost/tradevalue_test \
  PYTHONPATH=backend pytest -q backend/tests/test_postgres_integration.py
```

## Container

```bash
docker build -t tradevalue-api backend
docker run --rm -p 8000:8000 --env-file backend/.env tradevalue-api
```

Production must provide `ENV=nonprod` or `ENV=prod`, a corresponding database
URL, and the deployed frontend origin in `CORS_ORIGINS`. Apply schema changes as
a separate release step; the API never mutates the schema on startup.

## Vercel + Neon deployment

Import this repository into Vercel twice. Configure the API project with Root
Directory `backend` and the web project with Root Directory `frontend`.
`vercel.json` in each directory pins the framework and routing behavior.

For the API project:

1. Add Neon from the Vercel Marketplace and connect it only to the API project,
   or add an existing Neon pooled connection string as `DATABASE_URL`.
2. Set `ENV=prod`.
3. Set `CORS_ORIGINS` to the exact production frontend origin, with no trailing
   slash, such as `https://tradevalue.example.com`.
4. Optionally set `CORS_ORIGIN_REGEX` to a project-specific full-match regex for
   preview URLs. Avoid a regex that permits every `vercel.app` deployment.
5. Deploy and confirm `/api/health` returns `{"status":"ok"}`.

Use Neon's pooled `-pooler` connection string for the running API. The app keeps
its local SQLAlchemy pool deliberately small so horizontally scaled Functions do
not create excessive client connections. Keep a direct, non-pooled Neon URL for
schema application and ingestion jobs; do not expose either URL to the frontend.

Apply migrations using the direct connection before the API deployment:

```bash
DATABASE_URL="$NEON_DIRECT_DATABASE_URL" \
  python -m alembic -c backend/alembic.ini upgrade head
```

The repository's manually dispatched `Database migration` workflow performs
this as a separately gated environment operation. Configure a direct,
non-pooled `DATABASE_URL` secret in both GitHub `nonprod` and `prod`
Environments, and require reviewers for the `prod` Environment.

For the frontend project, set these variables in both Production and Preview:

```dotenv
VITE_USE_MOCK_API=false
VITE_API_BASE_URL=https://your-api-project.vercel.app
```

Redeploy the frontend after changing either `VITE_` value because Vite embeds
them into the browser bundle at build time. The frontend's Vercel rewrite keeps
React Router URLs working when opened or refreshed directly.

The checked-in ingestion CSVs and scripts are excluded from the Vercel Function.
Run ingestion from a trusted machine or a separate job using
`requirements-dev.txt` and the direct Neon database URL.
