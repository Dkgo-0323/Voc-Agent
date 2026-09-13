# VOC Agent

This repository contains a local-first Voice of Customer MVP backed by
PostgreSQL, Milvus, FastAPI, an independent APScheduler worker, and a Next.js
frontend. The controlled Agent exposes only fixed report, analytics, and RAG
tools; deterministic calculations and capacity-tier restrictions remain in the
backend.

## Prerequisites

- Python 3.11 or newer and `uv`
- Node.js 20 or newer with npm
- Docker Desktop with Compose
- An OpenAI-compatible chat and embedding provider; the configured embedding
  model must return exactly 1024 dimensions

Copy `.env.example` to `.env`, then replace all placeholder secrets. In
particular, set `EMBEDDING_API_KEY`, an LLM credential, a random
`JWT_SECRET_KEY`, and a non-default `ADMIN_PASSWORD`. Never commit `.env`.

## Install and initialize

PowerShell commands below are run from the repository root:

```powershell
uv sync --extra dev
Push-Location frontend
npm ci
npx playwright install chromium
Pop-Location

docker compose up -d
uv run alembic -c alembic.ini upgrade head
uv run python -m backend.app.db.seed
```

The authoritative Alembic configuration is the root `alembic.ini`. Standard
SKU seeding creates metadata only. To populate a deterministic UI/release
fixture with traceable PostgreSQL/Milvus IDs, use a dedicated collection:

```powershell
$env:MILVUS_COLLECTION_NAME = "aspect_mentions_phase14_1024"
uv run python scripts/seed_phase14_demo_data.py
uv run python scripts/verify_phase14_demo_data.py
```

The demo seed calls the configured embedding provider, is idempotent, and is
intended for development or a disposable release-test database—not production.

## Run the product

Use separate terminals from the repository root:

```powershell
uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

```powershell
uv run python -m backend.worker.main
```

Build-time public variables must be set before a production frontend build:

```powershell
Push-Location frontend
$env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000"
npm run build
npm run start
```

Open `http://localhost:3000` and sign in with `ADMIN_PASSWORD`.

## Verification

```powershell
uv run ruff check backend pipelines scripts tests conftest.py
uv run pytest -q

Push-Location frontend
npm run lint
npm run typecheck
npm test
npm run build
Pop-Location
```

The release browser suite expects a migrated, seeded disposable PostgreSQL
database and a dedicated Milvus collection. Set the three Phase 14 variables;
the password must match `.env`. Playwright builds and starts isolated backend
and frontend processes on ports 8014 and 3014:

```powershell
Push-Location frontend
$env:PHASE14_DATABASE_URL = "postgresql+asyncpg://phase14:phase14@localhost:55432/voc_phase14"
$env:PHASE14_MILVUS_COLLECTION = "aspect_mentions_phase14_1024"
$env:PHASE14_ADMIN_PASSWORD = "<same value as ADMIN_PASSWORD in .env>"
npm run test:e2e
Pop-Location

$env:DATABASE_URL = $env:PHASE14_DATABASE_URL
$env:MILVUS_COLLECTION_NAME = $env:PHASE14_MILVUS_COLLECTION
uv run python scripts/verify_phase14_demo_data.py
uv run python scripts/verify_phase14_agent_traces.py
```

Known release-test caveats: the real LLM can occasionally return an unsupported
first-round answer. The handwritten Router performs one bounded grounding
reprompt in that case. PyMilvus 2.3 also emits a `pkg_resources` deprecation
warning. Neither introduces hidden Agent state or changes the PostgreSQL
source-of-truth and citation-provenance contracts.
