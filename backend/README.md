# TradeValue backend API

The backend is a read-only FastAPI service backed by the PostgreSQL schema in
`database/schema.sql`. It implements every route in `docs/api-contract.md`,
including player and team browsing, Hockey Value, contracts, cap estimates,
search, overview aggregates, and comparison.

## Local development

From the repository root:

```bash
python -m pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
psql "$DATABASE_URL" -f backend/database/schema.sql
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

HTTP tests replace the database service and verify response contracts,
validation errors, route coverage, and CORS. A live smoke test still requires a
populated PostgreSQL database.

## Container

```bash
docker build -t tradevalue-api backend
docker run --rm -p 8000:8000 --env-file backend/.env tradevalue-api
```

Production must provide `ENV=nonprod` or `ENV=prod`, a corresponding database
URL, and the deployed frontend origin in `CORS_ORIGINS`. Apply schema changes as
a separate release step; the API never mutates the schema on startup.
