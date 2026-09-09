# Hockey Analytics

An NHL analytics project for collecting player and contract data, modeling player value, and translating performance into fair salary-cap value.

## Current Focus

The project is currently building the data foundation for future NHL analytics features, including:

* NHL player data
* Player statistics
* Contracts and cap hits
* NHL / AHL roster status
* LTIR tracking
* Salary-cap calculations
* Future player-value models

## Data Sources

Current and planned sources include:

* NHL
* MoneyPuck
* CapWages
* AHL HockeyTech / LeagueStat

The project prioritizes free or publicly available data sources.

## Tech Stack

* Python
* PostgreSQL
* pytest
* GitHub Actions
* React 19
* TypeScript
* Vite
* TypeScript
* React Router

## Project Structure

```text
Hockey-Analytics/
├── .github/
│   └── workflows/
├── backend/
│   ├── app/
│   ├── database/
│   └── tests/
├── frontend/
│   ├── src/api/
│   ├── components/
│   ├── mocks/
│   └── pages/
├── ml/
└── README.md
```

## Running the Frontend

The frontend currently uses realistic mock valuation data and does not require the backend or database.

```bash
cd frontend
npm install
npm run dev
```

Create a production build with `npm run build` and run lint with `npm run lint`.

## Running the API

The FastAPI backend implements the complete contract in
`docs/api-contract.md`. After configuring PostgreSQL and applying the schema:

```bash
python -m pip install -r backend/requirements-dev.txt
cd backend
uvicorn app.main:app --reload
```

The API listens on `http://localhost:8000`, serves interactive documentation at
`/docs`, and exposes a database-aware health check at `/api/health`. See
`backend/README.md` for frontend cutover, CORS, testing, and container commands.
For production, follow the complete
[Vercel and Neon deployment guide](docs/deployment-vercel-neon.md).

## Database

The PostgreSQL schema is located at:

```text
backend/database/schema.sql
```

Install the development dependencies, copy the environment template, and enter your local
PostgreSQL credentials:

```bash
python -m pip install -r backend/requirements-dev.txt
cp backend/.env.example backend/.env
```

Apply `backend/database/schema.sql` manually before running a loader. The
application uses `ENV=dev`, `ENV=nonprod`, or `ENV=prod` to select its database
configuration. Development can use the individual `DB_*` values. Nonprod and
prod use `DATABASE_URL` or their scoped `NONPROD_DATABASE_URL` /
`PROD_DATABASE_URL` value supplied by the deployment environment. The
application does not create the schema automatically.

## Running the Data Collection

From `backend/`:

```bash
python -m app.ScriptingFiles.FullDataScript.run_all
```

This loads checked-in player/goalie and current-season MoneyPuck data, NHL rosters,
historical NHL season statistics, active CapWages contracts, and the current
schedule, then refreshes roster statuses. Each stage is idempotent and targets
the schema in `backend/database/schema.sql`.

The checked-in team and line aggregate CSVs remain source assets: the current
schema intentionally has player/goalie stat tables but no team- or line-stat
tables.

To run only the roster-status refresh:

```bash
python -m app.ScriptingFiles.FullDataScript.populate_roster_status
```

Run tests with:

```bash
PYTHONPATH=backend pytest
```

The repository targets Python 3.12 and Node.js 24. Python installs use the
checked-in constraints files, and `npm ci` uses the frontend lockfile. To
regenerate the Python locks after changing a direct dependency, install
[`uv`](https://docs.astral.sh/uv/) and run:

```bash
uv pip compile backend/requirements.in --python-version 3.12 --universal --no-annotate --output-file backend/requirements.txt
uv pip compile backend/requirements-dev.txt --python-version 3.12 --universal --no-annotate --output-file constraints.txt
```

Python tests enforce branch coverage and write HTML/XML/LCOV reports under
`coverage/python/`. Frontend coverage is enforced with
`cd frontend && npm run test:coverage`, which writes HTML, Cobertura XML, and
LCOV reports under `frontend/coverage/`. CI uploads both report directories.
The initial Python 3.12 baseline is 46.94% branch-aware aggregate coverage
(48.95% lines and 33.33% branches). The frontend baseline is 74.04% statements,
61.95% branches, 65.55% functions, and 77.35% lines. These exact floors prevent
coverage regressions and should be raised as each subsystem gains tests.

## Branch Workflow

Development follows:

```text
Dev → NonProd → Prod
```

GitHub Actions handles promotion between environments.
See [CI and automatic promotion setup](docs/ci-promotion.md) for the required
GitHub repository settings and rollout sequence.

## Roadmap

### Completed foundation

* PostgreSQL schema and idempotent ingestion pipeline
* FastAPI implementation of the frontend API contract
* React application with a mock/live API switch
* Player-value training and evaluation pipeline
* Reproducible Python 3.12 and Node.js 24 environments
* CI promotion workflow, coverage gates, and Vercel/Neon deployment configuration

### Next milestone: live NonProd vertical slice

1. Provision the NonProd Neon database, apply the schema, and load a validated dataset.
2. Deploy the backend and verify health, seasons, players, teams, contracts, cap, search,
   overview, and comparison endpoints against real data.
3. Deploy the frontend with `VITE_USE_MOCK_API=false`, validate CORS and deep links, and
   complete an end-to-end smoke test.
4. Add live API contract tests for response shapes, null handling, traded-player totals,
   pagination, sorting, and error envelopes.

### Following milestones

1. **Salary-cap accuracy:** implement buried-contract relief, accrued cap space, and LTIR
   pool rules; add scenario-based cap tests.
2. **Data reliability:** improve NHL/AHL roster reconciliation, ingestion observability,
   freshness checks, and failure recovery.
3. **Model integration:** version and publish trained player-value outputs, expose model
   freshness/quality metadata, and validate projections before presenting them as current.
4. **Product depth:** replace remaining development-only messaging, expand player and team
   analytics, and improve comparison workflows.
5. **Quality:** raise backend service/ML and frontend HTTP/search/page coverage above the
   current regression floors as each milestone lands.

## Disclaimer

This is an independent project and is not affiliated with the NHL, AHL, MoneyPuck, CapWages, or their respective organizations.
