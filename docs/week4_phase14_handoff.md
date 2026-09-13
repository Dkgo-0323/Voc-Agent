# Week 4 Phase 14 Handoff

Phase 14 release verification completed on 2026-09-13. Phase 15 has not
started.

## Clean environment

A disposable PostgreSQL 15 container was created without a persistent volume:

```powershell
docker run --detach --rm --name voc_phase14_postgres `
  --env POSTGRES_USER=phase14 --env POSTGRES_PASSWORD=phase14 `
  --env POSTGRES_DB=voc_phase14 --publish 55432:5432 `
  --tmpfs /var/lib/postgresql/data postgres:15-alpine
$env:DATABASE_URL = "postgresql+asyncpg://phase14:phase14@localhost:55432/voc_phase14"
python -m alembic -c alembic.ini upgrade head
python -m alembic -c alembic.ini current
python -m backend.app.db.seed
$env:MILVUS_COLLECTION_NAME = "aspect_mentions_phase14_1024"
python scripts/seed_phase14_demo_data.py
python scripts/verify_phase14_demo_data.py
```

Results: Alembic reached `f7a8b9c0d1e2 (head)`, five locked SKUs were seeded,
10 deterministic documents/mentions and 10 real 1024-dimensional embeddings
were written, and the dedicated Milvus collection contained the same 10 UUIDs
as `aspect_mentions.id`. Nine mentions met the shared 0.55 quality threshold;
one controlled low-quality mention was excluded. All 10 documents were in the
`embedded` processing state with populated `embed_text`.

The backend passed its startup database, locked-SKU, Milvus schema, and live
embedding-dimension checks. `python -m backend.worker.main` remained alive with
its independent APScheduler process during a five-second startup probe. The
Playwright configuration performs a production Next.js build with the isolated
API URL and starts backend/frontend on ports 8014/3014.

## Browser release regression

The release suite is in `frontend/e2e/release.spec.ts`. The following focused
commands were used so long real-provider flows stayed within shell execution
limits:

```powershell
npx playwright test --grep "login, dashboard"
npx playwright test --grep "report generation"
npx playwright test --grep "controlled Ask"
npx playwright test --grep "logout and expired"
```

Results: four tests passed. They covered login, overview, SKU detail, same-tier
comparison, server-side cross-tier rejection, report generation and
regeneration, quantitative SQL, qualitative RAG, combined SQL+RAG, a
recent-context follow-up, citation popover, no-data abstention, logout, and an
invalid/expired token redirect.

The final combined command also passed in one production-build run:

```text
npm run test:e2e
  4 passed (2.2m)
```

Persisted Agent traces were audited with:

```powershell
python scripts/verify_phase14_agent_traces.py
```

The audit confirmed `tool_sql`, `tool_rag`, and combined tool execution; the
follow-up recovered week 202403 from visible recent conversation messages; the
no-data turn persisted `agent_status=abstained`; and cited IDs resolved to the
deterministic PostgreSQL/Milvus fixture.

## Regression results

```text
python -m ruff check backend pipelines scripts tests conftest.py
  All checks passed.

python -m pytest -q
  234 passed, 3 dependency deprecation warnings

npm run lint
  passed

npm run typecheck
  passed

npm test
  8 files, 35 tests passed

npm run build
  passed; all seven product routes built
```

The Python suite includes processing-state transitions, the embedding dimension
contract, PostgreSQL/Milvus provenance behavior, shared quality filtering,
dashboard APIs, APScheduler configuration, and the Week 3 deterministic Agent
suite.

## Release defects found and fixed

1. Credentialed development CORS used wildcard origin `*`, which browsers
   reject. Development now echoes only local `localhost`/`127.0.0.1` origins.
2. the comparison client serialized arrays as `sku_code[]`; FastAPI requires
   repeated `sku_code` parameters. It now uses explicit `URLSearchParams`.
3. the provider tool schema allowed arbitrary aspect strings, permitting
   `noise` to reach the strict tool boundary and fail. The provider-facing SQL
   and RAG schemas now expose the canonical enrichment aspect enum while the
   tool still performs authoritative validation.
4. production Next.js public environment values are build-time values. The E2E
   runner now builds under the isolated API URL instead of reusing an unrelated
   `.next` output.
5. Vitest initially collected the Playwright suite. Its include pattern is now
   restricted to `tests/**/*.test.{ts,tsx}`.
6. The live provider occasionally returned an unsupported first-round answer
   without calling a tool. The handwritten Router now performs one bounded
   grounding reprompt when no tool has yet been attempted.

## Known risks

- The live LLM produced two isolated invalid first-round responses with zero
  tool calls during exploratory runs. The handwritten Router now performs one
  bounded grounding reprompt only when no tool has been attempted; it remains
  inside the existing model-round and three-tool limits. The final combined
  four-test browser suite passed. Provider nondeterminism remains observable.
- PyMilvus 2.3 imports deprecated `pkg_resources`, and test dependencies emit
  Starlette/httpx and Marshmallow compatibility warnings. Version constraints
  preserve current compatibility, but these should be addressed in a later
  dependency-upgrade phase.
- The report persistence contract intentionally has no report-to-mention join,
  so report citation cards remain unavailable; Ask citations remain fully
  traceable.
