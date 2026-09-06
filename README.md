# TradeValue - NHL Contract Value Prediction

A full-stack web application that predicts NHL player contract values using machine learning. The application scrapes player data, contract information, and statistics from public sources, stores them in a PostgreSQL database, and uses ML models to predict contract cap hits based on player performance metrics.

## Features

- **Player Database**: Browse and search through NHL players with their statistics and contract information
- **Contract Analysis**: View detailed contract information including cap hits, duration, and total value
- **Actual vs expected by year**: For each contract year, compare **actual** cap hit (from saved salary rows) to **expected** cap hit from the ML model using **that season’s** advanced stats (see [Contract predictions](#contract-predictions-actual-vs-expected) below)
- **ML Predictions**: Train and run models (forwards, defensemen, goalies) on advanced metrics; optional simple prediction API for basic stat inputs
- **Data Scraping**: Automated data collection from CapWages and the NHL API (basic stats, advanced skater/goalie stats, contracts, salaries)
- **Web Interface**: React frontend with Vite

## Tech Stack

### Backend
- **FastAPI** - Modern Python web framework
- **PostgreSQL** - Relational database
- **SQLAlchemy** - ORM for database operations
- **scikit-learn** - Machine learning models
- **pandas** - Data manipulation and analysis
- **Requests** - HTTP library for web scraping

### Frontend
- **React** - UI library
- **Vite** - Build tool and dev server
- **React Router** - Client-side routing
- **Axios** - HTTP client for API calls

### Infrastructure
- **Docker** - Containerization
- **Docker Compose** - Multi-container orchestration

## Project Structure

```
TradeValue/
├── backend/
│   ├── app/
│   │   ├── ml/                    # Machine learning pipeline
│   │   │   ├── data/              # Dataset building and feature engineering
│   │   │   ├── training/          # Model training scripts
│   │   │   ├── inference/         # Prediction logic
│   │   │   └── artifacts/         # Trained models
│   │   ├── routers/               # API route handlers
│   │   ├── ScriptingFiles/        # Data scraping scripts
│   │   ├── config.py              # Configuration
│   │   ├── database.py            # Database setup
│   │   ├── models.py              # SQLAlchemy models
│   │   └── main.py                # FastAPI application
│   ├── tests/                     # Pytest suite (API, ML, config/database)
│   ├── Dockerfile
│   ├── pytest.ini
│   ├── .coveragerc
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/            # React components
│   │   │   ├── common/           # Reusable UI components
│   │   │   ├── players/          # Player-related components
│   │   │   ├── contracts/        # Contract-related components
│   │   │   └── Layout/           # Layout components
│   │   ├── pages/                # Page components
│   │   ├── services/             # API service layer
│   │   ├── utils/                # Utility functions
│   │   └── config/               # Configuration
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml
└── README.md
```

## Database Schema

Core tables include (among others):

### player_info
Stores basic player information:
- `id` (Primary Key)
- `firstname`, `lastname`
- `team`
- `position`
- `age`

### contracts
Stores contract details:
- `id` (Primary Key)
- `player_id` (Foreign Key → player_info.id)
- `team`, `start_year`, `end_year`, `duration`
- `cap_hit` (target variable for ML models)
- `rfa`, `elc` (boolean flags)
- `cap_pct`, `total_value`

### basic_player_stats
Stores player statistics by season:
- `id` (Primary Key)
- `player_id` (Foreign Key → player_info.id)
- `contract_id` (Foreign Key → contracts.id)
- `season`, `playoff` (boolean), `team`
- `gp`, `goals`, `assists`, `points`
- `plus_minus`, `pim`, `shots`, `shootpct`

### player_salaries
Per-player, per-contract-year salary rows (actual cap hit for a given NHL season year), used as ML labels and for the “actual” column in contract predictions:
- Links to `player_id`, `contract_id`, and a `year` (season start year, e.g. `2023` for 2023–24)
- `cap_hit`, optional flags such as **ELC slide** (`is_slide`) where applicable

### Advanced stats (skaters / goalies)
The ML pipeline and `/contract-predictions` use **`advanced_skater_stats`** and **`advanced_goalie_stats`** (joined by `player_id`, `contract_id`, `season`, `situation`, `playoff`). Goalie inference also uses **`basic_goalie_stats`** where present. Populate these with the scripting modules under `backend/app/ScriptingFiles/` (see [Data Collection](#data-collection)).

## Setup

### Prerequisites

- Docker and Docker Compose installed
- PostgreSQL database (can run locally or use Docker)
- Node.js 20+ (for local frontend development)
- Python 3.11+ (for local backend development)

### Environment Variables

Variables are read in `backend/app/config.py` (`DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME`). The app loads **`backend/.env`** via `python-dotenv`. `DB_USER` and `DB_NAME` are required. If `DB_PASSWORD` is unset or empty, the database URL is built **without** a password segment (useful only if your Postgres accepts that connection mode).

- **Docker Compose**: Put credentials in a **project root** `.env` file so Compose can substitute `${DB_USER}`, `${DB_PASSWORD}`, and `${DB_NAME}` into the backend service environment (see `docker-compose.yml`). The backend container also receives `DB_HOST=host.docker.internal` so it can reach PostgreSQL on the host machine.
- **Local backend** (`uvicorn` on your machine): Use **`backend/.env`** with the same keys. For local runs, `DB_HOST=localhost` is typical. If `DB_HOST` is `host.docker.internal` and you are not in Docker, `config.py` rewrites it to `localhost`.

Example:

```env
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_HOST=localhost
DB_PORT=5432
DB_NAME=your_database_name
```

### Running with Docker

1. Clone the repository:
```bash
git clone <repository-url>
cd TradeValue
```

2. Create `.env` file with database credentials (see above)

3. Start the services:
```bash
docker-compose up --build
```

The application will be available at:
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

### Local Development Setup

#### Backend

1. Navigate to backend directory:
```bash
cd backend
```

2. Create a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create `.env` file in backend directory with database credentials

5. Initialize database:
```bash
python3 -c "from app.database import init_db; init_db()"
```

6. Run the development server:
```bash
uvicorn app.main:app --reload
```

#### Frontend

1. Navigate to frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Run the development server:
```bash
npm run dev
```

## Data Collection

### Scraping Players

Scrape active players from CapWages:
```bash
cd backend
python3 -m app.ScriptingFiles.save_players_to_db
```

### Scraping Contracts

Scrape contract data for all players:
```bash
python3 -m app.ScriptingFiles.save_contracts_to_db
```

### Scraping Statistics

Scrape player statistics from NHL API:
```bash
python3 -m app.ScriptingFiles.save_basic_player_stats
```

### Building Player Salaries (Contract-Year)

Creates `player_salaries` rows for each contract and each contract-year (used as ML labels and for “actual” cap hit in the predictions UI/API):
```bash
cd backend
python3 -m app.ScriptingFiles.save_individual_contract_years
```

### Advanced statistics (skaters / goalies)

These populate `advanced_skater_stats` / `advanced_goalie_stats` (and related basic goalie stats) for model training and per-year predictions:

```bash
cd backend
python3 -m app.ScriptingFiles.save_skater_advanced_stats
python3 -m app.ScriptingFiles.save_goalie_advanced_stats
```

Note: The NHL API has rate limits. The scripts include delays and retry logic to handle this.

### Roster-status sync

The revamped backend supports the salary-cap roster classifications `ACTIVE`,
`MINORS`, `LTIR`, and `UNKNOWN`. It uses the free NHL current-roster API and the
public AHL HockeyTech LeagueStat feed; it does not infer a minor-league assignment
merely because a player is absent from an NHL roster. LTIR is maintained through
manual date-ranged overrides.

After manually applying `backend/database/schema.sql`, populate roster statuses
from `backend/`:

```bash
python -m app.ScriptingFiles.FullDataScript.populate_roster_status
```

See [`backend/database/README.md`](backend/database/README.md) for matching,
failure-handling, LTIR override, and configuration details.

To execute the entire full-data load, including roster classification, use:

```bash
python -m app.ScriptingFiles.FullDataScript.run_all
```

## Machine Learning Pipeline

### Training Models

Train models for forwards and defensemen:
```bash
cd backend
python3 -m app.ml.training.train_player_model
```

This will:
- Load player/contract/stats/salary data from PostgreSQL
- Build one training row per **non-ELC contract** aligned to the contract **start year**
- Use `player_salaries.cap_hit` as the label (`log_cap_hit = log1p(cap_hit)`)
- Train separate models:
- `forward_model`
- `defenseman_model`
- `goalie_model`
- Save models to `backend/app/ml/artifacts/`

Dataset joins are in `backend/app/ml/data/dataset_builder.py`, and feature engineering is in `backend/app/ml/data/features.py`.

### Evaluating Models

`evaluate_model()` returns metrics (it does not print by default). To print results:
```bash
cd backend
python3 -c "from app.ml.training.evaluate import evaluate_model; print('Forward:', evaluate_model('forward_model')); print('Defenseman:', evaluate_model('defenseman_model')); print('Goalie:', evaluate_model('goalie_model'))"
```

### Contract predictions (actual vs expected)

`GET /api/players/{player_id}/contract-predictions` returns one row per salary year with:

| Field | Meaning |
|--------|---------|
| `actual_cap_hit` | From `player_salaries.cap_hit` for that `(player_id, contract_id, year)` |
| `expected_cap_hit` | ML prediction using **advanced stats for `season == year`** (same contract). Contract context (`rfa`, `duration`, etc.) and `player.age` follow the same pattern as training inference; rate-style features reflect **that season’s** performance. |
| `is_slide` | ELC slide years: `expected_cap_hit` is `0` by convention |

**Fallback**: If there is no advanced-stats row for that season, or prediction fails (e.g. very low ice time filtered out), the API uses the **signing-year** prediction (`season == contract.start_year`). If that is also unavailable, `expected_cap_hit` is `0`.

Training still builds **one row per contract** at signing (see below); per-year expected values are **inference-only** and are best interpreted as exploratory “market value from that season’s numbers,” not a separately retrained model.

### Making Predictions

Use the prediction API endpoint or the web interface to make predictions based on player statistics.

## API Endpoints

### Players
- `GET /api/players` - Get all players
- `GET /api/players/{id}` - Get player by ID
- `GET /api/players/search` - Search players (query params: name, team, position)

### Contracts
- `GET /api/players/contracts` - Get all contracts
- `GET /api/players/contracts/{id}` - Get contract by ID
- `GET /api/players/{player_id}/contracts` - Get contracts for a player

### Contract Predictions
- `GET /api/players/{player_id}/contract-predictions` - Actual vs expected cap hit by year

### Statistics
- `GET /api/players/{player_id}/stats` - Get player statistics (query params: season, team, playoff)

### ML/Predictions
- `POST /api/ml/predict` - Predict contract value from **advanced** stat fields (see `PredictionRequest` in `backend/app/schemas.py`): required `position` (`forward`, `defenseman`, or `goalie`); skaters send metrics such as `icetime`, `i_f_points`, `on_ice_x_goals_percentage`, zone starts, etc.; goalies send goalie advanced fields (`x_goals`, `goals`, danger buckets, …) plus optional `gp` / `wins` / … . Omitted fields are filled with defaults where the predictor allows.

See http://localhost:8000/docs for interactive API documentation.

## Usage

1. **Browse Players**: Navigate to the Players page to view and search through the player database
2. **View Contracts**: Check the Contracts page to see contract details and values
3. **Make Predictions**: Use the Predictions page to input player statistics and get contract value predictions

## Development

### Database Configuration

The backend connects to PostgreSQL. Configure connection in `backend/app/config.py` or via environment variables:
- `DB_HOST` (default: localhost)
- `DB_PORT` (default: 5432)
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`

### Running Tests

From the `backend` directory, with dependencies installed (`pip install -r requirements.txt` includes `pytest` and `pytest-cov`):

```bash
cd backend
source venv/bin/activate   # if you use a venv
pytest
```

Options:

- **Coverage**: `pytest --cov=app --cov-report=term-missing`
- **Single file**: `pytest tests/test_players.py`
- **Verbose / traceback**: configured in `pytest.ini` (`-v --tb=short`)

Scraping scripts under `app/ScriptingFiles/` are omitted from coverage runs via `backend/.coveragerc`; lines marked with `# pragma: no cover` are excluded from coverage reports.
