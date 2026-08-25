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

## Week 2: Enrichment, Embedding & APScheduler (🚧 Up Next)
- [ ] **Local Enrichment Pipeline**:
  - [ ] Read raw data from `documents` table.
  - [ ] Aspect extraction & sentiment analysis -> write to `aspect_mentions` table.
  - [ ] Calculate actionable quality score (`quality_score`).
- [ ] **Milvus Integration**:
  - [ ] Setup Milvus async repository.
- [ ] Calculate embeddings using Zhipu `embedding-3` (dim from `EMBEDDING_DIMENSIONS`, currently 1024) on `mention_text` + `context_window`.
  - [ ] Upsert to Milvus. **CRITICAL**: Use `aspect_mentions.id` (UUID) as Milvus Vector primary key. Map `sku_code`, `aspect_label`, `sentiment`, `week_id` as metadata.
- [ ] **Scheduling (APScheduler)**:
  - [ ] Fill pipeline logic in `backend/worker/jobs.py`.
  - [ ] Schedule the batch job to run seamlessly in the independent worker process.
- [ ] **Basic Dashboard APIs**: Implement GET `/weeks`, `/overview`, `/skus`.

## Week 3: Agentic RAG & Function Calling (The Core)
- [ ] **Build Agent Tools (`backend/app/agent/`)**:
  - [ ] `tool_report`: Fetch weekly markdown report (Highest priority for macro/summary queries).
  - [ ] `tool_sql`: Query PostgreSQL for structured data, trends, counts, and competitor scores (Filtered by `capacity_tier`).
  - [ ] `tool_rag`: Hybrid search in Milvus + PostgreSQL for specific user quotes and semantic aspects.
- [ ] **Build Pure LLM Router (No LangChain/LlamaIndex)**:
  - [ ] Write a pure Function Calling Loop (approx. 30 lines) supporting multi-turn tool calls.
  - [ ] Implement System Prompt with strict routing priorities (1. Report -> 2. RAG -> 3. SQL).
- [ ] **Implement `POST /api/ask` Endpoint**:
  - [ ] Manage chat history in PostgreSQL `chat_messages` table (Store tool execution metadata in `tool_results` JSONB).
  - [ ] Implement two-stage streaming: ① Tool execution loading state -> ② Final answer token streaming.
  - [ ] Include cited `aspect_mentions` UUIDs in response.
- [ ] **Auth**: Implement simple single-password + JWT auth in `core/security.py`.

## Week 4: Frontend, Eval & Polish
- [ ] **Next.js Frontend Development**:
  - [ ] Dashboard pages (Static views).
  - [ ] Chat Interface ("Ask your data"): Handle the two-stage streaming, render Markdown, show citation popovers.
- [ ] **Evaluation System**:
  - [ ] Write 50 "Golden Queries" (e.g., "Is Jackery 1000 better than Anker C1000?").
  - [ ] Run `shared/eval/rag_eval.py` to test RAG accuracy.
  - [ ] Tweak system prompts and chunk retrieval numbers based on eval.
- [ ] **Final Polish**:
  - [ ] Test Alembic migration on a fresh PostgreSQL instance.
  - [ ] Write clear "How to Run" in `README.md`.
