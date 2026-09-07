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

## Database

The PostgreSQL schema is located at:

```text
backend/database/schema.sql
```

Install the dependencies, copy the environment template, and enter your local
PostgreSQL credentials:

```bash
python -m pip install -r backend/requirements.txt
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
pytest
```

## Branch Workflow

Development follows:

```text
Dev → NonProd → Prod
```

GitHub Actions handles promotion between environments.

## Roadmap

* Improve roster-status tracking
* Build salary-cap calculations
* Expand automated testing
* Add more NHL data
* Build player and team analytics
* Develop player-value models

## Disclaimer

This is an independent project and is not affiliated with the NHL, AHL, MoneyPuck, CapWages, or their respective organizations.
