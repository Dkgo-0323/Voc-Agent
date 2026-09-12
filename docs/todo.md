# MVP TODO (4 Weeks: Batch to Agent)

## Week 1: Infrastructure & Data Foundation (✅ Completed)
- [x] **Repo Init**: Initialize repo, `uv` package manager, `.env.example`.
- [x] **Async FastAPI Structure**: Set up `backend/app` with `main.py` and `core` config.
- [x] **Database & ORM**:
  - [x] Use Docker PostgreSQL 15 (Abandoned SQLite to ensure JSONB/ARRAY compatibility).
  - [x] Set up SQLAlchemy 2.0 (asyncio mode) + `asyncpg`.
  - [x] Configure Alembic (`env.py` in async mode, autogenerate).
  - [x] Define and migrate 7 core tables (`skus`, `documents`, `aspect_mentions`, `weekly_reports`, `weekly_topics`, `chat_sessions`, `chat_messages`).
- [x] **Data Ingestion (Pipelines)**:
  - [x] Setup `targets.py` with 5 locked SKUs (EcoFlow DELTA 2, Jackery 1000/240/300, Anker SOLIX F2000).
  - [x] Fetch Reddit via PRAW API.
  - [x] Load Amazon data from Julian McAuley static dataset (Parent ASINs).
  - [x] Sanitize data using Presidio (PII removal -> `author_hash`).
- [x] **Worker Skeleton**: Setup independent worker process (`python -m backend.worker.main`) using APScheduler.
- [x] **Infra**: `docker-compose up` for PostgreSQL + Milvus 2.x.

## Week 2: Enrichment, Embedding & APScheduler (✅ Completed)
- [x] **Local Enrichment Pipeline**:
  - [x] Read only raw documents for dashboard-enabled SKUs.
  - [x] Extract evidence-grounded aspects and sentiment, then persist to `aspect_mentions`.
  - [x] Calculate and enforce the actionable `quality_score` threshold in dashboard aggregates.
  - [x] Isolate failures per document and retain the processing error without blocking valid peers.
- [x] **Milvus Integration**:
  - [x] Set up the Milvus repository and enforce the 1024-dimension embedding contract.
  - [x] Build `embed_text`, persist it to PostgreSQL, then upsert vectors using `aspect_mentions.id` as the UUID primary key with scalar metadata.
- [x] **Scheduling (APScheduler)**:
  - [x] Implement the weekly orchestration in `backend/worker/jobs.py`.
  - [x] Schedule the independent worker every Sunday at 02:00 UTC with single-instance/coalescing protection.
- [x] **Basic Dashboard APIs**: Implement `GET /api/weeks`, `GET /api/overview`, and `GET /api/skus/{sku_code}/trends`.
- [x] **First-batch acceptance**: Processed one selected document for each locked SKU in a controlled network environment; all five reached `embedded`, producing 10 PostgreSQL mentions and 10 matching Milvus vectors. Verified document status, evidence/quality/embed-text contracts, vector UUID metadata, and all three Dashboard APIs.

## Week 3: Agentic RAG & Function Calling (✅ Completed)
- [x] **Controlled Agent tools**:
  - [x] Read-only `tool_report` with explicit `not_found` and Router-owned fallback.
  - [x] Deterministic `tool_sql` fixed operations with quality, dashboard, capacity-tier, and low-sample enforcement.
  - [x] Structured `tool_rag` with Milvus/PostgreSQL provenance and used-evidence-only citations.
- [x] **Pure handwritten LLM Router**:
  - [x] Composable single/multi-tool function-calling loop without LangChain/LlamaIndex.
  - [x] Hard three-call limit, no-data abstention, neutral comparison, and supported partial failures.
- [x] **Conversation persistence**:
  - [x] Reuse PostgreSQL `chat_sessions` and `chat_messages`.
  - [x] Configurable recent-N context (default 8), no hidden active-filter state, compact tool metadata only.
- [x] **`POST /api/ask` SSE endpoint**:
  - [x] Real-time tool lifecycle events and final answer chunks.
  - [x] Used citations only, stable completion identifiers, structured errors, and cancellation propagation.
- [x] **Auth**: Configured single-password login, JWT verification, `/api/auth/me`, and protected `/api/ask`; dashboard routes remain public.
- [x] **Reliability and Week 3 sign-off**:
  - [x] Structured tool/LLM/RAG error categories, controlled partial failures, and duplicate/call-limit guards.
  - [x] Deterministic 19-query smoke/golden acceptance set covering quantitative, qualitative, combined, follow-up, no-data, comparison, and fallback behavior.
  - [x] Week 2 regression verification: processing states, embedding dimension, UUID provenance, dashboard APIs, shared quality threshold, and independent APScheduler worker.
  - [x] Final documentation synchronization for the implemented controlled Agent design.
  - [x] Live authenticated RAG E2E verification with the configured Zhipu LLM and embedding provider, Milvus retrieval, PostgreSQL evidence hydration, SSE citation, and `done:success`.

## Week 4: Frontend, Eval & Polish
- [x] **Next.js Frontend Development**:
  - [x] Product foundation, JWT session flow, Overview, Level 2 SKU Detail, and same-tier Compare (Phases 1–6).
  - [x] Weekly Report viewer and explicit streamed generation (Phase 8).
  - [x] Ask Your Data browser workspace (Phase 9).
  - [x] UX and reliability pass across completed routes and streams (Phase 10).
- [x] **Weekly Report Backend (Phase 7)**:
  - [x] Authenticated `POST /api/reports/generate` SSE lifecycle with safe errors.
  - [x] Deterministic analytics plus filtered RAG evidence, bounded LLM synthesis, and candidate validation.
  - [x] Transactional create/replacement that preserves a prior report on failure or cancellation.
- [x] **Evaluation System**:
  - [x] Write and validate the 50-query semantic Golden dataset (Phase 11).
  - [x] Implement the semantic evaluation framework with deterministic checks, structured LLM judge support, JSON output, and release gates (Phase 12).
  - [x] Run fixture-backed semantic evaluation, classify failures, and fix evaluation root causes without changing Agent behavior (Phase 13).
- [ ] **Final Polish**:
  - [ ] Test Alembic migration on a fresh PostgreSQL instance.
  - [ ] Write clear "How to Run" in `README.md`.
