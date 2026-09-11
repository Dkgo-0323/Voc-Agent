# VOC Agent — Week 4 Productization, Evaluation & Release Plan

> Purpose: This document is an execution guide for Codex.
>
> Codex should implement Week 4 **phase by phase**. Do not jump ahead, do not combine large phases unless explicitly instructed, and do not silently expand scope.
>
> The operator will send the phase prompt for one phase at a time.

---

# 0. Week 4 Mission

Week 1–3 already established:

- PostgreSQL + Milvus infrastructure
- ingestion / sanitize / enrich / embedding pipeline
- dashboard aggregation APIs
- controlled handwritten Agent
- deterministic `tool_sql`
- structured `tool_rag`
- read-only `tool_report`
- PostgreSQL-backed conversation persistence
- JWT auth
- structured SSE `/api/ask`
- deterministic Week 3 acceptance suite
- Week 3 live backend E2E validation

Week 4 is **not** primarily about adding more Agent capability.

Week 4 is a **productization + evaluation + release milestone**.

The target is:

```text
Login
  ↓
Overview
  ├── SKU Detail
  ├── Competitor Compare
  ├── Weekly Report
  └── Ask Your Data
          ↓
      Controlled Agent
          ↓
 SQL / RAG / Report
          ↓
 Answer + citations
```

The finished MVP should be:

1. usable from the browser;
2. reproducible from a clean environment;
3. visually coherent enough for a portfolio demo;
4. grounded in deterministic backend calculations and traceable evidence;
5. evaluated using both deterministic tests and semantic evaluation;
6. protected against major provenance, comparison, unsupported-claim, and abstention failures.

---

# 1. Locked Week 4 Product Decisions

These decisions are fixed unless a later phase explicitly reopens them.

## 1.1 Product target

Engineering-complete MVP is the minimum bar.

The implementation may approach a product-like SaaS experience, but visual polish must not displace reliability, evaluation, reproducibility, or traceability.

## 1.2 Frontend starting point

Assume `frontend/` is currently only a Next.js skeleton or near-empty application.

## 1.3 Main product pages

The final frontend should provide:

```text
/login
/overview
/skus/[sku_code]
/compare
/reports
/ask
```

## 1.4 Overview

Use a combined portfolio + SKU monitoring view.

Expected information:

- selected week
- review volume
- overall sentiment
- notable portfolio movement
- positive / negative aspect summaries
- SKU cards for locked dashboard-enabled SKUs

## 1.5 SKU Detail

Implement **Level 2** depth:

- review volume
- sentiment distribution
- aspect distribution
- historical / weekly trend
- positive evidence
- negative evidence
- CTA to ask a question about the SKU

Do not implement root-cause workflow or action recommendation engines in Week 4.

## 1.6 Competitor Compare

Comparison must respect `capacity_tier`.

The frontend must only allow compatible same-tier SKU choices.

The backend must **independently validate** the same rule.

The comparison page should include:

- sentiment distribution
- aspect distribution
- weekly trends
- representative evidence
- AI-generated grounded comparison summary
- follow-up CTA into Ask Your Data

Do not duplicate Agent logic in a second comparison-specific LLM subsystem.

## 1.7 Weekly Report

Week 4 includes both:

- report viewer;
- report generation.

Report generation should use **SSE streaming**.

The report may be regenerated.

Regeneration means:

```text
existing report
      ↓
generate new candidate
      ↓
validate candidate
      ↓
successful?
  ┌───────┴────────┐
  no               yes
  ↓                 ↓
keep old       atomic replace
```

Never delete or overwrite a valid old report before the replacement report has been completely generated and validated.

## 1.8 Frontend state management

Use:

```text
TanStack Query
├── server state
│   ├── weeks
│   ├── overview
│   ├── SKU detail
│   ├── trends
│   ├── comparison
│   └── reports
│
React Context
└── auth
│
Local React state / hooks
├── filters
├── current selections
├── popovers
├── chat stream
└── report stream
```

Do not add Redux or Zustand unless explicitly approved later.

## 1.9 Backend API style

Use dedicated read APIs.

Do not create a generic `/api/dashboard` aggregate endpoint.

Expected direction:

```text
GET  /api/weeks
GET  /api/skus

GET  /api/overview
GET  /api/skus/{sku_code}
GET  /api/skus/{sku_code}/trends

GET  /api/compare

GET  /api/reports/{week_id}
POST /api/reports/generate

POST /api/ask
```

Exact paths and schemas should be confirmed against the repository before implementation.

## 1.10 Chat UX

Users should see friendly operational status such as:

```text
Searching relevant reviews...
Calculating sentiment trends...
Generating response...
```

Users should **not** see:

- raw tool JSON;
- hidden reasoning;
- provider exception strings;
- internal chain-of-thought.

## 1.11 Citations

Citation UI target:

```text
claim... [1]
```

Clicking `[1]` opens a popover showing at minimum:

- review preview
- platform
- SKU
- week

Prefer reusing the same underlying evidence presentation model for:

- SKU evidence cards
- comparison evidence
- report citations
- chat citation popovers

## 1.12 Evaluation

Keep the existing deterministic Week 3 regression suite.

Add a new **50-query semantic Golden evaluation suite**.

Use:

- deterministic assertions where possible;
- LLM-as-a-Judge for semantic dimensions;
- human review for failed / borderline / sampled passing cases.

## 1.13 Release gates

Target thresholds:

| Metric | Gate |
|---|---:|
| Tool / routing correctness | >= 90% |
| Answer correctness | >= 85% |
| Retrieval relevance | >= 85% |
| Citation groundedness | >= 95% |
| Abstention correctness | >= 90% |
| Follow-up context correctness | >= 90% |
| Deterministic numeric correctness | 100% |
| Cross-tier business-rule violations | 0 |
| Citation provenance violations | 0 |
| Critical unsupported claims | 0 |

Threshold implementation details may be refined during the evaluation phase, but any change must be explicitly documented.

---

# 2. Global Engineering Rules for Codex

Codex must follow these rules in every phase.

## 2.1 Inspect before changing

At the beginning of each phase:

1. read `AGENTS.md` if present;
2. inspect the current git status;
3. inspect the relevant implementation before assuming it matches this plan;
4. read current `docs/arch.md`, `docs/todo.md`, README, schemas, tests, and related modules;
5. treat repository code as the source of truth for what is already implemented.

Do not reimplement existing functionality.

## 2.2 Preserve Week 1–3 contracts

Do not casually change:

- PostgreSQL as the relational database;
- Milvus UUID alignment;
- `aspect_mentions.id` provenance contract;
- quality filtering;
- capacity-tier comparison rule;
- fixed deterministic analytics boundary;
- handwritten Agent architecture;
- maximum controlled tool-call behavior;
- recent-N PostgreSQL conversation model;
- JWT behavior;
- structured `/api/ask` SSE contract;
- no-data abstention;
- structured safe error categories;
- existing Week 3 regression behavior.

If a change is necessary, stop and explain why before implementing it.

## 2.3 LLM responsibility boundary

Keep this separation:

```text
LLM
├── intent interpretation
├── synthesis
├── supported comparison wording
└── tool selection within approved contracts

Deterministic application code
├── validation
├── calculation
├── filtering
├── capacity-tier constraints
├── provenance
├── persistence
├── transaction safety
└── streaming serialization
```

Do not move deterministic business logic into prompts.

## 2.4 Avoid scope creep

Week 4 does **not** include:

- multi-user registration
- RBAC
- Redis
- Celery
- generic distributed job queue
- WebSocket architecture
- GraphQL
- Redux
- report version history
- admin panel
- ingestion-management UI
- custom SKU creation
- taxonomy editor
- arbitrary SQL
- long-term Agent memory
- conversation summarization
- multi-agent workflow
- elaborate animation systems
- production-grade cloud deployment

## 2.5 Work phase by phase

For each phase:

1. inspect;
2. summarize current state;
3. implement only the requested phase;
4. add or update tests;
5. run focused tests;
6. run relevant regression tests;
7. review the diff;
8. update docs if the phase changes a public contract;
9. report what changed;
10. propose a semantic local commit;
11. stop.

Do not begin the next phase automatically.

## 2.6 Git discipline

Prefer one or several small semantic commits per phase.

Examples:

```text
feat(frontend): add application shell and query client
feat(auth): add frontend login and session bootstrap
feat(api): add sku detail read model
feat(compare): add same-tier comparison page
feat(report): add streamed report generation
feat(eval): add semantic golden query suite
docs: finalize week 4 runbook and demo flow
```

Do not push unless explicitly requested.

---

# 3. Milestone Structure

```text
Milestone A — Product Foundation
Phase 0–3

Milestone B — Product Experience
Phase 4–10

Milestone C — Evaluation
Phase 11–13

Milestone D — Release
Phase 14–15
```

---

# Phase 0 — Contract Freeze

## Objective

Define all Week 4 interfaces before substantial implementation.

Do not build UI pages yet.

## Scope

Inspect and freeze:

- frontend route map;
- required backend endpoints;
- request / response schemas;
- report schema;
- evidence / citation view model;
- report SSE event contract;
- frontend auth behavior;
- comparison validation rules;
- evaluation metric definitions.

## Required investigation

Inspect:

- current FastAPI routes;
- Pydantic schemas;
- ORM models, especially `weekly_reports`;
- current `/api/ask` SSE implementation;
- current citation schema;
- current `tool_sql` comparison behavior;
- frontend package configuration;
- existing tests;
- existing `shared/eval/rag_eval.py`.

Do not invent fields that are not supported by existing data.

If the current schema cannot support a desired frontend feature, document the gap and add the smallest necessary backend contract.

## Expected outputs

Update documentation with:

1. route map;
2. API inventory;
3. request / response contracts;
4. frontend view models;
5. report structure;
6. report generation SSE lifecycle;
7. auth token/session rules;
8. explicit out-of-scope items;
9. Week 4 Definition of Done.

## Report SSE target

A reasonable target is:

```text
report_started
stage_started
stage_completed
report_delta
report_completed
error
```

Reuse existing streaming infrastructure and error envelopes where appropriate.

Do not expose provider exceptions or hidden reasoning.

## Exit Gate

Phase 0 is complete only when:

- every planned page has a clear data source;
- every new API has a documented purpose;
- report persistence behavior is defined;
- regenerate semantics are defined;
- SSE event ordering is defined;
- citation/evidence UI fields are defined;
- no major contract remains ambiguous.

## Suggested tests

No major new runtime implementation is required.

Run schema/import tests or existing API contract tests if documentation work touches types.

## Suggested commit

```text
docs(week4): freeze product and API contracts
```

## Codex Prompt

```text
Implement Week 4 Phase 0: Contract Freeze.

Do not implement product pages yet.

First inspect the current repository state, including AGENTS.md if present, git status, docs/arch.md, docs/todo.md, README, FastAPI routes, Pydantic schemas, ORM models, the existing /api/ask SSE implementation, citation/evidence models, tool_sql comparison rules, frontend skeleton, tests, and shared/eval/rag_eval.py.

Then reconcile the Week 4 plan with the actual implementation.

Your task is to freeze and document:
- frontend route map;
- required backend endpoints;
- request/response schemas;
- frontend view models;
- report structure;
- report generation SSE event lifecycle;
- report atomic regeneration semantics;
- auth/session behavior;
- same-capacity-tier comparison rules;
- evaluation dimensions and release gates;
- explicit Week 4 out-of-scope items.

Do not invent unsupported database fields. If the desired UI needs data not currently represented, identify the minimum contract change required.

Preserve all Week 1–3 architecture decisions and existing behavior.

After changes:
1. review the diff;
2. run any relevant documentation/schema/import tests;
3. summarize frozen contracts and unresolved risks;
4. propose a semantic local commit;
5. stop before Phase 1.
```

---

# Phase 1 — Frontend Foundation

## Objective

Turn the Next.js skeleton into a stable application foundation without implementing full feature pages.

## Scope

Implement:

- route skeletons;
- shared app layout;
- sidebar/navigation;
- TanStack Query provider;
- API client layer;
- common loading state;
- common empty state;
- common error state;
- environment configuration;
- basic typography and layout system;
- reusable page container primitives.

Expected routes:

```text
/login
/overview
/skus/[sku_code]
/compare
/reports
/ask
```

## Constraints

Do not:

- build full data visualizations yet;
- add Redux;
- add elaborate animation;
- hard-code business data into components;
- duplicate backend calculation logic.

## Exit Gate

- frontend starts successfully;
- every route renders;
- sidebar/navigation works;
- query client is available;
- API base URL is environment-driven;
- shared error/loading primitives exist;
- lint/typecheck pass.

## Suggested tests

Run the frontend's available equivalents of:

- install consistency check;
- lint;
- typecheck;
- unit/component tests if configured;
- production build.

## Suggested commit

```text
feat(frontend): establish week 4 application foundation
```

## Codex Prompt

```text
Implement Week 4 Phase 1: Frontend Foundation.

Inspect the existing frontend skeleton and package configuration first.

Implement only the shared frontend foundation:
- routes for /login, /overview, /skus/[sku_code], /compare, /reports, /ask;
- shared app layout and navigation shell;
- TanStack Query provider;
- environment-driven backend API client;
- common loading, empty, and error UI primitives;
- basic reusable layout/page primitives;
- a clean restrained visual baseline suitable for a portfolio SaaS-style dashboard.

Do not implement full page business features yet.
Do not introduce Redux, Zustand, GraphQL, elaborate animations, or frontend-side business calculations.

Preserve all existing backend behavior.

Run lint, typecheck, tests if configured, and production build.
Review the diff, summarize the architecture added, propose a semantic local commit, and stop before Phase 2.
```

---

# Phase 2 — Frontend Authentication

## Objective

Provide a complete frontend login/session/logout experience using the already implemented backend JWT system.

## Scope

Implement:

- `/login`;
- login request;
- token persistence according to the repository's chosen safe mechanism;
- `/api/auth/me` session bootstrap;
- authenticated application state;
- expired/invalid token handling;
- 401 handling;
- logout;
- redirect behavior;
- clear auth error states.

Dashboard read-only endpoints may remain public if the backend architecture intentionally keeps them public.

`/api/ask` remains protected.

## Constraints

Do not create:

- registration;
- multiple accounts;
- password reset;
- RBAC.

## Exit Gate

Verify:

- valid login;
- invalid password;
- browser refresh with valid session;
- expired/invalid token;
- protected Ask behavior;
- logout;
- no auth loop.

## Suggested commit

```text
feat(auth): add frontend jwt session flow
```

## Codex Prompt

```text
Implement Week 4 Phase 2: Frontend Authentication.

Inspect the existing backend auth endpoints and security behavior before coding. Reuse the existing configured single-password login, JWT, /api/auth/me, and protected /api/ask behavior.

Implement:
- /login page;
- login API integration;
- frontend auth context/session bootstrap;
- token handling consistent with the current backend contract;
- invalid/expired token handling;
- 401 handling;
- logout;
- appropriate redirects and user-visible errors.

Do not add registration, RBAC, password reset, or a new auth backend.

Add focused tests for auth flows where practical.
Run frontend lint/typecheck/build and relevant backend auth regressions.
Review the diff, summarize behavior, propose a semantic commit, and stop before Phase 3.
```

---

# Phase 3 — Dashboard API Expansion

## Objective

Add only the backend read models needed by the planned product pages.

## Expected API direction

Confirm exact routes against Phase 0 contracts, likely:

```text
GET /api/skus
GET /api/skus/{sku_code}
GET /api/compare
GET /api/reports/{week_id}
```

Continue using existing:

```text
GET /api/weeks
GET /api/overview
GET /api/skus/{sku_code}/trends
```

## Requirements

Backend must own:

- quality threshold filtering;
- dashboard-enabled SKU filtering;
- ISO week validation;
- capacity-tier comparison validation;
- deterministic percentages/counts;
- stable evidence metadata.

## Compare contract

Frontend filtering is not a security or correctness boundary.

Backend must reject invalid cross-tier comparisons even when called directly.

## Evidence contract

Define/reuse a stable evidence view model usable by:

- SKU Detail;
- Compare;
- Reports;
- Chat citation popovers.

## Exit Gate

- all read APIs required by Overview/SKU/Compare/Report viewer exist;
- validation is deterministic;
- tests cover invalid SKU/week/cross-tier cases;
- Week 2/3 API regression behavior remains unchanged.

## Suggested commit

```text
feat(api): add product read models for week 4 frontend
```

## Codex Prompt

```text
Implement Week 4 Phase 3: Dashboard API Expansion.

Use the Phase 0 frozen contracts and inspect current routes/services/repositories/tests first.

Add only the dedicated read APIs required by the product frontend, likely including:
- SKU metadata/list;
- SKU detail;
- same-tier comparison;
- weekly report retrieval.

Reuse existing /api/weeks, /api/overview, and SKU trends endpoints where possible.

Keep all deterministic business rules in backend application code:
- dashboard-enabled SKU filtering;
- quality threshold;
- valid ISO weeks;
- same-capacity-tier comparison;
- deterministic metrics;
- stable evidence/provenance metadata.

Create or reuse a shared evidence response model suitable for SKU evidence, comparison evidence, reports, and chat citation presentation.

Do not create a generic dashboard endpoint, arbitrary SQL, or move calculations into the frontend.

Add focused API/service/repository tests and run relevant Week 2/3 regressions.
Review the diff, document any public contract changes, propose a semantic commit, and stop before Phase 4.
```

---

# Phase 4 — Overview Page

## Objective

Build the main portfolio landing page.

## Required UX

```text
Week Selector

Portfolio Metrics
├── Review Volume
├── Sentiment Distribution
└── Notable Change

Aspect Overview
├── Positive
└── Negative

SKU Cards
├── EcoFlow DELTA 2
├── Jackery Explorer 1000
├── Jackery Explorer 240
├── Jackery Explorer 300
└── Anker SOLIX F2000
```

Exact metric availability must follow actual backend data.

Do not fabricate missing metrics.

## Requirements

- selected week drives all relevant queries;
- loading state;
- empty-data state;
- API error state;
- responsive enough for laptop demo;
- SKU cards navigate to SKU detail.

## Exit Gate

- page works for multiple weeks where data exists;
- changing week refreshes consistent data;
- no hard-coded fake production data;
- no duplicated backend calculations.

## Suggested commit

```text
feat(overview): build portfolio overview dashboard
```

## Codex Prompt

```text
Implement Week 4 Phase 4: Overview Page.

Use the existing/frozen API contracts. Build the portfolio + SKU monitoring overview.

Include:
- week selector;
- portfolio metrics supported by the backend;
- sentiment view;
- positive/negative aspect overview if supported;
- SKU cards for dashboard-enabled locked SKUs;
- navigation into SKU detail;
- loading, empty, and error states.

The selected week must consistently drive the page's server-state queries.

Do not fabricate unsupported metrics.
Do not calculate deterministic business metrics independently in frontend code.

Keep visual design restrained and portfolio-ready rather than decorative.

Add appropriate frontend tests if configured, then run lint, typecheck, build, and relevant backend tests.
Review the diff, propose a semantic commit, and stop before Phase 5.
```

---

# Phase 5 — SKU Detail Page

## Objective

Implement the Level 2 SKU analysis experience.

## Required sections

```text
SKU Header

Core Metrics
├── Review Count
└── Sentiment

Aspect Distribution

Weekly / Historical Trend

Positive Evidence

Negative Evidence

Ask About This SKU →
```

## Evidence behavior

Evidence presentation should reuse a shared evidence component/model.

Evidence must remain traceable to backend provenance.

## Ask CTA

The CTA may prefill a visible user message or query such as:

```text
What are the main recent complaints about EcoFlow DELTA 2?
```

Do not create hidden active SKU state in the Agent.

## Exit Gate

- all locked SKUs are supported;
- evidence opens/displays correctly;
- empty evidence state works;
- ask CTA does not violate the recent-message-only conversation architecture.

## Suggested commit

```text
feat(sku): add level 2 sku detail experience
```

## Codex Prompt

```text
Implement Week 4 Phase 5: SKU Detail.

Build /skus/[sku_code] using the frozen backend contracts.

Include:
- SKU identity/header;
- review volume;
- sentiment distribution;
- aspect distribution;
- weekly/historical trend;
- positive evidence;
- negative evidence;
- Ask About This SKU CTA.

Reuse a shared evidence presentation component/model so this can later be reused in Compare, Reports, and citation UI.

Keep evidence traceable to the existing provenance contract.

The Ask CTA may create a visible prefilled question, but do not add hidden active-SKU conversation state.

Handle valid, invalid, empty-data, loading, and API-error states.
Run frontend checks and relevant backend regressions.
Review the diff, propose a semantic commit, and stop before Phase 6.
```

---

# Phase 6 — Competitor Compare

## Objective

Implement deterministic same-tier comparison plus a grounded AI summary.

## Selection rules

When SKU A is selected, SKU B choices must be filtered to the same `capacity_tier`.

Backend must still independently validate.

## Required sections

```text
SKU A vs SKU B

Sentiment Comparison

Aspect Comparison

Weekly Trends

Representative Evidence

AI Comparison Summary

Ask Follow-up →
```

## AI summary rule

Do not build a second comparison-specific reasoning system.

Prefer reusing the existing `/api/ask` Agent path so AI comparison wording remains grounded in the same controlled SQL/RAG behavior.

## Exit Gate

- compatible pairs work;
- cross-tier selection is unavailable in UI;
- direct backend cross-tier request is rejected;
- evidence is grounded;
- AI summary uses the controlled Agent rather than duplicated LLM logic.

## Suggested commit

```text
feat(compare): add controlled same-tier competitor comparison
```

## Codex Prompt

```text
Implement Week 4 Phase 6: Competitor Compare.

Build /compare.

Requirements:
- SKU A selector;
- SKU B selector filtered to the same capacity_tier;
- backend remains the authoritative validator;
- sentiment comparison;
- aspect comparison;
- weekly trends;
- representative evidence;
- AI-generated comparison summary;
- Ask Follow-up CTA.

Do not create a separate comparison LLM pipeline.
Reuse the existing controlled Agent for AI comparison synthesis where practical, so deterministic SQL/RAG rules, provenance, no-data behavior, and citations remain consistent.

Do not introduce hidden Agent filter state.

Add tests for valid same-tier pairs and invalid cross-tier requests.
Run frontend and backend checks.
Review the diff, propose a semantic commit, and stop before Phase 7.
```

---

# Phase 7 — Weekly Report Backend

## Objective

Add grounded, streamed weekly report generation.

This is the largest new backend capability in Week 4.

## Report structure

Keep the report bounded.

Recommended sections:

```text
Executive Summary
Key Metrics
Positive Themes
Negative Themes
SKU Highlights
Competitor Observations
Evidence / Citations
```

Adapt only where supported by the actual schema/data.

## Core design

```text
deterministic analytics
        +
retrieved evidence
        +
existing taxonomy
        ↓
LLM synthesis
        ↓
structured validation
        ↓
transactional persistence
```

The LLM must not invent deterministic metrics.

## Streaming flow

Target:

```text
report_started
stage_started
stage_completed
report_delta
report_completed
error
```

Possible stages:

```text
collecting_analytics
retrieving_evidence
synthesizing
validating
persisting
```

Do not expose hidden reasoning.

## Regeneration

Existing report remains intact while generating a replacement.

Only after the new report is valid should persistence atomically replace/update the old report.

On:

- LLM failure;
- retrieval failure;
- validation failure;
- persistence failure;

keep the previous report.

Cancellation semantics must be deliberately handled and tested.

## Avoid

Do not add:

- Celery;
- generic job table;
- report version history;
- multi-agent report writing;
- scheduled report-generation UI.

## Exit Gate

- generate report for a valid week;
- receive structured SSE lifecycle;
- validate report before persistence;
- retrieve generated report afterward;
- regenerate and atomically replace;
- failed regeneration preserves old report;
- no-data/report-not-possible behavior is explicit;
- structured errors do not leak provider details.

## Suggested commit

Potentially split:

```text
feat(report): add grounded report generation service
feat(report): stream and persist generated weekly reports
```

## Codex Prompt

```text
Implement Week 4 Phase 7: Weekly Report Backend.

This phase adds streamed report generation. Inspect the existing weekly_reports schema, repositories, analytics functions, RAG/evidence retrieval, LLM adapter, SSE infrastructure, cancellation handling, and structured errors before coding.

Implement a bounded evidence-grounded report generation flow:
deterministic analytics + retrieved evidence + existing taxonomy -> LLM synthesis -> structured validation -> transactional persistence.

Use the Phase 0 report schema.

Add an SSE generation endpoint with a controlled lifecycle such as:
- report_started;
- stage_started;
- stage_completed;
- report_delta;
- report_completed;
- error.

Reuse existing SSE/error infrastructure where appropriate, but do not expose hidden reasoning, provider exceptions, raw tool data, or stack traces.

Regeneration must be safe:
- never delete/overwrite the existing report before replacement generation succeeds;
- validate the new candidate first;
- atomically replace/update only after success;
- failed generation must preserve the previous valid report.

Do not add Celery, Redis, a generic job queue, report versioning, or multi-agent report generation.

Add tests for:
- successful generation;
- retrieval after generation;
- regeneration;
- failed regeneration preserves old report;
- no-data behavior;
- validation failure;
- structured failure;
- cancellation behavior where testable.

Run relevant Week 2/3 regression tests.
Review the diff, document the new public contract, propose semantic commit(s), and stop before Phase 8.
```

---

# Phase 8 — Weekly Report Frontend

## Objective

Build a report viewer and streamed Generate/Regenerate experience.

## Required UX

```text
Week Selector

Existing Report
or
No report generated

[Generate Report]
or
[Regenerate Report]

Streaming Progress

Final Report
├── Executive Summary
├── Metrics
├── Themes
├── SKU Highlights
├── Competitor Observations
└── Evidence/Citations
```

## Requirements

- consume report SSE;
- user-friendly stage messages;
- keep old report visible until successful replacement when practical;
- clear generation error state;
- explicit regenerate action;
- never trigger generation on page refresh;
- reuse evidence/citation UI.

## Exit Gate

- view existing report;
- generate missing report;
- regenerate existing report;
- progress updates render;
- failure preserves old report display;
- refresh does not regenerate automatically.

## Suggested commit

```text
feat(report-ui): add streamed report viewer and generator
```

## Codex Prompt

```text
Implement Week 4 Phase 8: Weekly Report Frontend.

Build /reports using the Phase 7 backend contract.

Implement:
- week selection;
- existing report retrieval;
- no-report state;
- explicit Generate action;
- explicit Regenerate action;
- SSE progress presentation using friendly stage labels;
- final report rendering;
- evidence/citation presentation using shared evidence UI;
- clear error/retry states.

Do not auto-generate on page load or refresh.

During regeneration, preserve the previous report in the UI until the backend confirms successful replacement when practical.

Do not display raw SSE payloads, raw tool JSON, hidden reasoning, or provider errors.

Run lint, typecheck, frontend tests/build, and relevant report backend tests.
Review the diff, propose a semantic commit, and stop before Phase 9.
```

---

# Phase 9 — Ask Your Data Frontend

## Objective

Turn the already implemented Week 3 `/api/ask` backend into a complete chat product experience.

## Required behavior

- authenticated Ask page;
- visible user messages;
- streamed Markdown answer;
- friendly tool progress;
- used citations only;
- citation popovers;
- follow-up conversation;
- no-data display;
- structured errors;
- cancellation handling;
- stable completion behavior.

## Tool lifecycle presentation

Translate backend tool events into user-facing messages such as:

```text
Searching relevant reviews...
Calculating sentiment trends...
Comparing products...
```

Do not display internal arguments unless explicitly part of a developer/debug mode approved later.

## Citation popover

At minimum:

- evidence preview;
- platform;
- SKU;
- week.

Use stable provenance fields from backend.

## Exit Gate

Browser E2E should support:

- quantitative question;
- qualitative RAG question;
- SQL + RAG hybrid;
- follow-up;
- citation;
- no-data abstention;
- invalid comparison;
- auth failure.

## Suggested commit

```text
feat(chat): add streamed ask-your-data interface
```

## Codex Prompt

```text
Implement Week 4 Phase 9: Ask Your Data Frontend.

Use the existing Week 3 /api/ask SSE contract. Do not redesign the backend Agent unless integration exposes a real contract defect.

Build /ask with:
- authenticated access;
- user/assistant message UI;
- streamed Markdown rendering;
- friendly tool lifecycle status;
- used citations only;
- citation popovers containing review preview, platform, SKU, and week;
- recent-message follow-up support;
- no-data/abstention UX;
- structured error handling;
- cancellation behavior;
- stable stream completion.

Do not expose raw tool JSON, hidden reasoning, provider exception strings, or internal stack traces.

Reuse the shared evidence presentation model where possible.

Test quantitative, RAG, hybrid SQL+RAG, follow-up, citation, no-data, invalid-comparison, and auth-error paths from the browser layer where practical.

Run frontend lint/typecheck/build and relevant Week 3 Agent regressions.
Review the diff, propose a semantic commit, and stop before Phase 10.
```

---

# Phase 10 — UX & Reliability Pass

## Objective

Make the product coherent and remove integration rough edges.

This is not a feature-expansion phase.

## Review areas

Across all pages:

- loading skeletons;
- empty states;
- error states;
- invalid route parameters;
- stale queries;
- disabled controls;
- responsive laptop layout;
- navigation consistency;
- date/week formatting;
- accessible labels;
- long text wrapping;
- citation popover overflow;
- SSE disconnects;
- request cancellation;
- 401 behavior;
- no accidental duplicate requests.

## Design principle

Prefer restrained consistency over elaborate visual work.

## Exit Gate

No major page should:

- silently fail;
- display raw backend internals;
- dead-end the user;
- show impossible comparison choices;
- fabricate absent data;
- require a manual browser refresh to recover from common errors.

## Suggested commit

```text
fix(frontend): harden product ux and failure states
```

## Codex Prompt

```text
Implement Week 4 Phase 10: UX & Reliability Pass.

Do not add new product features.

Audit the full frontend/backend integration for:
- loading/empty/error states;
- invalid params;
- stale/refetch behavior;
- disabled controls;
- responsive laptop layout;
- navigation consistency;
- auth failures;
- SSE disconnect/cancellation;
- citation popovers;
- duplicate requests;
- long-content rendering;
- unsupported/no-data cases;
- same-tier comparison UX.

Fix integration defects and inconsistent UX while preserving Week 1–3 contracts.

Do not introduce elaborate animations or new infrastructure.

Run the full available frontend test/lint/typecheck/build set and relevant backend regressions.
Review the diff, summarize reliability improvements, propose a semantic commit, and stop before Phase 11.
```

---

# Phase 11 — Build the 50-Query Golden Dataset

## Objective

Create a curated semantic evaluation dataset.

Do not treat the existing 19 deterministic queries as replaced.

They remain the regression suite.

## Distribution target

```text
7  quantitative
6  trend
7  comparison
10 evidence / qualitative RAG
6  SQL + RAG hybrid
5  conversational follow-up
5  no-data / abstention / invalid requests
4  report-related
------------------------------------------
50 total
```

Minor category redistribution is allowed only with explicit justification.

## Each case should define

Where applicable:

- unique ID;
- category;
- user question;
- setup/context;
- expected allowed tools;
- expected required tool(s);
- expected forbidden tool behavior;
- expected deterministic values/ranges;
- expected SKU/week;
- expected capacity-tier behavior;
- evidence/relevance expectation;
- expected abstention behavior;
- expected answer characteristics;
- citation expectations;
- human notes.

Avoid storing brittle exact prose answers unless necessary.

## Critical rules

Gold cases must be authored deliberately.

Do not simply ask an LLM to generate 50 questions and accept them unchanged.

Review each case against actual available data.

## Exit Gate

- exactly 50 reviewed semantic cases;
- category coverage is documented;
- expected behavior is testable;
- report cases are included;
- no duplicate or meaningless cases;
- fixtures/data assumptions are explicit.

## Suggested commit

```text
test(eval): add 50-query semantic golden dataset
```

## Codex Prompt

```text
Implement Week 4 Phase 11: 50-Query Golden Dataset.

Inspect the existing Week 3 deterministic 19-query regression suite and current eval tooling first.

Do not replace the 19-query suite.

Create a separate curated semantic Golden dataset with exactly 50 reviewed cases, targeting approximately:
- 7 quantitative;
- 6 trend;
- 7 comparison;
- 10 evidence/qualitative RAG;
- 6 SQL+RAG hybrid;
- 5 conversational follow-up;
- 5 no-data/abstention/invalid;
- 4 report-related.

Each case should capture structured expectations where applicable:
- id/category;
- question;
- conversation/setup context;
- expected required/allowed tools;
- forbidden behavior;
- deterministic expected values or constraints;
- SKU/week/tier expectations;
- evidence expectations;
- abstention expectations;
- citation expectations;
- human notes.

Avoid brittle exact-answer strings when a semantic expectation is more appropriate.

Do not blindly generate and accept synthetic gold data. Reconcile cases with the actual repository fixtures/test data and current system capabilities.

Validate the dataset schema and coverage.
Review the diff, summarize coverage, propose a semantic commit, and stop before Phase 12.
```

---

# Phase 12 — Evaluation Framework

## Objective

Turn evaluation into a repeatable release mechanism.

## Evaluation dimensions

At minimum:

```text
Routing Correctness
Retrieval Relevance
Answer Correctness
Citation Groundedness
Abstention Correctness
Follow-up Context Correctness
```

Plus deterministic critical assertions.

## Deterministic checks

Use deterministic code for:

- exact numeric correctness where gold values exist;
- required/forbidden tool selection when deterministic;
- cross-tier violations;
- citation ID/provenance consistency;
- malformed output;
- missing required citations;
- forbidden answer when abstention is required.

## LLM Judge

Use LLM Judge for semantic dimensions such as:

- answer correctness;
- relevance;
- groundedness;
- quality of synthesis.

Judge output must be structured.

Store enough detail to diagnose failures.

## Reporting

A single evaluation run should produce structured output such as:

- per-case result;
- per-dimension score;
- aggregate metrics;
- gate pass/fail;
- failure categories;
- low-score cases.

Prefer machine-readable JSON plus a concise human-readable summary.

## Exit Gate

One command/workflow can run the semantic suite and produce a gate report.

## Suggested commit

```text
feat(eval): add gated semantic evaluation runner
```

## Codex Prompt

```text
Implement Week 4 Phase 12: Evaluation Framework.

Inspect shared/eval/rag_eval.py, the Week 3 deterministic suite, the Phase 11 Golden schema, and current LLM adapters.

Build a repeatable semantic evaluation runner.

Evaluate at minimum:
- routing correctness;
- retrieval relevance;
- answer correctness;
- citation groundedness;
- abstention correctness;
- follow-up context correctness.

Use deterministic assertions whenever possible for:
- numeric correctness;
- required/forbidden tool behavior;
- cross-tier violations;
- citation/provenance consistency;
- malformed output;
- missing required citations;
- required abstention.

Use structured LLM-as-a-Judge only for genuinely semantic dimensions.

Produce:
- per-case structured results;
- per-dimension scores;
- aggregate metrics;
- gate pass/fail;
- categorized failures;
- a machine-readable output artifact;
- a concise human-readable summary.

Do not hide failed cases behind a single average score.

Add tests for the eval framework itself.
Review the diff, propose a semantic commit, and stop before Phase 13.
```

---

# Phase 13 — Evaluation, Failure Analysis & Tuning

## Objective

Run the system against the evaluation suite and improve it based on failure categories.

## Release gates

Use the locked target gates:

| Metric | Gate |
|---|---:|
| Tool / routing correctness | >= 90% |
| Answer correctness | >= 85% |
| Retrieval relevance | >= 85% |
| Citation groundedness | >= 95% |
| Abstention correctness | >= 90% |
| Follow-up context correctness | >= 90% |
| Deterministic numeric correctness | 100% |
| Cross-tier business-rule violations | 0 |
| Citation provenance violations | 0 |
| Critical unsupported claims | 0 |

## Failure taxonomy

Do not blindly tune prompts.

Classify failures first:

```text
Routing failure
→ Router / tool schema / system prompt

Retrieval failure
→ query construction / filters / top_k / embedding retrieval

Data/analytics failure
→ deterministic service / repository / aggregation

Grounding failure
→ synthesis prompt / evidence contract / citation handling

Conversation failure
→ recent-N context / message reconstruction

Abstention failure
→ router policy / synthesis policy

Report failure
→ analytics/evidence/report validation
```

## Human review

Review:

1. every failed case;
2. every borderline case;
3. a sample of high-scoring cases.

This checks both the product and the Judge.

## Constraints

Do not lower gates merely to obtain a pass unless the original metric was genuinely invalid.

Any gate change must include documented reasoning.

## Exit Gate

- all zero-tolerance gates pass;
- threshold metrics meet target;
- regressions remain green;
- major remaining limitations are documented.

## Suggested commits

Prefer fixes by category, e.g.:

```text
fix(agent): improve comparison routing constraints
fix(rag): tighten evidence retrieval filters
fix(citations): enforce final-answer evidence grounding
fix(report): reject unsupported report claims
```

## Codex Prompt

```text
Implement Week 4 Phase 13: Evaluation, Failure Analysis & Tuning.

Run:
1. the existing Week 3 deterministic regression suite;
2. the new 50-query semantic evaluation suite.

Use the documented release gates.

Before changing code, classify every meaningful failure into:
- routing;
- retrieval;
- analytics/data;
- grounding/citation;
- conversation;
- abstention;
- report;
- infrastructure/test defect.

Then fix root causes with the smallest appropriate change.

Do not default to system-prompt edits for every failure.
Do not move deterministic logic into the LLM.
Do not lower release thresholds simply to pass.

After each tuning group, rerun the relevant focused cases, then rerun the full semantic and deterministic suites.

Manually inspect all failed/borderline cases and a sample of passing cases to detect Judge errors.

Document:
- baseline metrics;
- failures;
- changes;
- final metrics;
- remaining limitations.

Propose semantic commits grouped by root cause and stop before Phase 14.
```

---

# Phase 14 — Release Verification

## Objective

Prove the full MVP works from a clean environment and from the browser.

## 14.1 Fresh infrastructure validation

Validate a clean setup:

```text
fresh PostgreSQL
    ↓
Alembic upgrade
    ↓
seed
    ↓
required test/demo data preparation
    ↓
Milvus
    ↓
backend
    ↓
frontend
```

Do not claim production deployment.

## 14.2 Browser E2E release regression

At minimum verify:

```text
Login
Overview
SKU Detail
Same-tier Compare
Generate Report
Regenerate Report
Quantitative Ask
Qualitative RAG Ask
Hybrid SQL + RAG Ask
Follow-up
Citation popover
No-data abstention
Invalid comparison
Logout / expired auth
```

## 14.3 Existing architecture regressions

Continue verifying important preserved contracts:

- processing statuses;
- embedding dimensions;
- Milvus/PostgreSQL UUID alignment;
- shared quality filtering;
- dashboard APIs;
- independent APScheduler worker;
- Week 3 deterministic Agent acceptance suite.

## Exit Gate

A clean developer environment can reproduce the product according to documented prerequisites.

All release-critical tests pass.

## Suggested commit

```text
test(release): add week 4 end-to-end verification
```

## Codex Prompt

```text
Implement Week 4 Phase 14: Release Verification.

Do not add new product features.

Validate the MVP from a clean environment.

At minimum:
- test Alembic migrations against a fresh PostgreSQL instance;
- initialize required seed/demo data using the repository's supported process;
- verify Milvus requirements and embedding contract;
- start backend and frontend;
- run the full browser-level product flow.

Browser release regression must cover:
- login;
- overview;
- SKU detail;
- valid same-tier comparison;
- report generation;
- report regeneration;
- quantitative Ask;
- qualitative RAG Ask;
- SQL+RAG Ask;
- conversation follow-up;
- citation popover;
- no-data abstention;
- invalid comparison;
- logout or expired-auth behavior.

Also run existing Week 1–3 critical regressions, including the deterministic Week 3 suite.

If a clean setup step is unclear or manual, document and fix the reproducibility problem rather than hiding it.

Summarize exact commands/results, propose any test/release commit, and stop before Phase 15.
```

---

# Phase 15 — Documentation & Demo Polish

## Objective

Turn the repository into a portfolio-ready, understandable engineering project.

## README must explain

At minimum:

1. what problem the project solves;
2. target product/user;
3. system architecture;
4. main stack;
5. data flow;
6. Agent design;
7. deterministic tool boundaries;
8. provenance/citation design;
9. frontend product pages;
10. report generation;
11. evaluation system;
12. setup prerequisites;
13. exact How to Run;
14. migrations;
15. worker startup;
16. backend startup;
17. frontend startup;
18. environment variables;
19. test commands;
20. evaluation commands;
21. known limitations.

## Architecture docs

Update architecture documentation to reflect actual Week 4 implementation, not the original plan.

Do not claim features that were not validated.

## TODO

Mark completed Week 4 phases.

Move intentionally deferred items to a later roadmap section.

## Demo flow

Document a short interview/demo script:

```text
1. Login
2. Overview
3. Open DELTA 2
4. Inspect evidence/trend
5. Compare with a same-tier competitor
6. Generate or view report
7. Ask a hybrid quantitative + qualitative question
8. Open a citation
9. Ask a follow-up
10. Briefly explain evaluation gates
```

## Exit Gate

A new developer or interviewer can understand:

- what the system does;
- how the architecture works;
- how to run it;
- how it is evaluated;
- what its limitations are.

## Suggested commit

```text
docs: finalize week 4 productization and release guide
```

## Codex Prompt

```text
Implement Week 4 Phase 15: Documentation & Demo Polish.

Do not add new product features.

Inspect the final implemented repository and update documentation so it reflects reality.

Update README with:
- product problem and target;
- architecture;
- stack;
- data pipeline;
- controlled Agent design;
- deterministic tool boundaries;
- provenance/citation model;
- frontend routes/features;
- streamed report generation;
- evaluation architecture and release gates;
- prerequisites;
- environment variables;
- exact How to Run steps;
- Alembic migration steps;
- worker/backend/frontend startup;
- test commands;
- semantic evaluation commands;
- known limitations.

Synchronize docs/arch.md and docs/todo.md with actual implementation.

Add a concise interview/demo flow covering login -> overview -> SKU -> compare -> report -> Ask -> citation -> follow-up -> evaluation.

Do not claim unverified production readiness or features that were not implemented.

Run a final documentation consistency review and any link/command checks available.
Review the diff, propose the final semantic documentation commit, and stop.
```

---

# 4. Final Definition of Done

Week 4 is complete when all of the following are true.

## Product

- [ ] Login flow works.
- [ ] Overview is functional.
- [ ] SKU Detail is functional for all locked SKUs.
- [ ] Compare only supports same-tier products.
- [ ] Weekly Report viewer works.
- [ ] Weekly Report generation works through SSE.
- [ ] Regeneration safely replaces only after success.
- [ ] Ask Your Data works from the browser.
- [ ] Friendly tool progress is visible.
- [ ] Markdown answers render correctly.
- [ ] Used citations are interactive.
- [ ] Citation popovers expose evidence metadata.
- [ ] Follow-up conversations work.
- [ ] No-data cases abstain cleanly.

## Engineering

- [ ] Frontend uses TanStack Query for server state.
- [ ] Auth is lightweight and reuses existing JWT backend.
- [ ] Backend remains authoritative for deterministic business rules.
- [ ] Cross-tier validation exists server-side.
- [ ] Evidence provenance remains intact.
- [ ] Existing Week 1–3 contracts remain preserved.
- [ ] No unnecessary Redux/Redis/Celery/GraphQL infrastructure was added.

## Evaluation

- [ ] Existing 19-query deterministic regression suite remains.
- [ ] Separate 50-query semantic Golden dataset exists.
- [ ] Evaluation runner reports per-case/per-dimension results.
- [ ] Deterministic assertions and LLM Judge are separated appropriately.
- [ ] Failed/borderline cases receive human review.
- [ ] Release metric thresholds pass.
- [ ] Zero-tolerance violations are zero.

## Reproducibility

- [ ] Fresh PostgreSQL migration works.
- [ ] Milvus contract is validated.
- [ ] Required demo/test data setup is documented.
- [ ] Backend can start from documented commands.
- [ ] Worker can start from documented commands.
- [ ] Frontend can start from documented commands.
- [ ] Browser E2E release regression passes.

## Documentation

- [ ] README How to Run is accurate.
- [ ] Architecture docs reflect Week 4.
- [ ] TODO reflects completed work.
- [ ] Known limitations are explicit.
- [ ] Demo flow is documented.

---

# 5. Final Release Gate

The release should not be considered complete merely because the UI looks correct.

Required quantitative/semantic gates:

```text
Tool / routing correctness        >= 90%
Answer correctness                >= 85%
Retrieval relevance               >= 85%
Citation groundedness             >= 95%
Abstention correctness            >= 90%
Follow-up context correctness     >= 90%

Deterministic numeric correctness = 100%
Cross-tier violations             = 0
Citation provenance violations    = 0
Critical unsupported claims       = 0
```

If a gate fails:

1. identify failing cases;
2. classify root cause;
3. implement a targeted fix;
4. rerun focused tests;
5. rerun the full deterministic suite;
6. rerun the full semantic evaluation suite;
7. document the result.

---

# 6. Recommended Operator Workflow

For every phase, the operator should:

```text
1. Send only that phase's Codex prompt.
2. Let Codex inspect the current repository.
3. Review Codex's proposed/implemented changes.
4. Verify tests.
5. Review git diff.
6. Create/approve semantic commit(s).
7. Ensure git status is clean.
8. Then send the next phase prompt.
```

Do not tell Codex:

```text
"Implement the whole Week 4 plan."
```

Prefer:

```text
"Implement Week 4 Phase 4 only."
```

This preserves reviewability and prevents scope drift.

---

# 7. Recommended Commit Flow

A possible final history may resemble:

```text
docs(week4): freeze product and API contracts
feat(frontend): establish week 4 application foundation
feat(auth): add frontend jwt session flow
feat(api): add product read models for week 4 frontend
feat(overview): build portfolio overview dashboard
feat(sku): add level 2 sku detail experience
feat(compare): add controlled same-tier competitor comparison
feat(report): add grounded report generation service
feat(report-ui): add streamed report viewer and generator
feat(chat): add streamed ask-your-data interface
fix(frontend): harden product ux and failure states
test(eval): add 50-query semantic golden dataset
feat(eval): add gated semantic evaluation runner
fix(agent): resolve semantic evaluation failures
test(release): add week 4 end-to-end verification
docs: finalize week 4 productization and release guide
```

The exact commit split should follow the actual diff.

---

# 8. What Week 4 Should Demonstrate in an Interview

The final product story should be:

```text
The system ingests and enriches VOC data,
stores structured analytics in PostgreSQL,
stores traceable semantic evidence in Milvus,
uses a controlled handwritten Agent to choose deterministic analytics
and grounded evidence retrieval,
streams transparent but safe execution status,
supports browser-based analytics and Q&A,
generates evidence-grounded weekly reports,
and is evaluated with deterministic regression tests plus
a 50-query semantic benchmark with explicit release gates.
```

The strongest project signal is not that the application contains many technologies.

The strongest signal is that:

- business rules are explicit;
- LLM boundaries are controlled;
- provenance is traceable;
- product UX consumes real system contracts;
- evaluation is repeatable;
- failure behavior is designed;
- the project can be reproduced and demonstrated end to end.
