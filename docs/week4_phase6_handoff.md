# Week 4 Phase 6 Handoff

Recorded after delivery of Week 4 Phases 0–6. This is not a claim that the
full Week 4 product is complete.

## Completed phases

- **Phase 0 — Contract Freeze** (`39054c0`): product/API, evidence, report,
  auth, and evaluation contracts are frozen in `docs/week4_contract_freeze.md`.
- **Phase 1 — Frontend Foundation** (`7037074`): routes, app shell, TanStack
  Query, API client, shared page/state primitives, and visual baseline.
- **Phase 2 — Frontend Authentication** (`4f70786`): configured-password JWT
  login, session bootstrap, 401 handling, logout, and protected app shell.
- **Phase 3 — Dashboard API Expansion** (`accb960`): public SKU metadata,
  detail, evidence, same-tier comparison, and report-read APIs.
- **Phase 4 — Overview** (`ea551e8`): week-selectable portfolio metrics,
  sentiment/aspect view, enabled SKU navigation, and UI-state coverage.
- **Phase 5 — SKU Detail** (`669d4c7`): Level 2 SKU metrics, sentiment/aspect
  distribution, raw trend rows, positive/negative evidence, and stateless Ask
  CTA. It introduced the shared `EvidenceCard` presentation component.
- **Phase 6 — Competitor Compare** (`9130fbd`): same-tier pair selection,
  deterministic comparison composition, evidence, and optional controlled-Agent
  summary through existing `/api/ask` SSE.

The next phase is **Phase 7 — Weekly Report Backend**.

## Contracts and decisions to preserve

- PostgreSQL remains the aggregate/provenance authority; the frontend performs
  presentation formatting only. Milvus vector ID remains exactly
  `aspect_mentions.id`.
- The shared frontend `EvidenceCitation` mirrors `AnswerCitation`: exact
  `evidence_preview`, `mention_id`, `document_id`, source SKU/platform/date,
  source URL, title, rating, and expandable review text. `EvidenceCard` makes
  these provenance fields available without creating a second evidence ID.
- Dashboard endpoints remain public; `/api/ask` is bearer-protected. Frontend
  session behavior remains the existing one-password JWT flow.
- SKU Detail filters selected weeks using server-returned `skus_covered` and
  does not ask the backend for unsupported scoped-week inventory.
- Compare restricts the second selector to the first SKU's same tier but treats
  this only as UX. The existing backend still rejects cross-tier direct requests
  with `capacity_tier_mismatch`.
- Compare uses `GET /api/compare` for deterministic metrics, existing SKU
  detail/trend/evidence APIs for supporting panels, and the existing controlled
  Agent for optional synthesis. The summary passes explicit SKU codes and ISO
  week in the visible request message; no hidden Agent comparison state or
  comparison-specific LLM subsystem exists.
- The frontend SSE helper consumes the established event union:
  `tool_started`, `tool_completed`, `answer_delta`, `citation`, `done`, and
  `error`. Compare renders answer deltas and Agent-selected citations only;
  it does not expose raw tool payloads or reasoning. A 401 dispatches the
  existing auth-clear event.
- No migrations, ORM changes, API routes, database writes, or Agent tool
  changes were introduced by Phases 4–6.

## New frontend modules

- `frontend/lib/api/dashboard.ts`: TypeScript mirrors and fetchers for existing
  dashboard, SKU detail/trend/evidence, and comparison contracts.
- `frontend/components/overview/overview-dashboard.tsx`: Phase 4 page.
- `frontend/components/evidence/evidence-card.tsx`: shared traceable evidence
  presentation.
- `frontend/components/sku/sku-detail-dashboard.tsx`: Phase 5 page.
- `frontend/lib/api/ask.ts`: authenticated browser SSE adapter for existing
  `/api/ask`; it is reusable by the future Ask page.
- `frontend/components/compare/comparison-dashboard.tsx` and
  `controlled-summary.tsx`: Phase 6 page and explicit one-shot Agent summary.

## Tests and validation status

Frontend tests cover overview data/week selection and states; SKU Detail covers
all five locked SKU codes plus invalid/empty/evidence/CTA/loading/error cases;
Compare covers a valid same-tier pair, frontend cross-tier option exclusion,
evidence rendering, and the existing Agent-summary request/citation flow.

Commands most recently observed passing in this thread:

```powershell
cd frontend
npm run lint
npm run typecheck
npm run test
npm run build

cd ..
.\.venv\Scripts\python.exe -m pytest tests/test_dashboard_api.py tests/test_tool_sql.py tests/test_agent_router.py tests/test_ask_api.py tests/test_tool_rag.py -q
# 102 passed, 3 third-party deprecation warnings
```

The last full frontend run reported 22 passing tests. Frontend commands use the
installed Next.js 16 runtime; read `frontend/AGENTS.md` and the relevant local
Next docs before future frontend edits.

## Known limitations and risks

- Phases 7–15 remain incomplete: report generation/replacement and report SSE,
  report viewer, dedicated Ask page, UX/reliability pass, semantic 50-query
  evaluation, release verification, and final documentation/runbook.
- `README.md` remains empty; the TODO is now phase-aware but final setup/demo
  documentation belongs to Phase 15.
- `weekly_reports` has no durable report-to-mention relationship. Do not invent
  interactive report citations without a separately reviewed schema contract.
- The current compare UI intentionally has no product “winner”; deterministic
  metrics and the controlled Agent must remain neutral and grounded.
- The browser SSE adapter is covered through comparison-component mocks, not a
  live provider/browser stream. Its behavior must be exercised against a live
  authenticated backend during later release validation.
- A unique-tier SKU has no comparison peer; Compare now keeps selectors visible
  with an empty-state explanation so users can choose another tier.
- `shared/eval/rag_eval.py` is absent despite older TODO wording. Evaluation
  work begins in Phase 11 and should not assume that file exists.
- Earlier handoff text about uncommitted reliability work is stale: those
  changes are committed in `12f194e`; `uv.lock` is committed in `3e24464`.

## Recommended first checks for the next thread

```powershell
git status --short --branch
git diff --check
cd frontend
npm run lint
npm run typecheck
npm run test
npm run build
cd ..
.\.venv\Scripts\python.exe -m pytest tests/test_dashboard_api.py tests/test_tool_sql.py tests/test_agent_router.py tests/test_ask_api.py tests/test_tool_rag.py -q
```
