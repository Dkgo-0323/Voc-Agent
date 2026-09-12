# Architecture & Key Decisions (VOC Agent MVP)

## 0. Scope & Upgrades
- **Target**: Outdoor power stations VOC weekly intelligence with a controlled multi-turn analytical Agent. Week 3 is signed off: minimal JWT authentication, structured Agent streaming, the deterministic 19-query smoke/golden acceptance set, and a live Zhipu + embedding provider + Milvus + PostgreSQL RAG verification are complete.
- **Core Stack**: Python 3.11+, `uv`, FastAPI (Async), SQLAlchemy 2.0 (asyncio), PostgreSQL 15, Milvus 2.x.
- **Major Upgrades from v1**:
  - Completely abandoned SQLite to avoid Alembic migration incompatibilities with JSONB/ARRAY types.
  - Abandoned LangChain/LlamaIndex in favor of a **Pure Handwritten Function Calling Loop** for maximum transparency and control.
  - Chat history relies entirely on PostgreSQL with indexing (Abandoned Redis as over-engineering for MVP).
  - Independent Worker Process for APScheduler to prevent CPU-intensive pipelines from blocking the API event loop.

## 1. System Topology
- **Data Ingestion (Pipelines)**: Weekly batch processing. Fetches from PRAW (Reddit) & McAuley dataset (Amazon). Sanitizes via Presidio.
- **Worker Process**: Independent python process (`python -m backend.worker.main`) running APScheduler to execute the ingestion and enrichment pipelines.
- **Backend (FastAPI)**: Exposes PostgreSQL-backed dashboard APIs and `POST /api/ask` as a structured SSE stream.
- **Agent Layer**: A bounded handwritten function-calling router composes deterministic analytics, traceable evidence retrieval, and read-only stored reports. PostgreSQL stores recent conversation history and compact execution metadata.
- **Authentication**: A configured single-password login issues expiring JWTs; bearer verification protects `/api/ask`. The existing read-only dashboard routes remain public.

## 2. Directory Structure

    voc-agent/
    ├── pyproject.toml               # uv package manager configs
    ├── alembic.ini                  # alembic configs
    ├── docs/                        # prompts.md, arch.md, todo.md
    ├── backend/                     # Async architecture
    │   ├── app/
    │   │   ├── main.py
    │   │   ├── core/                # settings, security.py (JWT), database.py (async engine)
    │   │   ├── api/                 # Dashboard routes and SSE /api/ask transport
    │   │   ├── agent/               # Schemas, tools, router, LLM adapter, conversation service
    │   │   ├── db/
    │   │   │   ├── models.py        # 7 core ORM models
    │   │   │   ├── seed.py          # Initial SKU injection
    │   │   │   └── migrations/      # alembic env.py (async mode) & versions
    │   ├── worker/                  # ★ Independent Process
    │   │   ├── main.py              # APScheduler entry point
    │   │   └── jobs.py              # Pipeline execution logic
    ├── pipelines/                   # Batch processing base
    │   ├── config/                  # targets.py (SKU mappings)
    │   ├── ingestion/               # reddit_fetcher.py, amazon_loader.py
    │   ├── sanitize/                # pii_cleaner.py
    │   └── ...
    ├── shared/                      # shared LLM client and Phase 12 semantic evaluation framework
    ├── frontend/                    # Next.js
    └── docker-compose.yml           # PostgreSQL + Milvus

## 3. Week 2 Pipeline & Dashboard

### Processing State Contract
- `documents.processing_status` progresses through `raw` → `enriched` → `embedded`; a per-document extraction or embedding error moves only that document to `failed` with `processing_error` populated.
- The worker fetches only raw documents belonging to dashboard-enabled SKUs. The explicit acceptance runner accepts only caller-supplied raw UUIDs and rejects duplicate or non-raw input.
- Extraction accepts at most three evidence-grounded aspects per review. `mention_text` must be an exact review substring (≤60 characters); quality is calculated before persistence.
- Model-supplied `context_window` is limited to 200 characters. If the model returns an oversized context for an otherwise valid mention, the pipeline rebuilds a bounded context from the exact review evidence rather than discarding the mention.
- `embed_text` is persisted in PostgreSQL before the document advances to `embedded`. Milvus upserts use `aspect_mentions.id` as the vector ID and carry `sku_code`, `aspect_label`, `sentiment`, `week_id`, and `quality_score` metadata.

### Operational Validation
- The Week 2 acceptance runner processed one selected document for each locked SKU in a controlled network environment.
- Final acceptance produced 10 `aspect_mentions` and 10 Milvus vectors for the five documents. UUID, scalar metadata, evidence, quality, and `embed_text` checks passed with no missing or orphan vectors.
- Dashboard aggregates are served by `GET /api/weeks`, `GET /api/overview`, and `GET /api/skus/{sku_code}/trends`; only dashboard-enabled SKUs and mentions meeting the configured quality threshold are included.

## 4. Implemented Agent Design & Tool Boundaries

The Agent uses a pure handwritten function-calling loop with a hard maximum of three attempted tool calls. Tools are composable; there is no mutually exclusive priority chain.

- **`tool_report`** reads existing `weekly_reports` only. A missing report returns `not_found`; the Router may then choose analytics and/or RAG. It never generates a replacement report.
- **`tool_sql`** exposes only six fixed deterministic operations: review count, sentiment distribution, aspect distribution, trend, aspect trend, and SKU comparison. It never accepts arbitrary SQL. Application code enforces dashboard-enabled SKUs, the shared quality threshold, same-`capacity_tier` comparison, and configurable low-sample warnings.
- **`tool_rag`** accepts structured query, SKU, week, sentiment, aspect, and `top_k` arguments. Application code validates locked/dashboard-enabled SKUs, taxonomy, ISO weeks, maximum `top_k`, and quality filtering before Milvus/PostgreSQL retrieval.

The LLM may interpret intent, regenerate explicit tool arguments from visible recent messages, select and sequence approved tools, synthesize supported output, and identify cited evidence IDs. Deterministic code owns validation, calculation, business constraints, provenance, persistence, and streaming serialization.

### Evidence, conversation, and failure behavior

- Provenance remains `Milvus vector id == aspect_mentions.id -> documents.id`; no second ID mapping exists.
- Retrieved evidence and final citations are distinct. Only evidence IDs actually referenced in the final answer are emitted. Citations provide an exact preview plus stable source metadata for expansion.
- Conversation context loads the most recent configurable N messages (default 8). No hidden active SKU/week/aspect/sentiment state or session summarization exists.
- No-data requests abstain instead of using model prior knowledge. A failed tool may produce a disclosed partial answer only when another successful result materially supports it.
- SSE emits real-time `tool_started`/`tool_completed`, then final `answer_delta`, used `citation` events, and `done`; request-level failures end with structured `error`. Successful final events are sent only after the chat transaction commits.
- Reliability errors are normalized into safe structured categories. Tool errors retain compact code/retryability metadata; LLM failures use `llm_timeout` or `llm_request_failed`, and embedding timeouts use `rag_embedding_timeout`. Provider exception text, stack traces, and hidden reasoning are never streamed or persisted.

### Week 3 acceptance status

- The deterministic 19-query smoke/golden set covers quantitative, trend, same-tier and cross-tier comparison, evidence, combined SQL+RAG, recent-message follow-up, no-data, and fallback behavior.
- The final Week 3 regression run preserves the validated Week 2 processing pipeline, embedding dimension contract, PostgreSQL/Milvus UUID alignment, dashboard APIs, shared quality filtering, and independent APScheduler worker process.
- Live end-to-end validation passed against the configured Zhipu LLM and embedding provider with local Milvus and PostgreSQL: an authenticated `POST /api/ask` RAG request returned HTTP 200, `tool_rag:success`, one grounded SSE citation, and `done:success`.
- The live citation's `mention_id` was verified as an `aspect_mentions.id` whose `document_id` matched the cited `documents.id`; its source URL and evidence preview were present. The request executed one tool call, within the maximum of three.

## 5. Storage & Schema Contracts

### Database Choices
- **RDBMS**: PostgreSQL 15. Managed by Alembic (`env.py` configured with `run_async_migrations`).
- **Vector DB**: Milvus 2.x (Docker). Uses Hybrid Search (Vector + Scalar Metadata filtering).
- **Embedding Contract**: Zhipu `embedding-3` via `https://open.bigmodel.cn/api/paas/v4/`; dimension is sourced only from `EMBEDDING_DIMENSIONS` (currently 1024) and must match both API output and the Milvus vector field.

### Cross-System Joining & Mapping
- **Milvus Granularity**: Sentence/Aspect level.
- **Primary Key Alignment**: The UUID in `aspect_mentions.id` (PostgreSQL) is strictly used as the vector `id` in Milvus. No redundant data stored in Milvus.
- **Cross-system Join Key**: `sku_code` (Slug format, e.g., `ecoflow-delta2`).

### Target SKUs (Locked)
1. `ecoflow-delta2` (1024Wh, mid) - Baseline for RAG verification.
2. `jackery-explorer-1000` (1002Wh, mid) - Direct competitor for SQL join/trend testing.
3. `jackery-explorer-240` (240Wh, entry) - High volume data (3653 reviews) for aggregation load testing.
4. `jackery-explorer-300` (293Wh, entry) - Low volume data for fallback testing.
5. `anker-solix-f2000` (2048Wh, large) - High-end semantic parsing test.

### ER & Tables
- `skus` (Contains `capacity_tier` to prevent cross-tier comparisons)
- `documents` (Raw reviews, handles PII `author_hash`, UNIQUE `platform` + `external_id`; includes processing status/error fields for the Week 2 pipeline)
- `aspect_mentions` (Granular aspects, mapped 1:1 with Milvus Vectors)
- `weekly_reports` & `weekly_topics` (Summaries)
- `chat_sessions` & `chat_messages`
  - `chat_messages` stores `tool_calls` and `tool_results` as JSONB.
  - *Decision*: `tool_results` only stores execution metadata (count/time), NOT the raw data payload, to save DB space and keep debugging clean.

## 6. Week 4 Product Surfaces (Phases 0–10)

- The Next.js app uses TanStack Query for dashboard server state, React Context for JWT session state, and local component state for visible filters and streamed content. Redux/Zustand were not added.
- `/overview` consumes only public `GET /api/weeks`, `GET /api/overview`, and `GET /api/skus`. It does not calculate new business metrics or fabricate the unavailable portfolio-movement metric.
- `/skus/[sku_code]` composes existing SKU detail, trend, and positive/negative evidence reads. It filters selectable weeks to the `skus_covered` values returned by the backend, and renders raw backend trend points rather than client-side aggregates.
- `AnswerCitation` is the shared evidence view model. The reusable frontend evidence card exposes the exact evidence preview and expandable `mention_id`/`document_id` plus source metadata. This preserves `mention_id == aspect_mentions.id == Milvus vector id` traceability.
- `/compare` limits SKU B to a dashboard-enabled SKU in SKU A's `capacity_tier`, but `GET /api/compare` remains the independent server-side constraint boundary. It composes existing comparison, detail, trend, and evidence reads; no comparison-specific backend or LLM service was introduced.
- The comparison page may request a one-shot grounded summary through the existing authenticated `POST /api/ask` SSE endpoint. Its message explicitly names the visible SKU pair and ISO week; it introduces no hidden Agent filters or comparison memory. It renders only streamed answer deltas and Agent-emitted citations.
- Phases 0–6 introduced no migrations, persistence-model changes, or new backend routes. Phase 7 adds authenticated `POST /api/reports/generate`: deterministic analytics and filtered RAG evidence are passed to a bounded report writer; the candidate is validated and only then inserted or atomically replaces the existing `(sku_id, week_id)` row. Failed generation, validation, persistence, or cancellation rolls back and leaves a prior report intact.
- Report generation SSE emits `report_started`, stage lifecycle events, ordered candidate `report_delta` chunks, then `report_completed` only after commit; safe terminal `error` events never expose provider text or stack traces. The provider adapter remains completion-based, so candidate chunks are not provider-token streaming.
- `weekly_reports` still has no durable report-to-mention relation. Report generation can use retrieved evidence for synthesis, but report-level interactive citations are not exposed or invented.
- `/reports` retrieves an existing report for an explicit SKU/week and never generates on page load or refresh. Its Generate/Regenerate action consumes only the safe report SSE lifecycle, translates stages into user-facing progress, and replaces the visible report only after `report_completed`. Candidate deltas are never presented as persisted content; failed regeneration keeps the prior report visible.
- `/ask` is protected by the existing authenticated app shell and streams only the established `POST /api/ask` contract. The browser keeps its visible messages locally and returns the committed `session_id` only for a follow-up; conversation context remains the server's recent-N messages with no hidden agent filters or state. Tool lifecycle events become friendly status text, while only Agent-emitted used citations are rendered in popovers with their evidence preview, platform, SKU, and week. Cancellation uses `AbortController`; structured errors and abstentions are shown safely without raw tool arguments, provider details, stack traces, or hidden reasoning.
- The Phase 10 reliability pass adds local stream cancellation and terminal-event checks to the existing Ask, comparison-summary, and report-generation consumers. An unexpected stream close is a retryable user-facing failure, never a successful completion; cancelled report regeneration preserves the already persisted report. The app segment also has a safe retry boundary, auth bootstrap failures offer retry, and evidence/citation UI wraps long traceability fields without changing provenance.

## 7. Week 4 Evaluation (Phases 11–13)

- `shared/eval/semantic_golden.py` defines a separately curated 50-case semantic Golden dataset. It complements, rather than replaces, the 20-case deterministic Week 3 router regression suite.
- `shared/eval/rag_eval.py` evaluates normal `AgentRunResult` objects or persisted observations. Deterministic checks enforce tool selection and bounds, numeric values, citation requirements and provenance, abstention, visible follow-up context, and cross-tier restrictions. Structured LLM judging is limited to answer correctness, retrieval relevance, citation groundedness, and unsupported-claim assessment.
- An evaluation report retains every case, check, judge result or error, category, dimension score, and locked release gate. An unmeasured semantic gate is failed rather than averaged away; no failure is hidden behind a combined score.
- The Phase 13 controlled executor (`shared/eval/fixture_execution.py`) is deliberately bound to the Golden fixtures, and `shared/eval/fixture_live_run.py` runs those observations through the configured LLM judge. This is repeatable evaluation infrastructure, not a replacement for live PostgreSQL/Milvus or browser release verification.
- The final Phase 13 fixture/provider artifact is `artifacts/eval/phase13_fixture_live_judge.json`. It meets all locked gates, while retaining a non-blocking SG37 judge-quality review category; Phase 14 must still validate a clean live environment and browser product flows.

## 8. Flowchart

    flowchart TD
      %% Batch Pipeline (Worker Process)
      subgraph Pipeline [APScheduler Worker Process]
        A[Ingest: Reddit/Amazon] --> B[Sanitize: Presidio PII]
        B --> C[Enrich: Aspect/Sentiment]
        C --> D{Storage Router}
        D -->|embedding-3 / Dim=1024| E[(Milvus Vector DB)]
        D -->|Sync UUID| F[(PostgreSQL)]
      end

      %% Real-time User Interaction (API Process; /api/ask requires JWT)
      subgraph Interaction [FastAPI Process]
        U((User)) -->|Ask: 'Delta 2 noise?'| H[Next.js Frontend]
        H -->|POST /api/ask| I[Pure Function Calling Router]
        
        I -->|Stored macro report| J[tool_report]
        I -->|Exact evidence| K[tool_rag]
        I -->|Deterministic metrics| L[tool_sql]
        
        J --> F
        K --> E
        K -.->|Fetch full text by UUID| F
        L --> F
        
        I --> M[Synthesize Answer with Citations]
        M -->|Structured SSE + used citations| H
      end
