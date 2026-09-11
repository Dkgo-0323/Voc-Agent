# Week 4 Phase 10 Handoff

## Verified status

Week 4 Phases 0 through 10 are implemented. The current branch head is the
Phase 10 reliability commit `ceb94d4`; it follows the Phase 7 report backend,
Phase 8 report UI, and Phase 9 Ask UI commits. No migration was added in
Phases 7–10. The next planned work is **Phase 11 — Build the 50-Query Golden
Dataset**. Do not begin Phase 12's evaluation runner or modify Agent behavior
until Phase 11's deliberately reviewed dataset is in place.

## Preserved architecture decisions

- PostgreSQL remains the relational source of truth. Milvus uses the exact
  `aspect_mentions.id` UUID as its vector ID, with no secondary mapping.
- The controlled handwritten Agent remains the only Agent architecture. The
  LLM can select approved tools and synthesize supported text; deterministic
  services retain calculations, quality filtering, validation, capacity-tier
  rules, provenance, persistence, and SSE serialization.
- `tool_sql` never accepts arbitrary SQL, server-side same-capacity-tier
  validation remains authoritative, and the frontend only narrows impossible
  choices for usability.
- Conversation context remains PostgreSQL-backed recent-N messages (default
  eight). The browser stores only its visible conversation and returns the
  committed `session_id` for a follow-up; it has no hidden Agent filters,
  summaries, or state.
- Citation provenance remains traceable. SKU, comparison, and Ask views use
  evidence/citation data containing the stable mention/document IDs. Ask
  renders only citations emitted as used by the Agent. Reports deliberately do
  not invent citation cards because `weekly_reports` has no durable
  report-to-mention relation.

## Implemented contracts and surfaces

- `POST /api/ask` remains authenticated SSE: `tool_started`,
  `tool_completed`, `answer_delta`, zero or more used `citation`, and terminal
  `done` or structured `error`. Frontend `streamAsk` accepts optional
  `sessionId` and `AbortSignal`.
- `POST /api/reports/generate` remains authenticated SSE:
  `report_started`, stage events, temporary `report_delta`, and terminal
  `report_completed` or structured `error`. `report_completed` carries the
  committed `WeeklyReport` payload (`report_id`, `sku_code`, `week_id`,
  `report_md`, `summary`, `generated_at`). Frontend report streaming now also
  accepts an optional `AbortSignal`.
- `/reports` retrieves persisted reports only and never generates on load. It
  keeps an old report visible during regeneration, locks scope controls during
  a request, supports cancellation, and treats an EOF without a terminal event
  as a safe retryable failure.
- `/ask` provides safe streamed Markdown-like text, friendly tool lifecycle
  labels, used-citation popovers, no-data abstention, recent-message follow-up,
  and cancellation. A disconnected stream or `done: error` is never displayed
  as success.
- `/compare` uses the existing authenticated Ask endpoint for a one-shot
  summary only. It now supports local cancellation and safe terminal-event
  validation; it does not create comparison-specific Agent state or logic.
- `frontend/app/(app)/error.tsx` supplies a safe retry boundary. Auth bootstrap
  failures provide retry UI, and long evidence/provenance values wrap instead
  of overflowing citation cards and popovers.

## Tests and validation currently passing

Run from `frontend/`:

```powershell
npm run lint; npm run typecheck; npm run test; npm run build
```

Last result: lint and typecheck passed; Vitest passed **34 tests in 8 files**;
the Next.js production build passed.

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_agent_llm.py tests\test_agent_router.py tests\test_agent_schemas.py tests\test_ask_api.py tests\test_conversation_service.py tests\test_tool_rag.py tests\test_tool_report.py tests\test_tool_sql.py tests\test_week3_golden_queries.py tests\test_report_generation.py -q
```

Last result: **146 passed**. The environment reports third-party deprecation
warnings from `pymilvus`, `environs`, and Starlette's `TestClient`; they did not
fail the suite.

## Deferred work, risks, and technical debt

- Phase 11 has not started: there is no separate curated 50-query semantic
  Golden dataset, evaluation runner, LLM judge, release-gate result, or human
  review record. The existing deterministic Week 3 19-query suite remains the
  regression baseline and must not be replaced.
- Browser-level release E2E, clean PostgreSQL migration verification, and the
  reproducible README/runbook remain Phase 14/15 work. The current frontend
  tests are component/unit integration coverage, not a live browser/backend
  release run.
- The frontend's lightweight Markdown rendering supports the required report
  sections, paragraphs, and bullet lists; it is not a general CommonMark
  renderer.
- Both SSE adapters parse the established `data:` JSON stream directly. A
  malformed record becomes a safe client failure through the consumer error
  path; reconnect/resume semantics are intentionally not implemented.
- Report-level evidence cannot be made interactively traceable without a
  separately reviewed persistence/schema contract. Do not fabricate a UI-only
  mapping.
- The branch is local and ahead of its origin; no commits from this handoff
  should be pushed without explicit operator direction.
