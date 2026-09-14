# Week 4 Phase 3 Handoff

Recorded after the Phase 0–3 delivery thread. This is a handoff record, not a
claim that the full Week 4 product is complete.

## Completed phases

- **Phase 0 — Contract Freeze** (`39054c0`): public product/API contracts,
  evidence/citation rules, report persistence/SSE lifecycle, auth behavior, and
  evaluation gates are frozen in `docs/week4_contract_freeze.md`.
- **Phase 1 — Frontend Foundation** (`7037074`): Next.js route skeletons,
  shared app shell/sidebar, page/state primitives, TanStack Query provider, and
  environment-driven API client are present for `/login`, `/overview`,
  `/skus/[sku_code]`, `/compare`, `/reports`, and `/ask`.
- **Phase 2 — Frontend Authentication** (`4f70786`): the frontend reuses the
  existing one-password JWT flow, checks `/api/auth/me` after browser refresh,
  clears invalid sessions on `401`, protects the application shell, and supports
  logout and login errors.
- **Phase 3 — Dashboard API Expansion** (`accb960`): the read-only product APIs
  below are implemented and documented.

Phases 4–15 are not complete. The next product phase is **Phase 4 — Overview
Page**. The existing overview route is still a foundation placeholder; do not
claim a completed product dashboard before Phase 4.

## Phase 3 public API contract

All dashboard reads remain public; only `/api/ask` remains bearer-protected.

| Route | Response / behavior |
|---|---|
| `GET /api/skus` | Dashboard-enabled SKU metadata only: `sku_code`, `brand`, `model`, `capacity_wh`, `capacity_tier`, `is_competitor`, `dashboard_enabled`. |
| `GET /api/skus/{sku_code}?week_id=YYYYWW` | One SKU's metadata, review/mention counts, sentiment breakdown, and top aspects. Unknown/disabled SKU is `400`; absent scoped week is `404`. |
| `GET /api/skus/{sku_code}/evidence?week_id=YYYYWW&sentiment=positive|negative|neutral&limit=1..20` | Shared `AnswerCitation[]`. Only dashboard-enabled, quality-qualified PostgreSQL evidence is selected. |
| `GET /api/compare?sku_code=<code>&sku_code=<code>[&week_id=YYYYWW]` | Neutral `ComparisonResponse`: selected week, capacity tier, `SkuComparisonMetrics[]`, and warnings. It rejects invalid ISO weeks, disabled/unknown SKUs, missing tiers, and cross-tier comparisons in backend application code. Constraint errors use `{ detail: { code, message, retryable, details } }`. |
| `GET /api/reports/{week_id}?sku_code=<code>` | Existing read-only `WeeklyReportPayload`; validates ISO week and locked/dashboard-enabled SKU through `ReportService`; missing rows are `404`. |

`GET /api/weeks`, `GET /api/overview`, and
`GET /api/skus/{sku_code}/trends` remain the existing contracts and should be
reused by later pages.

## Architecture decisions to preserve

- PostgreSQL remains the aggregate and provenance authority. The API never
  exposes arbitrary SQL or delegates counts/rates/filtering to the frontend.
- Dashboard API scope always applies `dashboard_enabled` and the shared
  `ASPECT_QUALITY_THRESHOLD`.
- Same-tier comparison is enforced by the existing `AnalyticsService` and
  `AnalyticsRepository`; UI filtering is not a correctness boundary.
- The common evidence display type is the existing `AnswerCitation`, not a new
  evidence identifier. `mention_id == aspect_mentions.id == Milvus vector ID`;
  its document and SKU IDs must match the embedded source metadata.
- SKU evidence ordering is deterministic: quality score descending, persisted
  mention creation time descending, then mention ID.
- Weekly reports have no durable report-to-mention relation. Report viewing is
  limited to stored Markdown/summary fields; report-level interactive citations
  must not be invented.
- There are no Phase 0–3 database migrations. `weekly_reports` remains one row
  per `(sku_id, week_id)` and Phase 3 adds no write path.
- `/api/ask` SSE is unchanged by Phase 3: successful streams emit tool lifecycle
  events, answer deltas, used citations, and `done`; request errors use the safe
  structured error envelope. Weekly-report generation SSE is still planned,
  not implemented.
- The frozen release gates are not implemented yet: the planned 50-case semantic
  dataset, evaluation runner, and release verification belong to Phases 11–14.
  `shared/eval/rag_eval.py` is not present in the current checkout.

## Components and tests added in this thread

- Frontend: `AppShell`, `FeaturePlaceholder`, `PageLayout`, loading/empty/error
  states, `QueryProvider`, environment-driven API client, `AuthProvider`, and
  `AuthGate`.
- Backend: dashboard response models/dependencies in
  `backend/app/api/dashboard.py`, plus `AspectRepository.get_sku_week_summary`
  and `get_sku_evidence`.
- Tests: frontend API/auth/login tests; backend dashboard API and SKU activation
  scope tests. Phase 3 also preserved the Week 2 and Week 3 regression suites.

## Known limitations, deferred work, and risks

- Phases 4–10 product behavior is not implemented: the routed frontend pages do
  not yet consume the dedicated reads as full product experiences; report
  generation/regeneration and its SSE lifecycle do not exist.
- Chat has no dedicated Week 4 browser experience yet; Phase 9 must consume the
  existing authenticated `/api/ask` SSE contract without changing its grounding
  guarantees.
- No 50-query semantic dataset, semantic evaluation runner, fresh-environment
  release validation, or final documentation/demo pass exists yet.
- README and `docs/todo.md` still describe the original broad Week 4 checklist;
  this handoff document is the accurate phase-level record until a later
  documentation phase reconciles those files.
- The current checkout contains unrelated, uncommitted Agent reliability work in
  `backend/app/agent/llm.py`, `backend/app/agent/router.py`,
  `backend/app/api/ask.py`, and their tests, plus uncommitted Week 3 live-E2E
  documentation updates, `docs/week4_codex_development_plan.md`, and `uv.lock`.
  These are intentionally not included in the Phase 0–3 commits. Review and
  either commit or discard them before beginning Phase 4.
- Full-repository Ruff currently reports four pre-existing style issues in
  `backend/app/core/security.py` and `tests/test_week3_golden_queries.py`.
  They do not affect the passing test/build checks but prevent a clean full-Ruff
  gate.

## Validation commands last run successfully

```powershell
.\.venv\Scripts\python.exe -m pytest -q
# 213 passed

cd frontend
npm run lint
npm run typecheck
npm run test
# 3 files / 8 tests passed
npm run build
```

The focused Phase 3 regression command also passed before the full run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_dashboard_api.py tests/test_tool_sql.py tests/test_tool_report.py tests/test_tool_rag.py tests/test_auth_api.py tests/test_ask_api.py tests/test_aspect_extractor.py tests/test_aspect_evidence_regression.py tests/test_embedder.py tests/test_milvus_repo.py tests/test_quality_scorer.py tests/test_sku_activation.py tests/test_worker_jobs.py tests/test_week3_golden_queries.py -q
# 159 passed
```
