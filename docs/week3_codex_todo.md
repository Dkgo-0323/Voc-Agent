# Week 3 Codex Development TODO — Controlled VOC Analytical Agent

> **Audience:** Codex / coding agent. This document is an execution specification, not a human-oriented tutorial.
>
> **Primary goal:** Complete Week 3 of the VOC Agent MVP by adding a controlled analytical Agent layer on top of the already-validated Week 2 PostgreSQL + Milvus pipeline.
>
> **Execution rule:** Work phase-by-phase in the order defined below. Do not skip acceptance checks. Do not expand scope without an explicit requirement from this document or the repository's existing architecture.

## Verified implementation status (2026-08-31)

- Phases 0 through 11 are implemented and verified.
- Checkpoints A through F are reached.
- Phase 8 adds configured single-password JWT authentication for `/api/ask`; dashboard routes intentionally remain public.
- Phase 9 adds structured LLM failure categories through compact metadata and SSE; existing deterministic tool failures, constraints, abstention, warnings, and call guards are covered by reliability scenarios.
- Week 3 is signed off; Week 4 frontend, larger evaluation, and polish work remain planned.
- Latest verification: 190 full-suite tests passed.

---

## 0. Repository Context and Source of Truth

Before changing code, inspect the current repository and read at minimum:

- `docs/arch.md` or the current architecture document.
- `docs/todo.md` or the current MVP roadmap.
- `backend/app/db/models.py`.
- current PostgreSQL repositories / query helpers.
- current Milvus repository and embedding code.
- current FastAPI routing structure.
- `backend/app/core/settings.py` and existing security placeholders.
- existing tests / acceptance runners.

Do **not** assume filenames or module boundaries if the repository has evolved. Reuse existing conventions where possible.

### Existing Week 2 contracts that MUST remain intact

1. PostgreSQL is the primary relational store; SQLite is abandoned.
2. SQLAlchemy 2.0 async mode is used.
3. Milvus stores aspect-level vectors.
4. `aspect_mentions.id` is the Milvus vector ID and the PostgreSQL/Milvus provenance key.
5. Milvus metadata includes at least:
   - `sku_code`
   - `aspect_label`
   - `sentiment`
   - `week_id`
   - `quality_score`
6. `mention_text` is evidence-grounded and must remain an exact source-review substring.
7. `context_window` is bounded and is not a replacement for the source review.
8. Dashboard-visible data is already filtered by the configured quality threshold and dashboard-enabled SKU rules.
9. The five locked SKUs and their `capacity_tier` values remain the comparison boundary.
10. Existing Week 2 dashboard APIs and processing-state behavior must not regress.

### Locked Week 3 design decisions

These decisions override the older simplified Week 3 routing description if there is a conflict.

- The product is a **VOC analytical interface**, not a general chatbot.
- The primary project identity is **data engineering / AI systems**, not “just RAG”.
- The LLM may understand intent, select tools, choose tool order, choose valid parameters, and synthesize answers.
- Deterministic application code must validate, query, calculate, constrain, and persist.
- The Agent may call **multiple tools for one user question**.
- Maximum tool calls per request: **3**.
- Tool selection is **not** a hard mutually-exclusive priority chain.
- `tool_report` is read-only in Week 3.
- If no weekly report exists, the Agent may fall back to analytics + RAG when appropriate.
- `tool_sql` must **not** expose arbitrary Text-to-SQL.
- `tool_sql` is a fixed analytics interface backed by deterministic repository queries.
- `tool_rag` uses structured arguments. The LLM proposes filters; application code validates and enforces them.
- Same-`capacity_tier` comparison is an application-level constraint, not only a prompt instruction.
- Small samples remain queryable but must produce an explicit warning.
- Recommended initial small-sample warning threshold: `20`, configurable rather than hard-coded deep inside query logic.
- Citation UX is two-layer:
  1. short evidence preview / exact mention,
  2. expandable full review or larger review context.
- Only evidence actually cited by the final answer is returned as answer citations.
- Conversation context for MVP uses the most recent **N messages**, recommended default `8` messages.
- Do not implement a session-summary memory system in Week 3.
- Follow-up context is inferred from recent chat history; do not introduce hidden per-session filters such as `active_sku`, `active_week`, or `active_aspect`.
- Streaming exposes execution events, not hidden model reasoning.
- Tool failure may yield a partial answer if remaining evidence is sufficient.
- If the VOC dataset cannot support a claim, the Agent must abstain rather than fill the gap using model prior knowledge.
- Auth is intentionally small: single configured password + JWT, with a small protected API surface.
- Week 3 ends with a 15–20 query smoke/golden set, not the full Week 4 50-query evaluation system.

---

# 1. Week 3 Definition of Done

Week 3 is complete only when all six layers below pass acceptance.

## 1.1 Data correctness

- [x] Structured analytics return deterministic, reproducible metrics.
- [x] RAG evidence is traceable from Milvus vector ID to `aspect_mentions.id` and then to the source `documents` record.
- [x] Existing quality and dashboard-enabled filters cannot be bypassed accidentally by the LLM.

## 1.2 Tool correctness

- [x] `tool_report` has a stable read-only contract.
- [x] `tool_sql` exposes only approved analytics operations.
- [x] `tool_rag` accepts structured filters and validates them.
- [x] All tools return structured success / empty / warning / error states rather than ambiguous strings only.

## 1.3 Agent correctness

- [x] Pure handwritten function-calling loop; no LangChain/LlamaIndex.
- [x] Supports single-tool and multi-tool requests.
- [x] Enforces `MAX_TOOL_CALLS = 3` or equivalent configured limit.
- [x] Does not invent unsupported VOC facts.
- [x] Handles no-data and partial-tool-failure cases explicitly.

## 1.4 Conversation correctness

- [x] Chat sessions and messages persist in PostgreSQL.
- [x] Recent-N history is loaded for follow-up questions.
- [x] Tool calls and compact execution metadata are persisted.
- [x] Raw retrieval payloads are not dumped into `chat_messages.tool_results`.

## 1.5 API correctness

- [x] `POST /api/ask` is registered.
- [x] Structured streaming events are emitted in a stable protocol.
- [x] Citations are emitted only for evidence used by the final answer.
- [x] Auth protects `/api/ask`; dashboard routes are intentionally public.

## 1.6 Acceptance correctness

- [x] 15–20 Week 3 smoke/golden queries exist.
- [x] They cover quantitative, qualitative, combined, follow-up, no-data, comparison, and failure/fallback behavior.
- [x] Week 2 regression checks still pass.
- [x] `docs/arch.md` and `docs/todo.md` are updated to reflect verified Week 3 behavior through Phase 11.

---

# 2. Non-Goals — Do Not Implement in Week 3

The unchecked items in this section are intentional non-implementations, not pending acceptance work.

Unless an existing dependency forces a minimal compatibility change, do **not** implement:

- [ ] Arbitrary LLM-generated SQL.
- [ ] A general Text-to-SQL endpoint.
- [ ] Weekly report generation pipeline.
- [ ] Long-term memory or chat summarization.
- [ ] Redis for chat history.
- [ ] User registration.
- [ ] User table / multi-user account management.
- [ ] OAuth.
- [ ] RBAC / roles.
- [ ] Refresh-token rotation.
- [ ] Password reset.
- [ ] Open-ended planner or autonomous agent graph.
- [ ] Parallel tool execution unless required by an existing abstraction.
- [ ] More than 3 tool calls per request.
- [ ] Statistical significance testing / confidence intervals / Bayesian ranking.
- [ ] External web search.
- [ ] Next.js chat UI.
- [ ] Full 50-query LLM-as-a-Judge evaluation.
- [ ] General product-performance claims not grounded in the VOC dataset.

If Codex discovers that one of these is already partially implemented, preserve compatibility but do not expand it.

---

# 3. Target Runtime Flow

Implement toward this logical flow:

```text
Authenticated User Request
        ↓
POST /api/ask
        ↓
Resolve/Create Chat Session
        ↓
Load Recent N Messages
        ↓
Handwritten Function-Calling Loop
        ↓
0..3 Tool Calls
   ├── tool_report
   ├── tool_sql / analytics
   └── tool_rag
        ↓
Grounded Final Synthesis
        ↓
Identify Actually Used Evidence
        ↓
Persist User + Assistant Messages + Tool Metadata
        ↓
Stream:
  tool_started
  tool_completed
  answer_delta
  citation
  done
        ↓
Frontend-ready response contract
```

The Agent is an orchestrator over trusted data capabilities. It is not permitted to become a second analytics engine.

---

# 4. Phase 0 — Repository Audit and Implementation Map

## Objective

Build a precise map of the current repository before writing Agent code.

## Codex tasks

- [x] Inspect the actual current tree.
- [x] Locate current models for:
  - `skus`
  - `documents`
  - `aspect_mentions`
  - `weekly_reports`
  - `weekly_topics`
  - `chat_sessions`
  - `chat_messages`
- [x] Confirm exact fields available for citation hydration.
- [x] Confirm exact fields available for time/week filtering.
- [x] Confirm how `quality_score` threshold is configured and reused by dashboard APIs.
- [x] Confirm how dashboard-enabled SKUs are marked or filtered.
- [x] Confirm `capacity_tier` representation and constraints.
- [x] Locate current PostgreSQL repository patterns.
- [x] Locate current Milvus repository / search abstraction.
- [x] Locate current embedding client usage.
- [x] Locate current FastAPI router registration.
- [x] Locate current test framework / acceptance runner conventions.
- [x] Identify placeholder files in `backend/app/agent/`.
- [x] Produce an internal implementation map before making structural changes.

## Constraints

- Do not rename large existing modules for aesthetics.
- Do not redesign Week 1/2 architecture.
- Prefer adding small Agent-specific modules around existing repositories.

## Exit criteria

Before Phase 1, Codex must know:

- exact DB fields used by every planned analytics operation;
- exact Milvus filter syntax already supported;
- exact provenance path from vector to source review;
- exact config location for quality threshold;
- exact router registration pattern.

---

# 5. Phase 1 — Define Agent Contracts and Shared Schemas

## Objective

Define stable typed interfaces before implementing tool internals.

## Required contract categories

Create or adapt typed schemas for the concepts below using the repository's existing Pydantic/version conventions.

### 5.1 Common tool result envelope

Every tool should be able to represent at least:

- `status`
  - success
  - empty / not_found
  - partial where useful
  - error
- tool name
- normalized request arguments
- warnings
- compact execution metadata
- payload appropriate to that tool

Do not force all tool payloads into an untyped generic dictionary if clean typed models fit the existing architecture.

### 5.2 Analytics tool arguments

Support structured parameters such as:

- operation
- `sku_codes`
- `week_range` or equivalent existing week representation
- optional `aspect`
- optional `sentiment`
- optional metric-specific fields

### 5.3 RAG tool arguments

Support structured parameters such as:

- semantic query
- `sku_codes`
- week/date scope
- sentiment
- aspect
- `top_k`

The LLM may propose these values, but application code validates them.

### 5.4 Citation / evidence models

Define separate concepts for:

1. **retrieved evidence** — internal tool evidence;
2. **answer citation** — evidence the final response actually cites;
3. **expanded source detail** — enough metadata to retrieve/render the larger review context later.

A citation should retain the `aspect_mentions.id` provenance ID.

### 5.5 Streaming event models

Prepare stable event types for:

- `tool_started`
- `tool_completed`
- `answer_delta`
- `citation`
- `done`
- `error`

Do not add chain-of-thought or internal reasoning fields.

## Acceptance checks

- [x] All tool schemas validate malformed enums / unknown operations cleanly.
- [x] Citation schema can identify a source mention unambiguously.
- [x] Streaming event schema is serializable and frontend-friendly.
- [x] No database query or LLM call is required to unit-test schema validation.

## Stop condition

Do not proceed to Router development after this phase. Implement deterministic tools first.

---

# 6. Phase 2 — Build Deterministic Analytics Layer (`tool_sql`)

## Objective

Create a controlled analytics capability where the LLM chooses **approved operations and parameters**, not raw SQL.

## Core design rule

The public Agent tool may retain the historical name `tool_sql` for compatibility, but its behavior must be an **analytics API**, not arbitrary SQL execution.

The model must never receive an `execute_sql(sql: str)` style capability.

## Recommended initial analytics operations

Implement the smallest complete set needed by the Week 3 golden queries. Prefer operations equivalent to:

1. `review_count` or dataset/sample count
2. `sentiment_distribution`
3. `aspect_distribution`
4. `trend`
5. `aspect_trend`
6. `compare_skus`

Adapt names to existing repository conventions if needed.

## Required deterministic behavior

### 6.1 Reuse existing data-quality rules

Every analytics operation that uses `aspect_mentions` must enforce the same configured quality threshold used by validated dashboard aggregates unless an existing business rule explicitly differs.

Do not duplicate the threshold as a second magic number.

### 6.2 Dashboard-enabled SKU rule

Reject or exclude SKUs that are not dashboard-enabled according to the existing repository contract.

### 6.3 Capacity-tier comparison rule

`compare_skus` must validate `capacity_tier` in application code.

Do not rely only on the system prompt.

Expected behavior for incompatible tiers:

- return a structured comparison-constraint result;
- include a machine-readable reason such as `capacity_tier_mismatch` or the closest project convention;
- do not fabricate a direct VOC winner.

### 6.4 Small-sample warning

Introduce a configurable threshold with recommended default:

```text
MIN_RELIABLE_SAMPLE = 20
```

Do not block the comparison solely because of low sample size.

Return a warning containing:

- affected SKU(s);
- actual sample size(s);
- threshold used.

The final Agent must surface this warning when it materially affects interpretation.

### 6.5 Neutral comparison output

The analytics layer returns dimensions, counts, proportions, trends, and warnings.

It must not return subjective judgments such as:

- “Product A is better”.
- “Product B wins”.

If a metric explicitly requested by the user has a numerical winner, the tool may return the numerical ordering but must preserve the metric definition.

## Repository design

Keep these layers separate where the current codebase permits:

```text
Agent Tool Contract
      ↓
Analytics Service / Dispatcher
      ↓
Deterministic PostgreSQL Repository Queries
```

Avoid putting large SQL/query logic directly in the Agent router or FastAPI endpoint.

## Phase 2 tests

Create deterministic tests / acceptance checks for at least:

- [x] one SKU count query;
- [x] sentiment distribution;
- [x] aspect distribution;
- [x] weekly trend;
- [x] aspect-specific trend;
- [x] valid same-tier comparison;
- [x] invalid cross-tier comparison;
- [x] low-sample warning;
- [x] unknown SKU;
- [x] invalid week range;
- [x] no matching data.

Where possible, verify numbers against direct repository/database results rather than asking an LLM to judge correctness.

## Phase 2 exit criteria

A caller can invoke the analytics layer directly with structured arguments and receive deterministic structured JSON-like results with no LLM involvement.

---

# 7. Phase 3 — Build RAG Retrieval Tool and Provenance

## Objective

Implement evidence retrieval that combines Milvus semantic search with PostgreSQL source hydration while preserving strict provenance.

## Required RAG input contract

The LLM may propose:

- query text;
- one or more SKU codes;
- week/date range;
- optional sentiment;
- optional aspect;
- `top_k`.

## Application validation responsibilities

The tool or validation layer must enforce:

- valid locked/dashboard-enabled SKU codes;
- valid time/week scope;
- valid sentiment values;
- valid aspect representation according to the existing enrichment taxonomy;
- configured quality threshold;
- safe maximum `top_k`;
- Milvus metadata filters consistent with Week 2 storage.

Recommended policy: define a configurable `MAX_RAG_TOP_K` and clamp or reject requests above it according to one consistent rule.

The LLM must not be allowed to disable quality filtering.

## Retrieval flow

Preserve this provenance path:

```text
Semantic query
    ↓
Embedding
    ↓
Milvus vector search + scalar filters
    ↓
vector id == aspect_mentions.id
    ↓
PostgreSQL aspect mention hydration
    ↓
documents source hydration
    ↓
RetrievedEvidence[]
```

Do not create a second unrelated vector/document ID mapping.

## Evidence requirements

Each retrieved evidence item should retain enough information for later answer synthesis and citation rendering, such as what is already available in the schema:

- `aspect_mentions.id`
- `mention_text`
- bounded context
- aspect
- sentiment
- SKU code
- week/date
- quality score where useful internally
- source document ID
- source platform
- source review metadata needed for later expansion

Do not persist full raw retrieval payloads in chat-message metadata.

## Two-layer citation contract

### Layer 1 — answer citation preview

Use exact evidence, normally the evidence-grounded `mention_text` plus compact source metadata.

### Layer 2 — expandable source

Retain a stable path to retrieve/render:

- larger context or full review;
- platform;
- date;
- SKU;
- relevant aspect/sentiment metadata.

Do not duplicate full source reviews into Milvus solely for citation rendering if PostgreSQL already owns the document record.

## Retrieved vs cited evidence

This distinction is mandatory:

```text
retrieved evidence != final answer citations
```

If 8 items were retrieved and the final answer uses only 3, only those 3 should be returned as citations.

Design the internal result so the Agent can reference evidence IDs explicitly during final synthesis.

## No-data behavior

If no matching evidence exists:

- return a structured empty result;
- do not use general LLM knowledge as a replacement;
- allow the final Agent to suggest expanding filters/date range if useful.

## Phase 3 tests

Test at least:

- [x] EcoFlow Delta 2 noise query;
- [x] negative charging query;
- [x] Jackery complaint query;
- [x] multi-SKU semantic query where valid;
- [x] sentiment-filtered query;
- [x] aspect-filtered query;
- [x] current/specific week filtering based on existing data representation;
- [x] no-result query;
- [x] invalid SKU;
- [x] excessive `top_k`;
- [x] provenance ID matches PostgreSQL `aspect_mentions.id`;
- [x] source document hydration works;
- [x] quality threshold is enforced.

## Phase 3 exit criteria

A caller can invoke RAG directly without the Agent and get traceable evidence objects whose provenance can be followed to source reviews.

---

# 8. Phase 4 — Implement Read-Only `tool_report`

## Objective

Preserve the report tool contract without expanding Week 3 into weekly report generation.

## Required behavior

`tool_report` should:

- query existing `weekly_reports` using existing schema semantics;
- return the stored report content and identifying metadata when present;
- return a structured `not_found` / empty result when absent;
- never generate a report during the request;
- never silently replace missing reports with fabricated summaries.

## Fallback rule

Fallback is handled by the Agent, not by embedding SQL/RAG execution invisibly inside `tool_report`.

Conceptual flow:

```text
tool_report
  ↓
report exists → return report
  ↓
report missing → structured not_found
  ↓
Agent may choose tool_sql + tool_rag
```

## Phase 4 tests

- [x] existing report path if test/seed data supports it;
- [x] missing report path;
- [x] invalid week/report identifier;
- [x] no report generation side effect.

---

# 9. Phase 5 — Build the Pure Handwritten Function-Calling Router

## Objective

Implement a small, transparent multi-turn function-calling loop without LangChain or LlamaIndex.

## Core behavior

The router receives:

- system policy;
- recent conversation messages;
- current user request;
- tool definitions.

Then it repeatedly performs:

```text
LLM response
   ↓
tool call present?
   ├── yes → validate args → execute tool → append tool result → continue
   └── no  → final answer
```

## Hard guardrail

Configure:

```text
MAX_TOOL_CALLS = 3
```

The application, not merely the prompt, enforces this limit.

If the model attempts a fourth tool call:

- stop additional tool execution;
- either synthesize from already available data or return a controlled error/fallback according to available evidence;
- record the limit event in execution metadata.

## Tool-selection guidance

Do **not** encode the old behavior as “choose exactly one tool according to priority”.

Use these semantics:

### `tool_report`
Use when an already-generated weekly macro report can directly answer the question.

### `tool_sql`
Use for deterministic quantitative questions such as:

- counts;
- proportions;
- distributions;
- trends;
- rankings defined by a specific metric;
- same-tier comparisons.

### `tool_rag`
Use for qualitative evidence such as:

- exact words;
- user quotes;
- specific complaint examples;
- semantic themes/examples.

### Multi-tool examples

`What are the main complaints about Delta 2 this week?`

Expected capability pattern:

```text
analytics → RAG → synthesis
```

`Why did Delta 2 negativity increase?`

Expected capability pattern:

```text
analytics confirms trend → RAG retrieves explanatory evidence → synthesis
```

`Show me actual complaints about Delta 2 fan noise.`

Expected capability pattern:

```text
RAG → synthesis
```

`Summarize this week.`

Expected capability pattern:

```text
report if available
otherwise analytics + RAG when needed
```

## System prompt policies

The Agent system prompt must state the following behavior clearly and compactly.

### Product boundary

- Answer from the VOC dataset and available report data.
- Do not use model prior knowledge to fill missing VOC evidence.

### Quantitative grounding

- Quantitative claims must come from `tool_sql`/analytics results or an existing stored report that explicitly contains them.
- Do not calculate database-wide metrics from a few RAG examples.

### Qualitative grounding

- Quotes/examples must come from RAG evidence or an existing stored report with traceable content.
- Never invent customer quotes.

### Neutral VOC positioning

When a user asks whether one product is “better” without defining a metric:

- summarize relevant VOC dimensions;
- show comparable metrics and evidence;
- avoid declaring an objective winner;
- allow the user to decide.

### Comparison rules

Respect application-returned:

- capacity-tier constraints;
- sample-size warnings;
- unavailable metrics.

### No-data rule

If evidence is insufficient:

- say that the dataset does not provide sufficient evidence;
- optionally suggest a broader date/filter query;
- do not answer from general product knowledge.

### Tool-error rule

If a tool fails:

- inspect remaining successful tool results;
- produce a partial answer only if it remains materially supported;
- clearly disclose the unavailable component;
- never pretend the failed data source succeeded.

### Citation rule

Final synthesis must reference only evidence IDs actually used in the answer so the application can emit only real citations.

## Do not expose reasoning

Do not stream or persist hidden reasoning such as:

- “I think I should call SQL…”
- private chain-of-thought;
- planner scratchpad.

Only expose execution status and final user-facing content.

## Phase 5 tests

Test the router without HTTP streaming first.

Cover at least:

- [x] SQL-only question;
- [x] RAG-only question;
- [x] SQL → RAG question;
- [x] report hit;
- [x] report miss followed by fallback;
- [x] no-data abstention;
- [x] low-sample warning surfaced;
- [x] cross-tier constraint surfaced;
- [x] one tool error + one successful tool result;
- [x] tool-call limit exceeded;
- [x] malformed tool arguments;
- [x] duplicate/redundant tool call behavior does not produce an infinite loop.

## Phase 5 exit criteria

The Agent can answer representative questions from a direct Python/service call and produce a final structured result before any streaming/API work begins.

---

# 10. Phase 6 — Conversation Persistence and Recent-N Context

## Objective

Add multi-turn behavior using existing PostgreSQL `chat_sessions` and `chat_messages`.

## Context strategy

MVP rule:

```text
recent N messages only
recommended N = 8
```

Use a setting/config value rather than burying the number inside router code.

Do not implement conversation summarization in Week 3.

## Follow-up strategy

The LLM reinterprets the latest question using recent message history.

Do **not** create hidden session state such as:

- `active_skus`
- `active_week`
- `active_aspect`
- `active_sentiment`

Tool arguments should be explicitly regenerated each turn from visible conversation context.

This keeps the session replayable and debuggable.

## Persistence rules

Persist at minimum according to existing schema capabilities:

- user message;
- assistant final answer;
- tool calls;
- tool execution metadata.

### `tool_results` JSONB must remain compact

Store execution/debug metadata such as:

- tool name;
- normalized arguments or safe filter summary;
- status;
- result count;
- execution duration;
- warnings;
- error category if any.

Do **not** store:

- complete retrieved reviews;
- complete tool payloads;
- embeddings;
- large raw database result sets.

## Transaction/error behavior

Choose a clear persistence policy and test it. At minimum ensure:

- a tool failure does not corrupt the chat session;
- assistant output corresponds to the tool metadata stored for that turn;
- a failed request does not leave misleading “successful” assistant content.

## Follow-up acceptance scenario

This conversation must work end-to-end at the service layer:

```text
User: Compare Delta 2 and Jackery Explorer 1000.
Assistant: [VOC comparison]
User: What about noise specifically?
Assistant: [understands same two SKUs; focuses on noise]
User: Show me some actual comments.
Assistant: [retrieves evidence for the active conversational topic from history]
```

The system should infer context from recent messages, not hidden filter state.

## Phase 6 tests

- [x] create session;
- [x] reuse session;
- [x] load only configured recent-N messages;
- [x] follow-up reference resolution;
- [x] tool metadata persistence;
- [x] raw payload not persisted;
- [x] malformed/unknown session behavior;
- [x] tool failure persistence consistency.

---

# 11. Phase 7 — Implement `POST /api/ask` and Streaming Protocol

## Objective

Expose the already-working Agent service through a stable frontend-ready streaming API.

## API responsibilities

The endpoint should orchestrate only transport-level concerns:

- authentication dependency;
- request validation;
- session resolution;
- calling the Agent service;
- mapping Agent/tool lifecycle events to streaming events;
- final error handling.

Do not move analytics, RAG, or routing logic into the endpoint.

## Request contract

Prefer a small request shape based on existing API conventions, logically including:

- optional `session_id`;
- user message.

Do not over-design frontend-only fields during Week 3.

## Streaming event contract

Support at least:

### `tool_started`
Frontend can show a generic status such as “Analyzing VOC metrics” or “Searching customer evidence”.

Include only safe execution metadata; do not include hidden reasoning.

### `tool_completed`
Include tool status and compact completion metadata such as counts/warnings where useful.

### `answer_delta`
Stream final user-facing answer tokens/chunks.

### `citation`
Emit only citations actually referenced by the final answer.

Each citation must contain enough stable identifiers/metadata for Week 4 citation popovers.

### `done`
Signal successful completion and include final identifiers such as session/message IDs if useful to the client contract.

### `error`
Use a structured error event for request-level failures.

## Transport choice

Use the transport that best matches the existing FastAPI/frontend architecture. SSE is acceptable if no better project convention already exists.

Do not introduce WebSockets only for novelty.

## Partial failure behavior

Example:

```text
analytics succeeds
RAG fails
```

If the quantitative result still answers part of the question:

- stream a supported partial answer;
- explicitly state that supporting review evidence is temporarily unavailable;
- do not emit fabricated citations.

If all required data capabilities fail, return a controlled request-level error.

## Disconnect / cancellation

Handle client disconnects and cancelled streaming tasks according to the current async FastAPI stack. Avoid leaving unnecessary long-running tool work when cancellation can be propagated safely.

## Phase 7 tests

Use the repository's API test style or an HTTP client.

Validate at least:

- [x] new session request;
- [x] existing session request;
- [x] SQL-only event sequence;
- [x] RAG-only event sequence;
- [x] SQL → RAG event sequence;
- [x] citation events appear after/with final answer contract as designed;
- [x] no unused retrieved evidence is emitted as citation;
- [x] partial tool failure;
- [x] request-level failure;
- [x] client disconnect/cancellation if practical in current test stack.

Expected conceptual event sequence for a combined query:

```text
tool_started(analytics)
tool_completed(analytics)
tool_started(rag)
tool_completed(rag)
answer_delta(...)
answer_delta(...)
citation(...)
citation(...)
done(...)
```

Exact wire format may follow repository conventions, but event semantics should remain stable.

---

# 12. Phase 8 — Minimal JWT Authentication

## Objective

Prevent the demo API from being unauthenticated without building a user-management subsystem.

## Required Week 3 scope

Implement or complete:

- [x] configured single-password authentication;
- [x] `POST /api/auth/login`;
- [x] JWT signing;
- [x] JWT expiration;
- [x] JWT verification dependency;
- [x] `GET /api/auth/me` or equivalent lightweight token-validation endpoint;
- [x] protect `POST /api/ask`;
- [x] dashboard routes intentionally remain public as the existing read-only dashboard surface.

## Configuration

Secrets/passwords must come from settings/environment configuration.

Do not hard-code production secrets into source files.

## Explicit non-scope

Do not add:

- users table;
- registration;
- OAuth;
- RBAC;
- refresh token flow;
- password-reset flow.

## Phase 8 tests

- [x] correct password returns valid token;
- [x] incorrect password rejected;
- [x] missing token rejected for protected route;
- [x] malformed token rejected;
- [x] expired token rejected;
- [x] valid token can call `/api/ask`;
- [x] `/api/auth/me` confirms valid authentication using the chosen minimal identity representation.

---

# 13. Phase 9 — Reliability, Error Taxonomy, and Guardrails

## Objective

Convert the happy-path implementation into a controlled MVP system.

## Define consistent error categories

Use existing project error conventions if present. Ensure the system can distinguish at least conceptually:

- invalid tool arguments;
- invalid/unknown SKU;
- invalid time/week range;
- comparison constraint;
- empty data;
- low-sample warning;
- PostgreSQL/query failure;
- Milvus failure;
- embedding-provider failure/timeout;
- LLM failure/timeout;
- tool-call-limit reached;
- authentication failure.

Do not expose stack traces or secrets to the frontend.

## Required reliability scenarios

### 13.1 Milvus unavailable

If the request also has useful analytics results:

- allow partial quantitative answer;
- state that evidence retrieval is unavailable;
- no fabricated quotes/citations.

### 13.2 PostgreSQL analytics failure

If the request is qualitative and RAG evidence can still be hydrated safely, a supported qualitative answer may be possible.

Do not invent percentages/trends/rankings.

### 13.3 No data

Return an abstention-style answer, for example semantically:

> No sufficient VOC evidence was found for this aspect in the selected period.

Optionally suggest:

- broader date range;
- fewer filters;
- another SKU.

Do not use general model knowledge as fallback.

### 13.4 Small sample

Answer is allowed, but warning must be visible in final synthesis when comparison interpretation depends on the small sample.

### 13.5 Cross-tier comparison

Do not silently perform a direct comparison that violates the locked capacity-tier rule.

Return/explain the constraint neutrally.

### 13.6 Malformed model tool arguments

Validate before execution.

Allow the function-calling loop to recover within the 3-call budget if the chosen LLM API/tool protocol supports a clean corrective turn.

Never execute malformed/unvalidated values directly against the database/vector store.

### 13.7 Duplicate/repeated tool calls

Prevent accidental infinite repetition.

At minimum, enforce the global tool-call count. Prefer lightweight duplicate-call detection if it can be implemented without introducing a planner framework.

## Phase 9 exit criteria

Representative failure scenarios produce controlled user-facing behavior and useful compact logs/metadata without corrupting sessions.

---

# 14. Phase 10 — Week 3 Smoke/Golden Query Set

## Objective

Create a small deterministic/manual acceptance suite that becomes the seed for Week 4's 50-query evaluation.

## Target size

Create **15–20 queries**, recommended target `19`.

Do not build the full LLM-as-a-Judge workflow yet unless a minimal existing runner can be reused with almost no added scope.

## Recommended composition

| Category | Target count |
|---|---:|
| Count / distribution | 2 |
| Trend | 2 |
| SKU comparison | 3 |
| Specific evidence / quotes | 3 |
| SQL + RAG combined | 3 |
| Multi-turn follow-up | 2 |
| No-data / abstention | 2 |
| Failure / fallback | 2 |
| **Total** | **19** |

## Required representative queries

Adapt wording to actual available dataset weeks, but include semantic equivalents of:

### Quantitative

1. `How many negative mentions did EcoFlow Delta 2 receive in <known week>?`
2. `What are the main complaint aspects for EcoFlow Delta 2 in <known week>?`

### Trend

3. `How has negative sentiment for EcoFlow Delta 2 changed over the available weeks?`
4. `How has fan/noise sentiment changed over the available weeks?`

### Comparison

5. `Compare EcoFlow Delta 2 and Jackery Explorer 1000 using customer feedback.`
6. `Compare their noise-related feedback.`
7. A deliberately incompatible cross-tier comparison to verify the constraint.

### Evidence

8. `Show me actual complaints about Delta 2 fan noise.`
9. `Give me examples of negative charging feedback for Delta 2.`
10. `What exact words do users use for a known supported aspect?`

### Combined SQL + RAG

11. `What are the main complaints about Delta 2 this week?`
12. `Why did Delta 2 negativity increase?` — only if the available data actually contains an increase; otherwise choose a trend direction supported by data.
13. `Which complaint category is most common, and show representative comments?`

### Follow-up

14. Turn 1: `Compare Delta 2 and Jackery Explorer 1000.`
    Turn 2: `What about noise specifically?`

15. Continue the same session:
    `Show me some actual comments.`

### No-data

16. Ask about an aspect known to have no matching evidence in the selected period.
17. Ask with an intentionally over-restrictive valid filter combination that yields zero evidence.

### Failure / fallback

18. Simulate/force RAG unavailability while analytics remains available.
19. Simulate/force report absence or another controlled fallback path.

## Manual acceptance dimensions

For every query record at least:

- expected tool sequence;
- actual tool sequence;
- routing correctness;
- tool argument correctness;
- quantitative correctness where applicable;
- correct comparison constraints;
- sample-size warning correctness;
- citation correctness;
- no unsupported claims;
- latency / execution time if easy to capture;
- pass/fail;
- notes.

## Critical acceptance rule

Do not judge only whether the prose “sounds good”.

A response fails if:

- a quantitative claim is unsupported by analytics/report data;
- a quote is not traceable to retrieved evidence;
- the answer cites evidence it did not use;
- a no-data case is filled with general LLM knowledge;
- a cross-tier comparison violates the business constraint;
- a low-sample comparison omits the warning where material;
- a follow-up loses obvious recent conversation context;
- the Agent exceeds the configured tool-call limit.

---

# 15. Phase 11 — Regression and Week 3 Sign-Off

## Objective

Prove Week 3 did not break Week 2 and synchronize documentation with actual behavior.

## Regression checks

- [x] Week 2 processing-state tests/acceptance still pass in the current preliminary regression run.
- [x] existing embedding dimension contract remains 1024 unless repository configuration explicitly changed for a documented reason.
- [x] PostgreSQL/Milvus ID alignment remains intact.
- [x] Dashboard APIs still work.
- [x] dashboard quality threshold behavior has not diverged from Agent analytics unexpectedly.
- [x] APScheduler worker remains independent of the FastAPI event loop.

## Documentation updates

Update `docs/arch.md` to reflect the implemented design.

### Replace the old routing interpretation

The architecture should no longer imply that the Agent always chooses exactly one tool using a strict priority order.

Document instead:

- report / analytics / RAG as composable capabilities;
- maximum 3 tool calls;
- report read-only Week 3 behavior;
- report-missing fallback;
- fixed analytics operations rather than arbitrary SQL;
- structured RAG filters and application validation;
- two-layer citations;
- recent-N chat context;
- no-data abstention;
- partial-tool-failure behavior;
- structured streaming events;
- minimal JWT auth.

Update `docs/todo.md` Week 3 checkboxes only after acceptance criteria actually pass.

Do not mark Week 4 frontend/evaluation/polish work complete.

## Optional documentation artifact

If useful, add a compact Week 3 acceptance report under `docs/` containing:

- environment used;
- golden-query results;
- known limitations;
- remaining Week 4 work.

Keep it concise and evidence-based.

---

# 16. Recommended 7-Day Execution Order

Use this only as sequencing guidance. Acceptance gates matter more than literal calendar days.

## Day 1 — Contracts + Analytics Foundation

- [x] Phase 0 repository audit.
- [x] Phase 1 schemas/contracts.
- [x] Begin Phase 2 analytics repository queries.
- [x] Finish capacity-tier and sample-warning behavior.
- [x] Run deterministic analytics acceptance.

**Do not start the Agent router if analytics results are not trustworthy.**

## Day 2 — RAG + Provenance + Citations

- [x] Complete Phase 3.
- [x] Verify Milvus → PostgreSQL provenance.
- [x] Verify source-review expansion path.
- [x] Verify quality/filter enforcement.

## Day 3 — Report Tool + Function Calling Router

- [x] Complete Phase 4 read-only report tool.
- [x] Complete Phase 5 handwritten router.
- [x] Test SQL-only, RAG-only, SQL→RAG, report fallback, no-data.

## Day 4 — Conversation Persistence

- [x] Complete Phase 6.
- [x] Test recent-N context.
- [x] Test the three-turn comparison/noise/comments chain.
- [x] Confirm compact tool metadata persistence.

## Day 5 — Streaming API

- [x] Complete Phase 7.
- [x] Stabilize event contract.
- [x] Validate citations and partial-failure streaming.

## Day 6 — Auth + Reliability

- [x] Complete Phase 8.
- [x] Complete Phase 9.
- [x] Exercise invalid inputs, expired JWT, Milvus failure, no-data, cross-tier, tool-call limit.

## Day 7 — Golden Set + Regression + Docs

- [x] Complete Phase 10.
- [x] Complete Phase 11.
- [x] Update architecture and roadmap based on implemented reality through Phase 11.
- [x] Do not add new features after acceptance begins unless needed to fix a failed acceptance criterion.

---

# 17. Suggested Module Boundaries

Adapt to the real repository; do not force this exact tree if current conventions differ.

A clean target separation is conceptually:

```text
backend/app/
├── agent/
│   ├── router.*
│   ├── prompts.*
│   ├── schemas.*
│   ├── citations.*
│   └── tools/
│       ├── report.*
│       ├── analytics.*
│       └── rag.*
├── api/
│   ├── ask.*
│   └── auth.*
├── services/
│   └── chat / agent orchestration modules
├── repositories/
│   └── deterministic analytical queries
└── core/
    └── security.*
```

Keep these responsibilities distinct:

```text
FastAPI endpoint
    ≠
Agent router
    ≠
Agent tool
    ≠
Repository query
    ≠
Database/vector client
```

Avoid allowing `ask` endpoint code to become a monolithic implementation file.

---

# 18. Logging and Observability Requirements

Reuse the existing project logger if available.

For each Agent request, log safe operational metadata sufficient for debugging, such as:

- request/session identifier;
- tool name;
- normalized high-level filters;
- tool status;
- result count;
- latency;
- warning/error category;
- tool-call count.

Do not log:

- JWT secrets;
- configured password;
- raw embeddings;
- unnecessary PII;
- hidden LLM reasoning;
- full source-review payloads unless existing secure debug policy explicitly permits it.

This metadata should align conceptually with what is stored in `chat_messages.tool_results`.

---

# 19. Configuration Requirements

Prefer central settings for values likely to change, including equivalents of:

- recent chat-message limit (recommended default `8`);
- max tool calls (`3`);
- small-sample warning threshold (recommended default `20`);
- max RAG `top_k`;
- JWT expiration;
- JWT signing secret;
- single demo password;
- existing quality threshold;
- existing embedding and Milvus settings.

Do not duplicate existing configuration variables if they already exist.

Validate required secrets/settings at startup using the current settings pattern.

---

# 20. Final Agent Behavioral Contract

Use the following rules as implementation invariants.

## 20.1 LLM responsibilities

The LLM may:

- interpret user intent;
- resolve follow-up references from recent conversation;
- choose approved tools;
- choose valid structured arguments;
- sequence up to 3 tool calls;
- synthesize grounded quantitative + qualitative answers;
- select which retrieved evidence is actually cited.

## 20.2 Application responsibilities

Deterministic code must:

- validate all tool arguments;
- build SQL queries;
- execute database queries;
- enforce quality filters;
- enforce dashboard-enabled SKU filters;
- enforce capacity-tier comparison rules;
- enforce sample-size warning rules;
- enforce max `top_k`;
- enforce max tool calls;
- preserve PostgreSQL/Milvus provenance;
- persist chat history/tool metadata;
- verify JWTs;
- serialize streaming events.

## 20.3 Forbidden LLM behavior

The LLM must not:

- write or execute arbitrary SQL;
- invent VOC metrics;
- invent customer quotes;
- claim a product is objectively “better” when the dataset only supports dimensional VOC comparison;
- hide small-sample limitations;
- bypass capacity tiers;
- answer no-data VOC questions using pretrained product knowledge;
- expose hidden chain-of-thought;
- exceed the application tool-call limit.

---

# 21. Implementation Checkpoints for Codex

After each major phase, stop feature work and run the corresponding checks before proceeding.

## Checkpoint A — Analytics trusted

**Status: reached.** Deterministic analytics, tier constraints, sample warnings, and quality filtering are covered by `tests/test_tool_sql.py`.

Required before RAG/router work is considered integrated:

- deterministic numbers verified;
- same-tier rule verified;
- low-sample warning verified;
- quality threshold verified.

## Checkpoint B — Evidence trusted

**Status: reached.** Retrieval filters, provenance hydration, no-data, and expandable citation sources are covered by `tests/test_tool_rag.py`.

Required before Router integration:

- semantic retrieval works;
- filters work;
- vector ID → mention → document provenance verified;
- no-data works;
- citation source can be expanded.

## Checkpoint C — Agent trusted

**Status: reached.** Single/multi-tool routing, the three-call limit, abstention, and partial failures are covered by `tests/test_agent_router.py`.

Required before HTTP streaming:

- single-tool routing works;
- multi-tool routing works;
- max 3 calls enforced;
- no-data abstention works;
- tool failures do not create unsupported claims.

## Checkpoint D — Conversation trusted

**Status: reached.** Recent-N context, follow-ups, compact metadata, and absence of hidden filter state are covered by `tests/test_conversation_service.py`.

Required before frontend-facing API is considered stable:

- recent-N history loaded;
- follow-ups resolved;
- metadata persisted compactly;
- no hidden filter state introduced.

## Checkpoint E — API trusted

**Status: reached.** Streaming, citations, structured errors, and minimal JWT authentication pass acceptance.

Required before Week 3 acceptance:

- structured streaming contract stable;
- citations correspond only to used evidence;
- errors structured;
- auth works.

## Checkpoint F — Week 3 signed off

**Status: reached.** The 19-query acceptance set, Week 2 regression suite, and final architecture/roadmap synchronization are complete.

Required before marking Week 3 completed:

- 15–20 golden/smoke queries reviewed;
- major failures fixed or explicitly documented;
- Week 2 regression passes;
- docs updated.

---

# 22. Codex Working Protocol

When Codex executes this document, use the following operating procedure.

## Before each phase

1. Re-read the phase objective and constraints.
2. Inspect the relevant current repository files.
3. Identify reuse opportunities before creating new abstractions.
4. State internally what existing contract will be preserved.

## During implementation

1. Make the smallest coherent change that satisfies the current phase.
2. Avoid unrelated refactors.
3. Add/update tests alongside the behavior.
4. Keep LLM-dependent behavior behind deterministic validation boundaries.
5. Do not change Week 2 schemas/contracts casually.

## After each phase

1. Run targeted tests.
2. Run relevant regression tests.
3. Inspect actual outputs, not only exit codes.
4. Fix failures before moving to the next phase.
5. Summarize:
   - files changed;
   - behavior added;
   - tests run;
   - acceptance status;
   - known limitations.

Do not mark TODO items complete based only on code existence.

---

# 23. Recommended Development Commits / Milestones

If using Git commits during execution, prefer small phase-aligned commits similar to:

1. `feat(agent): define week3 tool and streaming contracts`
2. `feat(agent): add deterministic voc analytics tool`
3. `feat(agent): add rag retrieval and citation provenance`
4. `feat(agent): add readonly weekly report tool`
5. `feat(agent): add bounded function-calling router`
6. `feat(chat): persist recent conversation context and tool metadata`
7. `feat(api): add streaming ask endpoint`
8. `feat(auth): add minimal jwt protection`
9. `test(agent): add week3 golden query acceptance set`
10. `docs: finalize week3 architecture and acceptance`

Adapt commit boundaries to the repository's actual working state. Do not create empty/artificial commits merely to match this list.

---

# 24. Week 3 Final Checklist

## Analytics

- [x] Fixed operation interface implemented.
- [x] No arbitrary Text-to-SQL capability.
- [x] Counts/distributions/trends work.
- [x] Same-tier comparison enforced.
- [x] Low-sample warnings work.
- [x] Quality threshold reused.

## RAG

- [x] Structured RAG arguments implemented.
- [x] Filters validated by application.
- [x] Milvus + PostgreSQL provenance works.
- [x] `top_k` bounded.
- [x] No-data returns structured empty state.
- [x] Two-layer citation data available.
- [x] Retrieved evidence is distinguished from cited evidence.

## Report

- [x] Read-only report retrieval implemented.
- [x] Missing report returns explicit not-found state.
- [x] No Week 3 report generation added.

## Router

- [x] Pure handwritten function-calling loop.
- [x] No LangChain/LlamaIndex.
- [x] Multiple tool calls supported.
- [x] Hard maximum 3 tool calls.
- [x] Multi-tool SQL + RAG synthesis works.
- [x] Neutral VOC comparison behavior.
- [x] No-data abstention.
- [x] Partial-failure behavior.

## Conversation

- [x] PostgreSQL session persistence.
- [x] Recent-N history, recommended N=8.
- [x] Follow-up questions work.
- [x] No hidden active filter state.
- [x] Compact tool metadata only.

## API / Streaming

- [x] `POST /api/ask` registered.
- [x] `tool_started` event.
- [x] `tool_completed` event.
- [x] `answer_delta` event.
- [x] `citation` event.
- [x] `done` event.
- [x] structured `error` event.
- [x] no hidden reasoning streamed.

## Auth

- [x] single-password login.
- [x] JWT issuance.
- [x] JWT expiry.
- [x] JWT verification.
- [x] `/api/auth/me` or equivalent.
- [x] `/api/ask` protected.
- [x] no user-management scope creep.

## Acceptance

- [x] 15–20 golden/smoke queries.
- [x] routing reviewed.
- [x] quantitative correctness reviewed.
- [x] citations reviewed.
- [x] no-data reviewed.
- [x] failure/fallback reviewed.
- [x] Week 2 regressions pass in the final Week 3 sign-off run.
- [x] `docs/arch.md` synchronized through Phase 11.
- [x] `docs/todo.md` synchronized through Phase 11.

---

# 25. Final Sign-Off Statement

Only mark **Week 3: Agentic RAG & Function Calling** as completed when the implementation satisfies the following statement:

> The VOC Agent can accept authenticated multi-turn questions, use a bounded handwritten function-calling loop to compose deterministic PostgreSQL analytics, traceable Milvus/PostgreSQL evidence retrieval, and optional stored reports, then stream a grounded neutral VOC answer with citations. Quantitative calculations and business constraints remain deterministic; the LLM is limited to intent interpretation, approved tool orchestration, and synthesis. No-data and partial-failure behavior are explicit, conversation history is persisted in PostgreSQL, and a 15–20 query acceptance set has passed without regressing the validated Week 2 pipeline.
