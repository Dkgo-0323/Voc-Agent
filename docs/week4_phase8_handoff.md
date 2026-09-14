# Week 4 Phase 8 Handoff

## Completed phase

`/reports` is now a client-side weekly-report viewer and explicit generation
workspace. It uses TanStack Query for weeks, SKUs, and existing report reads;
local state is limited to selection and report-stream presentation.

## User-visible behavior

- Select an enabled SKU and covered week, then view a stored report when one
  exists.
- A `404` report lookup becomes a no-report state with an explicit Generate
  button. Refreshing or changing scope never starts generation automatically.
- Generate and Regenerate consume `POST /api/reports/generate` SSE and show
  friendly lifecycle messages instead of raw events or backend details.
- During regeneration, the persisted report remains visible until the stream
  emits `report_completed`; only that committed payload replaces the view.
- Terminal stream errors show retry UI and leave the previous report displayed.

## Provenance limitation preserved

The Phase 7 report model has no stored report-to-mention relation. The viewer
therefore explicitly explains that report-level citation cards are unavailable;
it does not infer or fabricate evidence/citation UI. Shared `EvidenceCard`
continues to serve SKU, comparison, and Agent citations.

## Files and tests

- `frontend/components/reports/report-dashboard.tsx`: report workspace and
  safe Markdown section rendering.
- `frontend/lib/api/reports.ts`: report read and authenticated SSE client.
- `frontend/tests/report-dashboard.test.tsx`: existing report/no auto-generate,
  explicit generation, completed replacement, and failed regeneration coverage.

## Next phase

Phase 9 is Ask Your Data Frontend. It should reuse the existing `/api/ask`
SSE adapter and shared citation presentation without changing Agent behavior.
