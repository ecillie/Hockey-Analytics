# Deploying TradeValue on Vercel and Neon

TradeValue deploys as two Vercel projects backed by one Neon Postgres database.
The API and web app are intentionally separate so each directory is detected and
built with its native framework.

## 1. Create Neon

The preferred path is to add Neon from the Vercel Marketplace while configuring
the backend project. You can also create the database directly in Neon.

Keep two connection strings:

- `DATABASE_URL`: the pooled Neon URL whose hostname contains `-pooler`; use it
  for the deployed backend.
- `NEON_DIRECT_DATABASE_URL`: the direct URL; keep it outside the frontend and
  use it for schema changes and ingestion.

Initialize an empty database from a trusted local environment:

```bash
psql "$NEON_DIRECT_DATABASE_URL" -f backend/database/schema.sql
```

Then load the source data if the database has not already been populated:

```bash
python -m pip install -r backend/requirements-dev.txt
cd backend
DATABASE_URL="$NEON_DIRECT_DATABASE_URL" ENV=prod \
  python -m app.ScriptingFiles.FullDataScript.run_all
```

Do not run the ingestion pipeline inside the request-serving Vercel Function.

## 2. Create the backend Vercel project

Import the Git repository and configure:

- Root Directory: `backend`
- Framework: FastAPI (also pinned by `backend/vercel.json`)
- Production branch: `Prod`, if retaining the repository's promotion workflow

Add these Production variables:

```dotenv
ENV=prod
DATABASE_URL=postgresql://...-pooler....neon.tech/...?...sslmode=require
CORS_ORIGINS=https://YOUR_FRONTEND_PRODUCTION_DOMAIN
```

For Preview deployments, use a separate Neon branch where possible. Set
`ENV=nonprod`, `DATABASE_URL` to that branch's pooled URL, and configure the same
production origin plus a narrowly scoped preview regex:

```dotenv
CORS_ORIGINS=https://YOUR_FRONTEND_PRODUCTION_DOMAIN
CORS_ORIGIN_REGEX=^https://YOUR_FRONTEND_PROJECT(-[a-z0-9-]+)?\.vercel\.app$
```

Deploy, then verify:

```bash
curl https://YOUR_BACKEND_DOMAIN/api/health
curl https://YOUR_BACKEND_DOMAIN/api/seasons
```

## 3. Create the frontend Vercel project

Import the same Git repository again and configure:

- Root Directory: `frontend`
- Framework: Vite (also pinned by `frontend/vercel.json`)
- Production branch: `Prod`

Add these variables to Production and Preview:

```dotenv
VITE_USE_MOCK_API=false
VITE_API_BASE_URL=https://YOUR_BACKEND_DOMAIN
```

These variables are compiled into the browser bundle, so changing them requires
a new frontend deployment. `DATABASE_URL` must never be configured on the
frontend project.

## 4. Validate the release

After both deployments succeed:

1. Open the frontend production URL and refresh directly on `/players`.
2. Confirm seasons, players, teams, search, and a player detail page load.
3. Confirm the browser console has no CORS or mixed-content errors.
4. Confirm unknown player and team URLs show application-level not-found states.
5. Review backend Function logs for database connection or timeout errors.

Git-based deployments handle builds automatically. The repository CI workflows
still run unit tests, lint, and the frontend production build before promotion.
The `Dev`, `NonProd`, and `Prod` workflows each publish an environment-specific
`required` check. Configure those checks as branch requirements and enable the
automatic promotion cascade by following
[CI and automatic promotion setup](./ci-promotion.md).
