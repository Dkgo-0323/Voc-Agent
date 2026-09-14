# Week 4 Phase 7 Handoff

## Completed phase

Phase 7 adds authenticated weekly-report generation at `POST /api/reports/generate`.
The endpoint accepts `{ "sku_code": string, "week_id": integer }`, validates
the locked/dashboard-enabled SKU and ISO week, then emits a safe SSE lifecycle:
`report_started`, `stage_started`, `stage_completed`, zero or more
`report_delta`, and exactly one terminal `report_completed` or `error`.

## Preserved design

- PostgreSQL remains the source of truth. `weekly_reports` remains one row per
  `(sku_id, week_id)`; no migration, job queue, version history, Agent tool, or
  comparison-specific LLM path was added.
- The service collects fixed deterministic analytics and filtered RAG evidence,
  asks the existing provider adapter for a bounded JSON candidate, validates the
  required Markdown sections, and stages an insert/update in the request
  transaction. `report_completed` is emitted only after commit.
- A failed retrieval, synthesis, validation, persistence, cancellation, or commit
  rolls back uncommitted work; an existing report is never deleted first.
- The report writer receives no authority to invent metrics, quotes, causes,
  recommendations, or competitors. The prompt requires it to state when
  comparison data is absent.

## Important limitation

`weekly_reports` does not persist report-to-mention IDs. Reports can be
evidence-grounded during generation, but Phase 7 deliberately does not emit or
render report-level interactive citations. Adding them requires a separately
reviewed durable provenance contract.

## New modules and tests

- `backend/app/reporting/service.py`: collection, bounded synthesis validation,
  and transactional staging.
- `backend/app/api/reports.py`: JWT-protected SSE transport.
- `backend/app/db/repositories/report_repo.py`: non-committing single-row upsert.
- `tests/test_report_generation.py`: generation, no-data, invalid candidate,
  invalid scope, terminal SSE, commit, and rollback behavior.

## Next phase

Phase 8 is the Weekly Report Frontend. It should consume only the persisted
`WeeklyReportPayload` returned by `report_completed`, treating `report_delta` as
temporary display progress.
