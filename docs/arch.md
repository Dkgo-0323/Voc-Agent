# VOC Agent Architecture

This document describes the implemented repository at the end of Week 4. It
is a local engineering/demo architecture, not a production-readiness claim.

## System boundaries

VOC Agent has four independently understandable layers:

1. A batch pipeline ingests, sanitizes, enriches, scores, and embeds customer
   text for five locked portable-power SKUs.
2. PostgreSQL stores all relational/product facts, workflow state, reports,
   chat history, and citation records. Milvus stores only retrieval vectors and
   scalar search metadata.
3. FastAPI exposes deterministic read models, authentication, report
   generation, and a controlled handwritten Agent.
4. Next.js renders the product and keeps server state, auth state, and local UI
   state separate.

```text
sources -> sanitize -> documents(raw)
                     -> enrich -> aspect_mentions + quality
                     -> embed_text -> embedding provider -> Milvus
                              PostgreSQL UUID <------------^ vector ID

PostgreSQL/Milvus -> repositories/services -> FastAPI -> Next.js
                                            -> controlled Agent -> SSE
independent APScheduler worker -> weekly pipeline (Sunday 02:00 UTC)
```

PostgreSQL is the relational source of truth. A Milvus hit is never exposed as
evidence by itself: the backend hydrates its UUID from PostgreSQL and validates
the relational record. `aspect_mentions.id` and the Milvus primary key are the
same UUID.

## Data model and pipeline

Alembic manages seven core tables: `skus`, `documents`, `aspect_mentions`,
`weekly_reports`, `weekly_topics`, `chat_sessions`, and `chat_messages`.
Documents advance through `raw`, `enriched`, and `embedded`; failures remain
isolated and record an error. The catalog is deliberately limited to the five
codes in `pipelines/config/targets.py`.

Reddit ingestion uses PRAW. Amazon ingestion uses a local/static McAuley review
dataset. Presidio removes PII before persistence and authors are represented by
a hash. Enrichment accepts only canonical aspects, limits extracted evidence
to exact source substrings, and computes quality in deterministic code.
Dashboard and RAG reads share `ASPECT_QUALITY_THRESHOLD` (default `0.55`). The
text embedded for retrieval is persisted as `embed_text`, allowing vector
inputs to be audited.

`EMBEDDING_DIMENSIONS` defaults to 1024 and is one contract spanning provider
output, the application, and the Milvus schema. API startup probes the provider
and validates an existing collection before accepting traffic. The worker is a
separate process and APScheduler invokes the weekly pipeline every Sunday at
02:00 UTC with `max_instances=1` and `coalesce=True`.

## Backend and public contracts

The API routes are mounted directly under `/api`:

| Method and path | Auth | Contract |
| --- | --- | --- |
| `GET /health` | No | PostgreSQL health and runtime metadata. |
| `POST /api/auth/login` | No | Exchange the configured admin password for a JWT. |
| `GET /api/auth/me` | Yes | Validate the JWT and return the current principal. |
| `GET /api/weeks` | No | Available ISO weeks. |
| `GET /api/overview` | No | Portfolio and per-SKU weekly summary. |
| `GET /api/skus` | No | Locked SKU metadata. |
| `GET /api/skus/{sku_code}` | No | SKU detail for a week. |
| `GET /api/skus/{sku_code}/evidence` | No | Paginated, quality-filtered evidence. |
| `GET /api/skus/{sku_code}/trends` | No | Weekly SKU trend series. |
| `GET /api/compare` | No | Two-to-three same-tier SKU comparison. |
| `GET /api/reports/{week_id}` | No | Persisted weekly report or not-found response. |
| `POST /api/reports/generate` | Yes | Generate/regenerate a report over SSE. |
| `POST /api/ask` | Yes | Run a controlled Agent turn over SSE. |

Request/response models are Pydantic schemas in `backend/app/schemas`. Database
access remains behind repositories. The comparison service is authoritative
for capacity tiers and rejects mixed-tier requests even if a client or model
requests them. Analytics, thresholds, counts, percentages, low-sample warnings,
and validation are deterministic; the LLM only routes and synthesizes.

`API_PREFIX` is retained in settings for compatibility but is not used to
remount these current paths.

## Controlled Agent and tool boundaries

`backend/app/agent/router.py` implements a pure function-calling loop. It has
no framework-managed memory and no hidden state. The hard limits are three
attempted tools, eight model rounds, duplicate-call protection, and one bounded
grounding reprompt only when the model tries to answer before any tool call.

- `tool_report` reads one already-persisted report. A missing report is an
  explicit result which the Router may combine with other tools.
- `tool_sql` accepts only six named operations: `review_count`,
  `sentiment_distribution`, `aspect_distribution`, `trend`, `aspect_trend`,
  and `compare_skus`. It never executes generated SQL.
- `tool_rag` accepts a query plus validated SKU/week/aspect/sentiment/top-k
  filters. It embeds the query, applies Milvus scalar filters, hydrates results
  from PostgreSQL, rechecks provenance and quality, and returns bounded
  evidence.

Provider-facing schemas expose the canonical aspect enum, while each tool
revalidates inputs at its authoritative boundary. Partial tool failures are
structured; no-data paths abstain instead of inventing support. Comparisons are
neutral and inherit the same server-side capacity restriction as the dashboard.

Chat sessions/messages are persisted in PostgreSQL. On each turn, only the
most recent visible user and assistant messages are supplied (default 8), with
compact tool names/statuses/cited IDs. Raw payloads, summarized secret context,
and implicit active SKU/week filters are not carried forward.

## SSE and persistence contracts

Ask success order is:

```text
tool_started -> tool_completed -> answer_delta* -> citation* -> done
```

There may be multiple tool pairs. A terminal `error` replaces normal
completion on failure. Citation objects are emitted only for evidence used in
the answer and retain the PostgreSQL mention UUID/source metadata. The turn and
its citations are committed before successful terminal events. Disconnects
propagate cancellation instead of continuing unobserved work.

Report generation success order is:

```text
report_started
  -> stage_started -> stage_completed (analytics)
  -> stage_started -> stage_completed (evidence)
  -> stage_started -> stage_completed (synthesis)
  -> report_delta*
  -> report_completed
```

Analytics and RAG inputs are bounded and deterministic. The synthesized
candidate is validated before any `report_delta`; chunks therefore improve UI
delivery but are not token streaming and cannot prove persistence. A database
transaction atomically creates/replaces the report before
`report_completed`. Failure/cancellation leaves an older report intact. The
current schema has no weekly-report-to-mention relation, so report citations
are unavailable by design.

## Frontend architecture

Implemented routes are `/login`, `/overview`, `/skus/[sku_code]`, `/compare`,
`/reports`, and `/ask`; `/` redirects. A shared application shell protects the
authenticated UI and provides navigation and logout.

- TanStack Query owns backend/server state and cache lifecycles.
- React Context owns the JWT session and authentication bootstrap.
- Components own transient selections, forms, stream progress, and popovers.
- Axios attaches the token stored at `voc.access-token`.

There is no Redux/Zustand store and no frontend shadow of Agent memory.
`NEXT_PUBLIC_API_BASE_URL` is embedded when Next.js builds. Ask and report
clients parse named SSE events, retain completed content, surface structured
errors, and invalidate relevant Query caches after successful mutation.

## Report and evaluation architecture

Weekly report generation combines repository-backed deterministic analytics,
quality-filtered RAG evidence, bounded LLM synthesis, schema/content
validation, and atomic persistence. Reading a report and generating one are
separate APIs and Agent `tool_report` remains read-only.

Evaluation has three layers:

1. Unit/integration regression tests verify pipeline states, embedding
   dimensions, UUID provenance, quality filters, APIs, scheduler behavior,
   report transactions, tools, Router behavior, SSE, and frontend state/UI.
2. The Week 3 deterministic Agent suite covers quantitative, RAG, hybrid,
   follow-up, abstention, comparison, and fallback behavior without relying on
   provider interpretation.
3. A 50-case semantic Golden dataset covers quantitative (7), trend (6),
   comparison (7), evidence (10), hybrid (6), follow-up (5), abstention (5),
   and report (4). Deterministic checks can evaluate captured observations;
   the optional structured judge scores semantic answer/retrieval quality.

Release gates are routing >=90%, answer correctness >=85%, retrieval relevance
>=85%, citation groundedness >=95%, abstention >=90%, follow-up >=90%, numeric
correctness 100%, and zero cross-tier, provenance, or critical unsupported
claim violations. The saved Phase 13 artifact is a controlled fixture judged
by the configured live provider, not 50 live database Agent runs. Phase 14 is a
separate real PostgreSQL/Milvus/provider browser suite.

## Preserved decisions and limitations

- PostgreSQL remains authoritative; Milvus can be rebuilt from persisted
  mention/embed data and vector IDs must equal mention UUIDs.
- Deterministic business rules do not move into prompts. Capacity-tier checks
  are enforced by services/tools, not trusted to the UI or model.
- Citations require traceable, hydrated, used evidence. Report prose currently
  lacks citation joins and must not be represented as citation-capable.
- Recent-N visible conversation is the only conversational carry-over; adding
  hidden Agent filters or memory would break the contract.
- Authentication is one configured password plus browser-local JWT storage;
  there is no multi-user/RBAC/tenant architecture.
- Live sources/providers introduce network, credential, cost, and
  nondeterminism constraints. The fixture and demo seed are development/release
  aids, not production data initialization.
- The fixed embedding dimension and old Milvus/PyMilvus compatibility pins
  require a coordinated upgrade. Known dependency deprecation warnings remain.
- Low-sample analytics warn but remain queryable; the MVP does not claim
  statistical significance.
