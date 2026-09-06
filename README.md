# Hockey Analytics

A backend-focused NHL analytics project for collecting and organizing player, contract, roster, and salary-cap data.

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

## Project Structure

```text
Hockey-Analytics/
├── .github/
│   └── workflows/
├── backend/
│   ├── app/
│   ├── database/
│   └── tests/
└── README.md
```

## Database

The PostgreSQL schema is located at:

```text
backend/database/schema.sql
```

Database connection:

```bash
DATABASE_URL=postgresql://user:password@localhost:5432/hockey_analytics
```

## Running the Data Pipeline

From `backend/`:

```bash
python -m app.ScriptingFiles.FullDataScript.run_all
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
