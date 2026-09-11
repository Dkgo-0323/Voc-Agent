# Week 4 Phase 0: Product and API Contract Freeze

**Status:** frozen before Phase 1 implementation (2026-09-11).

This document reconciles the Week 4 plan with the checked-out application. It is
the contract for subsequent Week 4 phases; it does not claim that planned routes
or report generation already exist. Code remains the source of truth when this
document and an implemented contract differ.

## Baseline and preserved constraints

The current FastAPI application registers only dashboard, authentication, and
Agent routers. Implemented HTTP routes are `GET /health`, `GET /api/weeks`,
`GET /api/overview`, `GET /api/skus/{sku_code}/trends`, `POST /api/auth/login`,
`GET /api/auth/me`, and authenticated `POST /api/ask`.

The frontend is the untouched Next.js starter page. It has no product routes,
API client, authentication state, TanStack Query dependency, or frontend tests.

All Week 4 work must preserve:

- PostgreSQL as the relational source of truth, Milvus vector ID equal to
  `aspect_mentions.id`, and PostgreSQL evidence hydration;
- dashboard-enabled SKU filtering and the shared
  `ASPECT_QUALITY_THRESHOLD` (default `0.55`);
- the locked SKU set, fixed analytics operations, no arbitrary SQL, and the
  three attempted-tool-call maximum;
- exact-substring evidence, used-citations-only behavior, safe SSE errors,
  recent-N PostgreSQL conversation context, and no-data abstention;
- JWT bearer verification for `/api/ask` and the current public dashboard
  routes, unless a later phase explicitly changes an endpoint's protection.

## Frontend route map

The following routes are the Week 4 product target. They are planned routes,
not currently implemented pages.

| Route | Purpose | Data source at release | Current gap |
|---|---|---|---|
| `/login` | Submit the configured MVP password and establish browser session. | `POST /api/auth/login`, then `GET /api/auth/me`. | No page or session layer. |
| `/overview` | Select a covered week and inspect portfolio aggregates and SKU rankings. | Existing `GET /api/weeks` and `GET /api/overview?week_id=YYYYWW`. | No page. |
| `/skus/[sku_code]` | Per-SKU metrics, trends, and evidence. | Existing trends route plus the planned SKU-detail and evidence read contracts below. | The existing API lacks a SKU detail aggregate and evidence list. |
| `/compare` | Same-capacity-tier deterministic comparison, evidence, and a handoff to Ask. | Planned `GET /api/compare`; grounded narrative remains a prefilled `/ask` request, not a second comparison LLM. | No public comparison read API. |
| `/reports` | View a stored report and start a generation/replacement stream. | Planned report read and generation routes. | Current report repository/tool is read-only; no public route or generation service exists. |
| `/ask` | Stream a controlled Agent answer, progress, and used citations. | Existing authenticated `POST /api/ask`. | No page or SSE client. |

The frontend must use server state for API data, local state for filters and
streams, and an auth context for the bearer token. The plan calls for TanStack
Query, but it is not yet installed; adding it belongs to Phase 1, not this
freeze.

## API inventory and contracts

### Implemented public contracts

All JSON models reject unknown fields where the current Pydantic model declares
`extra="forbid"`.

| Endpoint | Auth | Request | Response / semantics |
|---|---|---|---|
| `GET /api/weeks` | public | none | `WeekResponse[]`: `week_id`, ISO `week_start`/`week_end`, `doc_count`, `mention_count`, sorted `skus_covered`. |
| `GET /api/overview?week_id=YYYYWW` | public | required integer query parameter | `OverviewResponse`: `week_id`; `summary.total_mentions`; positive/negative/neutral counts; `top_aspects` with `aspect_label`, `mention_count`, `positive_rate`; `sku_rankings` with `sku_code`, `sku_name`, `mention_count`, `sentiment_score`. A week without dashboard data is `404`. |
| `GET /api/skus/{sku_code}/trends?weeks=1..12` | public | path SKU and optional `weeks` (default 4) | `SkuTrendsResponse`: SKU code/name/capacity tier and per-week/per-aspect counts plus `avg_quality_score`. Unknown or disabled SKU and an invalid range are `400`. |
| `POST /api/auth/login` | public | `{ "password": string }`, 1–1024 characters | `{ "access_token": string, "token_type": "bearer" }`; incorrect password is `401` with `WWW-Authenticate: Bearer`. |
| `GET /api/auth/me` | bearer | `Authorization: Bearer <JWT>` | `{ "subject": string }`; absent, malformed, invalid, or expired token is `401`. |
| `POST /api/ask` | bearer | `AskRequest`: optional UUID `session_id`; nonblank, trimmed `message` (1–10,000 characters) | `text/event-stream`; documented below. Validation errors are normal FastAPI `422` responses before streaming starts. |

`GET /health` is infrastructure-only and is not a Week 4 product data source.

### Required Week 4 additions

These are dedicated read/write contracts needed by planned pages. They are
**not implemented** at Phase 0. Field names below are constrained to currently
stored values or already-existing Agent models; each endpoint needs tests before
it is introduced.

| Endpoint | Purpose and minimum request | Frozen response / behavior |
|---|---|---|
| `GET /api/skus` | List dashboard-enabled SKUs for navigation and valid comparison choices. No request body. | `SkuMetadata[]`: `sku_code`, `brand`, `model`, `capacity_wh`, `capacity_tier`, `is_competitor`, `dashboard_enabled`. Reuse the existing repository model; do not expose disabled SKUs. |
| `GET /api/skus/{sku_code}?week_id=YYYYWW` | SKU Detail summary for one existing dashboard week. | A new read model composed from existing aggregates: SKU metadata; selected `week_id`; `review_count`, `mention_count`; positive/negative/neutral counts; top aspect buckets; and no synthetic movement/recommendation fields. It must reject an unknown/disabled SKU and a week with no scoped data. |
| `GET /api/skus/{sku_code}/evidence?week_id=YYYYWW&sentiment=positive|negative&limit=1..N` | Evidence cards for SKU Detail. | A list of the shared `EvidenceViewModel`. It must select only dashboard-enabled, quality-qualified mentions, apply the requested sentiment/week, preserve the mention-to-document provenance, and document deterministic ordering in its implementation. `representative` is a UI label, not a stored field or an LLM judgment. |
| `GET /api/compare?sku_code=<code>&sku_code=<code>[&week_id=YYYYWW]` | Deterministic same-tier comparison. | A read model based on the existing comparison, aspect-distribution, trend, and evidence data. It must validate all requested codes before querying, require at least two enabled SKUs with the same non-null `capacity_tier`, return neutral metrics, and surface `capacity_tier_mismatch` or `capacity_tier_unavailable` as a structured client error. No winner/better field. |
| `GET /api/reports/{week_id}?sku_code=<code>` | Read a stored report for one locked, dashboard-enabled SKU and ISO week. | The current `WeeklyReportPayload` shape: `report_id`, `sku_code`, `week_id`, nullable `report_md`, nullable `summary`, and `generated_at`. Missing report is a typed/not-found response; it must not fabricate a report. |
| `POST /api/reports/generate` | Create a candidate report or atomically replace the report for one locked, dashboard-enabled SKU/week. Request: `{ "sku_code": string, "week_id": integer }`. | `text/event-stream` with the lifecycle below. A separate `regenerate` flag is deliberately unnecessary: the same request creates when absent and replaces only after a successful validated candidate. |

The request-level error envelope for new streaming APIs must reuse the existing
safe shape: `{ "event_type": "error", "error": { "code", "message",
"retryable", "details" } }`. Provider text, stack traces, raw tool data, and
hidden reasoning are never protocol fields.

## Frontend view models

Frontend code may define TypeScript equivalents, but it must not broaden these
models with fields absent from their backend response.

| View model | Backing contract | Required fields |
|---|---|---|
| `WeekOption` | `WeekResponse` | `week_id`, `week_start`, `week_end`, `doc_count`, `mention_count`, `skus_covered`. |
| `OverviewViewModel` | `OverviewResponse` | selected `week_id`, total mentions, sentiment counts, top aspects, and SKU ranking rows. No portfolio-movement field exists yet. |
| `SkuNavigationItem` | `SkuMetadata` | code, brand, model, optional capacity Wh/tier, competitor and enabled flags. |
| `SkuDetailViewModel` | planned SKU detail + trends + evidence | metadata, selected week, count/distribution data, trend points, and positive/negative `EvidenceViewModel[]`. The current trends endpoint alone does not provide all detail data. |
| `ComparisonViewModel` | planned comparison response | requested SKU metadata, shared tier, neutral per-SKU counts/rates/score, aspects/trends/evidence, warnings, and a validation error state. It has no `winner`. |
| `WeeklyReportViewModel` | `WeeklyReportPayload` | `report_id`, SKU, week, nullable Markdown, nullable summary, `generated_at`. Absence is a distinct not-found/empty state. |
| `AskStreamViewModel` | `AskRequest` and current `StreamingEvent` union | local draft, optional `session_id`, accumulating answer Markdown, lifecycle status, used citations, terminal status/error, and stable session/user/assistant IDs from `done`. |
| `ReportGenerationStreamViewModel` | planned report SSE union | SKU/week, ordered stages, accumulating Markdown candidate, terminal report metadata, and terminal error. It must not treat deltas as persisted before `report_completed`. |
| `AuthSessionViewModel` | auth routes | in-memory/stored bearer token, verified subject, loading state, and unauthenticated/expired state. There is no user profile or role. |

## Shared evidence and citation contract

The common display model is the existing `AnswerCitation`; it is suitable for
chat and planned SKU/compare evidence cards without adding a second evidence ID:

```text
mention_id, document_id, evidence_preview, sku_code, aspect_label, sentiment,
week_id, source { document_id, sku_code, platform, published_at, source_url,
                  title, rating, review_text }
```

`mention_id` is exactly `aspect_mentions.id`, which is also the Milvus vector
ID. `document_id` must equal `source.document_id`, and `sku_code` must equal
`source.sku_code`. `evidence_preview` is the exact persisted mention text; it
is not an LLM paraphrase. `review_text` is already available in hydrated
evidence, though a UI should render it only on explicit expansion.

Retrieved evidence and citations remain separate. A citation is emitted only
when its mention ID was retrieved and explicitly selected for the final answer.
The UI may number and pop over citations locally, but may not invent a citation
for an aggregate-only claim.

`weekly_reports` does **not** currently store cited mention IDs or a report
evidence relation. Consequently Phase 0 freezes report viewing/generation to
the stored Markdown and summary fields; report-level interactive citations are
out of scope until a later, separately reviewed schema contract adds durable
provenance (for example, a validated report-to-mention relation). Chat,
SKU-detail, and comparison evidence continue to use the shared contract above.

## Weekly Report persistence contract

The existing `weekly_reports` row has only:

```text
id, sku_id, week_id, report_md?, summary?, generated_at
```

It has a unique constraint on `(sku_id, week_id)`. It has no status, author,
generation error, source/citation, version, or draft columns. `weekly_topics`
exists, but no current report service reads or writes it. The current
`ReportRepository` and `ReportService` perform read-only lookup for locked,
dashboard-enabled SKUs and return stored content verbatim or `not_found`.

The Week 4 report generation implementation must use this existing one-row
identity. It must validate the locked/dashboard-enabled SKU and ISO week,
construct and validate a complete candidate outside the old row's destructive
path, then write the candidate report/summary and `generated_at` in one database
transaction. If there is no row, it inserts; if there is a row, it replaces that
row atomically. It must not add report version history in Week 4.

If candidate generation, validation, or commit fails, the request emits a safe
terminal `error`, rolls back, and the prior report remains readable unchanged.
No `report_completed` is sent before the successful commit.

## Report-generation SSE lifecycle

The report stream will be new. It reuses SSE framing and the safe error envelope
from `/api/ask`, but uses its own discriminated `event_type` values:

1. `report_started` — emitted once after request validation and before work;
   carries `sku_code` and `week_id` only.
2. `stage_started` — emitted before each named, user-safe stage. The stage is a
   stable public label (for example, data collection or report drafting), never
   raw tool arguments or private reasoning.
3. `stage_completed` — emitted after that stage; may carry safe counts/warnings,
   never raw retrieval payloads or provider exceptions.
4. `report_delta` — zero or more ordered Markdown fragments of the candidate.
   These are display progress only, not proof of persistence.
5. `report_completed` — exactly once, only after candidate validation and
   transaction commit. Carries the persisted `WeeklyReportPayload`.
6. `error` — terminal alternative to `report_completed`. It carries the standard
   safe error envelope and is never followed by a completed event.

No event follows either terminal event. Cancellation follows the existing ask
behavior: cancel in-flight work where possible and roll back uncommitted writes.

## Authentication and session behavior

Authentication is intentionally a configured-single-password MVP. Successful
login issues an HS256 JWT for fixed subject `admin`, with `iat` and `exp`; the
configured lifetime defaults to seven days. The backend does not issue refresh
tokens, use cookies, expose logout, store users, or implement RBAC.

The frontend stores/sends the access token as a bearer credential, bootstraps or
validates it through `/api/auth/me`, and clears its local session then returns to
`/login` on `401`. This is a browser-session behavior proposal; it must not
claim server-side logout/revocation. `/api/ask` remains protected and stores the
verified subject only as `chat_sessions.created_by`; dashboard routes are public
today. Planned report mutation must require bearer authentication. Whether new
dashboard read routes remain public follows the current dashboard decision and
must be tested explicitly when each route is added.

Chat session behavior is independent of the JWT token: an omitted `session_id`
creates a session; a supplied valid UUID reuses an active session; unknown or
inactive sessions emit `unknown_session`. The service loads the most recent
configured eight messages by default, has no hidden filters or summarization,
and persists compact tool metadata plus cited mention IDs only after a turn.

## Same-capacity-tier comparison rule

Direct comparison accepts only dashboard-enabled SKU codes. `tool_sql` defaults
an omitted SKU list to all enabled SKUs, validates ISO weeks, and permits
`compare_skus` only for at least two codes whose `capacity_tier` values are all
present and identical. Cross-tier input returns `capacity_tier_mismatch` with a
code-to-tier `details` map before aggregate queries. Missing tier metadata
returns `capacity_tier_unavailable`, also before aggregate queries.

The comparison data is deterministic, mention-based, quality-filtered, and
neutral: review/mention counts, sentiment counts/rates, and sentiment score
`(positive_count - negative_count) / mention_count`. `review_count` is distinct
`document_id` count, not all raw documents. A sample below
`MIN_RELIABLE_SAMPLE` (default 20) warns but does not block a valid query; zero
matching data is partial with `no_matching_data`. The frontend filters choices
by tier for usability, but never substitutes for server validation.

## Evaluation metrics and release gates

The existing deterministic suite includes the Week 3 19-query golden acceptance
coverage and tests schemas, analytics, report read-only behavior, RAG
provenance, conversation persistence, SSE, auth, dashboard APIs, and pipeline
contracts. It must remain green.

The Week 4 plan requires a separate 50-query semantic suite with deterministic
assertions where possible, LLM-as-a-Judge dimensions where needed, and human
review of every failed/borderline case plus a passing sample. At Phase 0,
`shared/eval/rag_eval.py` and the semantic dataset do not exist; neither must be
represented as implemented. Their Phase 11–13 work must define reproducible
case records and per-case metrics before gates can be measured.

Frozen release gates are:

| Metric | Gate |
|---|---:|
| Tool / routing correctness | >= 90% |
| Answer correctness | >= 85% |
| Retrieval relevance | >= 85% |
| Citation groundedness | >= 95% |
| Abstention correctness | >= 90% |
| Follow-up context correctness | >= 90% |
| Deterministic numeric correctness | 100% |
| Cross-tier violations | 0 |
| Citation provenance violations | 0 |
| Critical unsupported claims | 0 |

A later threshold or metric-definition change requires written justification;
it cannot be made solely to pass an evaluation run.

## Explicit out of scope for Week 4

Week 4 excludes multi-user registration, user storage, RBAC, OAuth, refresh
tokens, server-side token revocation, Redis, Celery/distributed queues,
WebSockets, GraphQL, Redux/Zustand, arbitrary SQL, custom SKU creation,
taxonomy editing, an admin/ingestion UI, long-term Agent memory, conversation
summarization, multi-agent workflows, report version history, elaborate
animation, production deployment claims, root-cause/action-recommendation
engines, and a second comparison-specific LLM subsystem.

## Week 4 Definition of Done

Week 4 is complete only when the planned pages consume the documented contracts;
same-tier constraints are enforced server-side; report replacement has the
atomic behavior above; Ask renders only safe lifecycle state and used citations;
the deterministic suite and semantic evaluation meet the frozen gates; a clean
developer environment can migrate, seed, run, and verify the product; and final
documentation distinguishes implemented, verified behavior from limitations.
