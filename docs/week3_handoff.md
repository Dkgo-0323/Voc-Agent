# Week 3 Development Handoff

## Current Status

- Current completed phase: Phase 11 (regression and Week 3 sign-off).
- Current checkpoint: Checkpoints A-F reached.
- Phase 8: `POST /api/auth/login` issues expiring JWTs for the configured password, `GET /api/auth/me` validates bearer tokens, and `/api/ask` is protected. Dashboard routes intentionally remain public.
- Week 3 is complete; any future work begins with the separately scoped Week 4 roadmap.
- Working tree: Week 3 work is uncommitted on branch `codex/week2-day1-repositories`; HEAD is `63c5f81` (Week 2 acceptance hardening).
- Verified on 2026-08-31: 190 full-suite tests passed.

## What Was Implemented

### Phases 0-1: audit and contracts

- Pydantic contracts cover fixed analytics/RAG/report arguments, structured tool results, retrieved evidence, final citations, expanded source metadata, Agent results, conversation results, and streaming events.
- `ToolStatus` supports `success`, `empty`, `not_found`, `partial`, and `error`.
- Retrieved evidence is intentionally separate from final answer citations. Both retain the PostgreSQL `aspect_mentions.id` as `mention_id`.

### Phase 2: deterministic analytics (`tool_sql`)

- Approved operations: `review_count`, `sentiment_distribution`, `aspect_distribution`, `trend`, `aspect_trend`, and `compare_skus`.
- The LLM never receives arbitrary SQL capability. Repository queries are fixed SQLAlchemy statements.
- Results remain neutral metrics: counts, proportions, trends, per-dimension comparison values, and warnings.
- Cross-tier comparisons return a structured `capacity_tier_mismatch`/constraint error; they are not silently executed.
- Low samples remain queryable and return warnings using `MIN_RELIABLE_SAMPLE` (default 20).

### Phase 3: RAG and provenance

- Structured filters cover semantic query, one or more SKU codes, inclusive week range, sentiment, aspect taxonomy, and `top_k`.
- Retrieval path is embedding -> Milvus filtered search -> vector UUID -> PostgreSQL mention/document hydration -> `RetrievedEvidence`.
- Multi-SKU retrieval searches each validated SKU partition, merges by score, and applies a global `top_k`.
- Hydration rechecks quality, dashboard-enabled SKU status, requested metadata, and source-document provenance.
- `build_answer_citations` accepts only explicitly selected IDs that were present in retrieved evidence.

### Phase 4: read-only report tool

- Reads existing `weekly_reports` by dashboard-enabled locked SKU and ISO week.
- Returns stored content verbatim or structured `not_found`.
- Contains no report generation and no invisible analytics/RAG fallback.

### Phase 5: handwritten Router

- `FunctionCallingRouter` uses an OpenAI-compatible function-calling adapter with no LangChain/LlamaIndex.
- Tools are composable rather than selected through a strict priority chain.
- `MAX_TOOL_CALLS = 3` is enforced in application code; duplicate calls and malformed arguments do not execute.
- Quantitative claims must use analytics/stored report data; exact examples must use traceable evidence.
- No-data returns abstention. One failed tool can yield a disclosed partial answer only when another result provides material support.
- Final citation IDs are validated against retrieved evidence; uncited exact evidence use is rejected.

### Phase 6: conversation persistence

- Reuses `chat_sessions` and `chat_messages`; no new migration was added.
- Loads only the most recent configured N user/assistant messages (default 8), then restores chronological order.
- Stores the user message, final assistant message, normalized tool calls, compact execution metadata, and cited mention IDs.
- Does not store full tool payloads, reviews, embeddings, or large result sets in `tool_results`.
- No hidden active SKU/week/aspect/sentiment state and no session summarization.
- Session-row locking plus monotonic microsecond timestamps preserve deterministic user/assistant and cross-turn ordering.

### Phase 7: SSE API

- `POST /api/ask` accepts only optional `session_id` and `message`.
- Real-time tool lifecycle callbacks produce `tool_started` before execution and `tool_completed` after execution.
- Final events are `answer_delta`, used `citation` events, then `done`; request-level failures end with structured `error`.
- The chat transaction must commit before answer/citation/`done`; commit failure produces `error` instead of false success.
- Streaming cancellation cancels in-flight Agent work and rolls back uncommitted work where possible.
- `get_request_identity` is a JWT bearer-token dependency that returns the verified token subject.

### Phase 8: minimal JWT authentication

- `POST /api/auth/login` checks the configured `ADMIN_PASSWORD` and returns an expiring bearer token for the fixed `admin` subject.
- `GET /api/auth/me` validates the token and returns the subject.
- `/api/ask` is protected; authenticated identity flows only into `chat_sessions.created_by`.
- Dashboard routes intentionally remain public. No users table, registration, OAuth, RBAC, refresh tokens, or password-reset flow was added.

### Phase 9: reliability and guardrails

- Existing deterministic errors cover invalid arguments/SKUs/weeks, capacity constraints, empty data, low samples, analytics queries, and RAG vector/hydration failures.
- RAG now distinguishes safe retryable `rag_embedding_timeout` from `rag_embedding_failed`.
- Router failures retain an `AgentRunResult.error`; LLM failures use `llm_timeout` or `llm_request_failed` without provider text.
- Compact `tool_results` includes only error code/retryability, including the agent-level error; SSE terminal errors use that safe category.
- Reliability tests cover analytics/RAG partial fallbacks, abstention, warnings, constraints, malformed corrective calls, duplicate/limit guards, embedding timeout, and safe LLM failure output.

## Important Technical Decisions

- `docs/week3_codex_todo.md` overrides the old strict-priority routing description.
- LLM responsibility is limited to intent, recent-history reference resolution, approved tool choice/order, structured arguments, synthesis, and used-evidence selection.
- Deterministic code owns validation, SQL, calculations, filters, capacity constraints, sample warnings, provenance, persistence, and SSE serialization.
- Tool calls are sequential and bounded to three. No arbitrary SQL, planner graph, web search, or parallel tool execution was introduced.
- A missing report is a tool result, not an implicit fallback. The Router decides whether to call analytics/RAG afterward.
- Comparisons are allowed only when all requested enabled SKUs have the same non-empty `capacity_tier`.
- Low sample size warns; it does not block otherwise valid results.
- No-data cannot be filled from model prior knowledge.
- Citations are two-layer: exact evidence preview plus stable source/document metadata, including the expandable review detail already owned by PostgreSQL.
- SSE exposes execution facts only. It never includes model scratchpad, hidden planning, or chain-of-thought.
- Provider exception strings and stack traces are not included in tool results, compact chat metadata, or SSE errors.

## Key Files and Responsibilities

- `backend/app/agent/schemas.py`: all Agent/tool/evidence/citation/conversation/streaming contracts.
- `backend/app/agent/tool_sql.py`: `AnalyticsService`, fixed-operation validation and neutral metric assembly.
- `backend/app/db/repositories/analytics_repo.py`: deterministic PostgreSQL aggregate statements.
- `backend/app/agent/tool_rag.py`: `RagRetrievalService`, filter enforcement, Milvus orchestration, hydration verification, citation selection.
- `backend/app/db/repositories/evidence_repo.py`: mention + document hydration with quality/dashboard rechecks.
- `backend/app/agent/tool_report.py`: `ReportService`, read-only report behavior.
- `backend/app/db/repositories/report_repo.py`: existing-report lookup.
- `backend/app/agent/llm.py`: small OpenAI-compatible chat-completions/function-call adapter.
- `backend/app/agent/router.py`: bounded multi-tool loop, system policy, grounding/failure/citation rules, real-time lifecycle callbacks.
- `backend/app/agent/conversation.py`: recent-history orchestration and compact persistence shapes.
- `backend/app/db/repositories/conversation_repo.py`: session/message queries, row locking, deterministic turn persistence.
- `backend/app/api/ask.py`: request-scoped dependency composition and thin SSE transport/error/transaction boundary.
- `backend/app/api/auth.py`: configured-password login and `/api/auth/me` endpoints.
- `backend/app/core/security.py`: JWT helpers, constant-time configured-password comparison, and bearer identity dependency.
- `backend/app/main.py`: registers the ask and dashboard routers.
- `backend/app/core/settings.py` and `.env.example`: `MIN_RELIABLE_SAMPLE=20`, `MAX_RAG_TOP_K=20`, `RECENT_MESSAGE_LIMIT=8`, JWT settings, and `ADMIN_PASSWORD`.
- `backend/app/db/repositories/schemas.py`: typed rows used by the new repositories.
- `pipelines/enrichment/aspect_extractor.py`: Week 2-compatible bounded context reconstruction needed by citation hydration; no context exceeds 200 characters.
- `tests/test_agent_*.py`, `tests/test_tool_*.py`, `tests/test_conversation_service.py`, `tests/test_ask_api.py`, and `tests/test_auth_api.py`: Phase 1-9 behavioral coverage.

## Data and Schema Assumptions

- PostgreSQL remains the relational source of truth and SQLAlchemy 2.0 async sessions remain the access pattern.
- Analytics are mention-based. `review_count` is `count(distinct aspect_mentions.document_id)`; `mention_count` is `count(aspect_mentions.id)`.
- Analytics join `skus` by `skus.sku_code == aspect_mentions.sku_code` and always require `skus.dashboard_enabled = true` plus `aspect_mentions.quality_score >= settings.aspect_quality_threshold`.
- Week filtering uses inclusive integer ISO-week IDs (`YYYYWW`) stored in `aspect_mentions.week_id` and `weekly_reports.week_id`.
- Sentiment values are `positive`, `negative`, and `neutral`; aspect values must come from `pipelines.enrichment.prompts.ASPECT_LABELS`.
- Capacity tiers come from `skus.capacity_tier`; locked SKU membership comes from `pipelines.config.targets.LOCKED_SKU_CODES`.
- Milvus metadata fields are `sku_code`, `aspect_label`, `sentiment`, `week_id`, and `quality_score`; vector `id` is exactly `aspect_mentions.id`.
- Evidence hydration joins `aspect_mentions.document_id -> documents.id` and `documents.sku_id -> skus.id`, retaining platform, date, URL, title, rating, and review body.
- Report lookup joins `weekly_reports.sku_id -> skus.id` and never writes.
- Conversation metadata uses existing JSONB columns `tool_calls`, `tool_results`, and `cited_ids`.

## Contracts That Must Be Preserved

- Do not add an `execute_sql(sql: str)` tool or let the Router/endpoint build repository queries.
- Preserve the shared dashboard/Agent quality threshold and dashboard-enabled filtering.
- Preserve `aspect_mentions.id` as the only vector/evidence provenance ID.
- Preserve exact-substring `mention_text` and bounded `context_window` behavior.
- Preserve same-tier comparison and non-blocking low-sample warnings.
- Preserve the distinction between retrieved evidence and final citations.
- Preserve the three attempted-tool-call maximum and duplicate-call guard.
- Preserve recent visible-message inference; do not add hidden active filters or summarization in Week 3.
- Preserve compact chat metadata and transaction-consistent assistant output.
- Keep `/api/ask` thin; authentication remains a dependency and must not move into tools or the Router.
- Do not alter existing Dashboard API response contracts or Week 2 processing-state transitions.

## Tests and Acceptance Status

Implemented and verified:

- Phase 1 schema validation and serialization.
- Phase 2 all six analytics operations, constraints, warnings, invalid inputs, empty data, and repository filter SQL.
- Phase 3 semantic/filter/provenance/hydration/no-data/citation-selection behavior.
- Phase 4 report hit/miss/validation/no-side-effect behavior.
- Phase 5 single/multi-tool, report fallback, abstention, warnings, constraints, failures, call limit, malformed and duplicate calls.
- Phase 6 create/reuse/recent-N/follow-up/metadata/failure/ordering behavior.
- Phase 7 new/existing sessions, SQL/RAG/combined sequences, citation filtering, partial/request failures, real lifecycle timing, commit boundary, and cancellation.
- Phase 8 login, invalid/missing/malformed/expired tokens, `/auth/me`, protected ask, and public-dashboard decision.
- Phase 9 deterministic error categories, safe embedding/LLM timeout handling, compact error metadata, partial fallbacks, no-data, warnings, constraints, malformed-call recovery, duplicate guard, and limit guard.
- Phase 10 deterministic 19-query smoke/golden acceptance set.
- Phase 11 Week 2 regression, documentation synchronization, and Checkpoint F.

Latest commands and outcomes:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_agent_schemas.py tests/test_tool_sql.py tests/test_tool_rag.py tests/test_tool_report.py tests/test_agent_llm.py tests/test_agent_router.py tests/test_conversation_service.py tests/test_ask_api.py -q
# 116 passed, 3 warnings

.\.venv\Scripts\python.exe -m pytest tests/test_week3_golden_queries.py -q
# 20 passed, 2 warnings

.\.venv\Scripts\python.exe -m pytest tests/test_aspect_extractor.py tests/test_aspect_evidence_regression.py tests/test_embedder.py tests/test_milvus_repo.py tests/test_quality_scorer.py tests/test_sku_activation.py tests/test_dashboard_api.py tests/test_worker_jobs.py -q
# 54 passed, 3 warnings

.\.venv\Scripts\python.exe -m pytest -q
# 190 passed, 3 warnings
```

Warnings are third-party deprecations from PyMilvus/pkg_resources, environs/Marshmallow, and Starlette TestClient.

Final sign-off verification:

- Phase 10 provides 19 documented deterministic smoke/golden cases with expected and actual tool sequences, arguments, warnings, citations, status, and fixture timing.
- Phase 11 confirms the Week 2 processing pipeline, 1024-dimensional embedding contract, PostgreSQL/Milvus UUID alignment, dashboard APIs, shared quality threshold, and independent APScheduler worker remain covered by regression tests.
- No live external LLM/Milvus/PostgreSQL end-to-end run was performed during this final handoff audit; current acceptance evidence is the deterministic test suite.

## Known Issues / Limitations

- The authentication scope is intentionally limited to one configured password and one fixed `admin` identity; there is no user management, refresh flow, or RBAC.
- No live external LLM/Milvus/PostgreSQL failure-injection or end-to-end run has been performed; current acceptance evidence uses deterministic fakes/mocks.
- `answer_delta` chunks the completed final answer in 240-character pieces; it does not forward provider token deltas.
- Failures while constructing FastAPI dependencies before the SSE generator starts can use normal FastAPI error handling rather than an SSE `error` event.
- Concurrent requests for the same session can read the same pre-turn history. Persistence order is serialized, but semantic conflict resolution is not implemented.
- Recent-N counts messages, not complete turns; an odd configured N can begin with an assistant message.
- Week 3 implementation and documentation are committed locally and tagged `v0.3-week3`. The untracked `uv.lock` is intentionally excluded because no dependency declaration changed; it may be regenerated when dependency resolution is intentionally updated.
- Documentation contains some older encoding artifacts in terminal rendering; files are UTF-8 and should be read explicitly as UTF-8 in PowerShell.

## Next Phase

Week 3 is signed off. Week 4 remains intentionally unimplemented: frontend dashboard/chat work, the larger 50-query evaluation system, live provider evaluation, fresh-database Alembic validation, and runbook polish are outside this completed scope.

## Files the Next Codex Thread Should Read First

1. `docs/week3_codex_todo.md` — primary locked specification and updated status.
2. `docs/week3_handoff.md` — current implementation map and verification state.
3. `backend/app/agent/router.py`, `backend/app/agent/tool_sql.py`, and `backend/app/agent/tool_rag.py` — grounded-tool and failure contracts that golden cases exercise.
4. `backend/app/api/ask.py`, `backend/app/core/security.py`, and `backend/app/api/auth.py` — protected streaming/error boundary.
5. `backend/app/main.py` — router registration pattern.
6. `backend/app/agent/schemas.py`, `router.py`, and `conversation.py` — contracts that auth must not disrupt.
7. `tests/test_auth_api.py`, `tests/test_ask_api.py`, and `tests/test_dashboard_api.py` — HTTP testing conventions and regression surface.

## Recommended First Validation Commands

```powershell
git status --short
git diff --check
.\.venv\Scripts\python.exe -m pytest tests/test_auth_api.py tests/test_agent_schemas.py tests/test_tool_sql.py tests/test_tool_rag.py tests/test_tool_report.py tests/test_agent_llm.py tests/test_agent_router.py tests/test_conversation_service.py tests/test_ask_api.py -q
.\.venv\Scripts\python.exe -m pytest -q
```
