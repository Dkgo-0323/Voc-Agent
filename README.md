# VOC Agent

VOC Agent is a local-first Voice of Customer analysis MVP for product, market,
and customer-insight teams monitoring portable-power products. It turns
Reddit and Amazon review text into weekly portfolio metrics, SKU drill-downs,
same-capacity-tier comparisons, grounded evidence answers, and generated
weekly reports.

This repository is an engineering/demo system, not a production deployment.
Its central rule is that PostgreSQL remains the relational source of truth:
the LLM may select controlled tools and synthesize prose, but it does not own
business rules, calculations, filters, citations, or conversation state.

## Architecture and technology

```text
Reddit / Amazon files
        |
        v
ingest -> PII sanitize -> enrich -> quality score -> embed
        |                                      |       |
        +-------------- PostgreSQL <-----------+       +-> Milvus
                           |                    source ID = aspect_mentions.id
                           v
                    FastAPI read models
                           |
              +------------+-------------+
              |                          |
        Next.js dashboard         handwritten Agent
                                  report / SQL / RAG tools
                                          |
                                  SSE answers + citations
```

- Backend and pipeline: Python 3.11+, FastAPI, SQLAlchemy asyncio/asyncpg,
  Alembic, APScheduler, Pydantic, Presidio, PRAW, and the OpenAI-compatible SDK.
- Storage: PostgreSQL 15; Milvus 2.3.4 with etcd and MinIO. The compatible
  Python client is intentionally pinned below PyMilvus 2.4.
- Frontend: Next.js 16, React 19, TypeScript, Tailwind CSS 4, TanStack Query,
  Axios, Recharts, and Lucide.
- Verification: pytest, Ruff, Vitest/Testing Library, ESLint, TypeScript,
  Playwright, a deterministic Agent suite, and a semantic Golden evaluation.

The ingestion pipeline accepts Reddit through PRAW and the local/static
McAuley Amazon dataset. It sanitizes PII, restricts processing to five locked
SKUs, and moves each document through `raw -> enriched -> embedded`; one failed
document does not block its peers. Enrichment extracts evidence-backed aspect
mentions, persists the exact `embed_text`, and applies a deterministic quality
score. Dashboard and RAG reads share the default `0.55` quality threshold.
Embeddings are 1024-dimensional, and each Milvus vector primary key must equal
the corresponding `aspect_mentions.id` UUID. The independent worker runs the
pipeline every Sunday at 02:00 UTC with one-instance/coalescing protection.

See [docs/arch.md](docs/arch.md) for the detailed component, state, API, SSE,
and provenance contracts.

## Controlled Agent

The Agent is a handwritten function-calling loop, not LangChain or
LlamaIndex. A turn can attempt at most three tools over at most eight model
rounds. If the first answer is unsupported and no tool was attempted, the
Router allows one bounded grounding reprompt. These are its only tools:

| Tool | Boundary |
| --- | --- |
| `tool_report` | Reads an already persisted weekly report; never generates one. |
| `tool_sql` | Runs only six fixed operations: review count, sentiment distribution, aspect distribution, trend, aspect trend, and same-tier SKU comparison. It cannot execute model-authored SQL. |
| `tool_rag` | Accepts validated structured filters, embeds the query, searches Milvus, then hydrates and verifies evidence from PostgreSQL. |

Capacity-tier comparison, dashboard eligibility, sample warnings, quality
filtering, arithmetic, and canonical aspect validation are enforced in code.
Only evidence actually used in the answer may become a citation. Citation IDs
are PostgreSQL mention UUIDs that must match the Milvus IDs returned during
retrieval. Chat history is stored in PostgreSQL; each turn receives only the
most recent visible user/assistant messages (`RECENT_MESSAGE_LIMIT`, default
8) plus compact tool metadata. There is no hidden active-filter or Agent state.

`POST /api/ask` emits `tool_started`, `tool_completed`, `answer_delta`,
`citation`, and terminal `done` SSE events, or a terminal `error`. Successful
messages and citations are committed before final success events.

## Product routes and state

| Route | Purpose |
| --- | --- |
| `/login` | Single-password login and JWT session creation. |
| `/overview` | Week selector, portfolio summary, and SKU monitoring table. |
| `/skus/[sku_code]` | SKU metrics, trends, aspect breakdown, and evidence. |
| `/compare` | Two-to-three SKU comparison; the server rejects mixed capacity tiers. |
| `/reports` | Read a stored weekly report or explicitly generate/regenerate it. |
| `/ask` | Quantitative, qualitative, hybrid, and recent-context follow-up questions with citation popovers. |

TanStack Query owns remote/server state, React Context owns the JWT session,
and route components own ephemeral UI state. The token is stored under
`voc.access-token` in browser local storage and attached to API requests. No
Redux/Zustand store or client-side copy of Agent state is present. Dashboard
read routes are public; Ask, report generation, and `/api/auth/me` require the
JWT. Logout clears the token, and an invalid/expired token redirects to login.

Weekly report generation is a separate authenticated workflow. It combines
deterministic analytics with quality-filtered RAG evidence, asks the LLM for a
bounded candidate, validates it, and atomically creates or replaces the week’s
report. Failure or cancellation preserves the previous report. Its SSE stages
are `report_started`, `stage_started`, `stage_completed`, `report_delta`, and
`report_completed`, or terminal `error`. `report_delta` chunks a completed
candidate; it is not token streaming. The schema has no report-to-mention join,
so report citation cards are deliberately unavailable; Ask citations remain
traceable.

## Prerequisites

- Python 3.11 or newer and [uv](https://docs.astral.sh/uv/)
- Node.js 20 or newer with npm
- Docker Desktop with Compose
- An OpenAI-compatible chat provider and embedding provider; the configured
  embedding model must return exactly 1024 dimensions
- Reddit credentials only when running Reddit ingestion

Copy `.env.example` to `.env` and replace placeholders. Never commit `.env`.
The main variables are:

| Variables | Meaning |
| --- | --- |
| `DATABASE_URL` | Async PostgreSQL URL used by the API, worker, migrations, and scripts. |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Docker Compose PostgreSQL initialization. |
| `MILVUS_HOST`, `MILVUS_PORT`, `MILVUS_COLLECTION_NAME` | Vector service and collection. |
| `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` | Compose-only Milvus object-store credentials. |
| `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` | Chat/enrichment provider. `OPENAI_API_KEY` is only a legacy fallback. |
| `LLM_MAX_TOKENS`, `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES`, `LLM_EXTRA_BODY` | Provider request controls. |
| `EMBEDDING_API_KEY`, `EMBEDDING_BASE_URL`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`, `EMBEDDING_BATCH_SIZE` | Embedding provider and the cross-system dimension contract. |
| `ASPECT_QUALITY_THRESHOLD`, `MIN_RELIABLE_SAMPLE`, `MAX_RAG_TOP_K`, `RECENT_MESSAGE_LIMIT` | Deterministic data and Agent limits. |
| `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_EXPIRE_DAYS`, `ADMIN_PASSWORD` | Authentication. Use non-default secrets outside development. |
| `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT` | Optional live Reddit ingestion. |
| `APP_ENV`, `LOG_LEVEL` | Runtime mode and logging. |
| `NEXT_PUBLIC_API_BASE_URL` | Frontend API origin; set it before a production build because it is build-time public configuration. |

`API_PREFIX` remains in settings for compatibility, but current routes are
mounted directly under `/api`; changing it does not remount the API.

## How to run

All PowerShell commands start at the repository root.

1. Install dependencies and the browser used by release E2E:

   ```powershell
   uv sync --extra dev
   Push-Location frontend
   npm ci
   npx playwright install chromium
   Pop-Location
   ```

2. Start PostgreSQL and Milvus dependencies, migrate, and seed locked SKU
   metadata:

   ```powershell
   docker compose up -d
   uv run alembic -c alembic.ini upgrade head
   uv run alembic -c alembic.ini current
   uv run python -m backend.app.db.seed
   ```

   Create a migration only when the ORM schema intentionally changes:

   ```powershell
   uv run alembic -c alembic.ini revision --autogenerate -m "describe change"
   uv run alembic -c alembic.ini upgrade head
   ```

3. Populate data using either the real pipeline or the deterministic demo
   fixture. The pipeline uses configured sources/providers:

   ```powershell
   uv run python scripts/run_pipeline_once.py --limit 5
   ```

   For an idempotent development/demo fixture, use a dedicated collection.
   This calls the configured embedding provider and is not a production seed:

   ```powershell
   $env:MILVUS_COLLECTION_NAME = "aspect_mentions_phase14_1024"
   uv run python scripts/seed_phase14_demo_data.py
   uv run python scripts/verify_phase14_demo_data.py
   ```

4. Start these long-running processes in separate repository-root terminals:

   ```powershell
   uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
   ```

   ```powershell
   uv run python -m backend.worker.main
   ```

   For frontend development:

   ```powershell
   Push-Location frontend
   $env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000"
   npm run dev
   ```

   Or verify and run the production build locally:

   ```powershell
   Push-Location frontend
   $env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000"
   npm run build
   npm run start
   ```

Open `http://localhost:3000` and sign in with `ADMIN_PASSWORD`. API health is
at `http://127.0.0.1:8000/health`; development OpenAPI is at `/docs`.

## Tests, evaluation, and release gates

Run deterministic backend and frontend checks:

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

The Phase 14 Playwright suite uses a migrated disposable PostgreSQL database,
a dedicated Milvus collection, real configured providers, and ports 8014/3014.
After applying the migration and both demo scripts against those isolated
names, run:

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

The 50-case semantic Golden dataset has deterministic checks and an optional
structured LLM judge. Evaluate captured observations reproducibly with:

```powershell
uv run python -m shared.eval.rag_eval `
  --observations path\to\observations.json `
  --judge-results path\to\judge-results.json `
  --output artifacts\eval\evaluation-report.json
```

Or run the controlled fixture through the configured live judge (this incurs
provider calls and is nondeterministic):

```powershell
uv run python -m shared.eval.fixture_live_run `
  --output artifacts\eval\fixture-live-report.json
```

Release requires tool/routing >=90%, answer correctness >=85%, retrieval
relevance >=85%, citation groundedness >=95%, abstention >=90%, follow-up
>=90%, and deterministic numeric correctness 100%. Cross-tier, provenance,
and critical unsupported-claim violations must each be zero. Phase 13's saved
fixture/live-judge report passed all gates; Phase 14 separately passed the
real-service browser flow and Week 1-3 regressions. Details and exact results
are in `docs/week4_phase13_handoff.md` and `docs/week4_phase14_handoff.md`.

## Interview/demo flow

1. **Login**: explain the deliberately small single-password/JWT boundary.
2. **Overview**: select a week and read portfolio/SKU health from deterministic
   API aggregates.
3. **SKU**: open a product to inspect trends, aspects, and filtered evidence.
4. **Compare**: compare same-tier SKUs, then mention that mixed tiers are
   rejected by the server rather than by prompt instruction.
5. **Weekly Report**: generate, inspect, and regenerate; explain validation and
   atomic replacement.
6. **Ask**: demonstrate a numeric SQL question, qualitative RAG question, and
   combined SQL + RAG question.
7. **Citation**: open a citation popover and trace its mention ID back through
   PostgreSQL and Milvus provenance.
8. **Follow-up**: ask a context-dependent question and explain recent-N visible
   history with no hidden filter state.
9. **Evaluation**: show deterministic contracts, the 50-case semantic gates,
   and the separate browser release suite; distinguish fixtures from live E2E.

## Known limitations

- The five SKU catalog and single-password authentication are MVP constraints;
  there is no multi-user identity, RBAC, tenant isolation, or deployment setup.
- Providers and ingestion sources require external credentials/network access.
  Real LLM and judge output can vary; one bounded grounding reprompt mitigates,
  but does not eliminate, unsupported first responses.
- The Phase 13 semantic run uses a controlled fixture plus a live judge, not 50
  live Agent/database executions. Phase 14 covers a smaller browser flow using
  PostgreSQL, Milvus, and real configured providers.
- Weekly reports do not persist report-to-mention provenance and therefore do
  not expose citation cards. Ask citations do.
- Retrieval uses one fixed embedding dimension/collection contract; changing
  models requires coordinated PostgreSQL/Milvus migration or re-embedding.
- Analytics below `MIN_RELIABLE_SAMPLE` remain queryable with a warning rather
  than being statistically conclusive.
- The frontend token is held in local storage. This is adequate for the scoped
  local demo, not a hardened browser-session design.
- PyMilvus 2.3 and current test dependencies emit known deprecation warnings.
  Their versions are constrained for compatibility with Milvus 2.3.4.
