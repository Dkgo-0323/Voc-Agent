# MVP TODO (4 Weeks: Batch to Agent)

## Week 1: Infrastructure & Data Foundation
- [ ] Initialize repo, uv/poetry, `.env.example`.
- [ ] Set up async FastAPI structure (`backend/app`).
- [ ] Set up SQLAlchemy 2.0 + Alembic:
  - [ ] Configure `alembic.ini`.
  - [ ] Define initial models (`Document`, `WeeklyTopic`).
  - [ ] Generate first migration (SQLite locally).
- [ ] Build Data Ingestion Scripts (Reddit + Amazon):
  - [ ] Fetch, clean (Presidio anonymization), and map to DB schema.
  - [ ] Insert into SQLite using async sessions.
- [ ] Set up Docker compose for Milvus (and optionally Postgres).

## Week 2: Enrichment, Embedding & APScheduler
- [ ] Local Enrichment Pipeline:
  - [ ] Aspect extraction & actionable scoring.
- [ ] Milvus Integration:
  - [ ] Define async Milvus repository.
  - [ ] Compute embeddings and upsert with metadata (platform, brand, sku).
- [ ] Scheduling (APScheduler):
  - [ ] Integrate APScheduler into FastAPI lifespan events (or as a separate worker script).
  - [ ] Schedule the pipeline to run every Sunday night.
- [ ] Implement basic GET APIs for dashboard (weeks, overview, skus).

## Week 3: Agentic RAG & Function Calling (The Core)
- [ ] Build Agent Tools (`backend/app/agent/`):
  - [ ] `tool_sql.py`: Tools to fetch top negative topics or brand sentiment scores.
  - [ ] `tool_rag.py`: Tools to query Milvus for specific aspect mentions (e.g., "give me 5 quotes about noise").
- [ ] Build LLM Router:
  - [ ] Use OpenAI API (or compatible local LLM) with `tools` array.
  - [ ] Implement the execution loop (parse user -> call tool -> get tool result -> generate final answer).
- [ ] Implement `POST /api/ask` endpoint:
  - [ ] Accept chat history.
  - [ ] Return streaming response with citation metadata.

## Week 4: Frontend, Eval & Polish
- [ ] Next.js Frontend Development:
  - [ ] Dashboard pages (Static views).
  - [ ] Chat Interface ("Ask your data") with Markdown rendering and citation popovers.
- [ ] Evaluation System:
  - [ ] Write 50 "Golden Queries" (e.g., "Is Jackery 1000 better than Anker C1000?").
  - [ ] Run `shared/eval/rag_eval.py` to test RAG accuracy.
  - [ ] Tweak system prompts and chunk retrieval numbers based on eval.
- [ ] Final Polish:
  - [ ] Test Alembic migration on a fresh PostgreSQL instance.
  - [ ] Write clear "How to Run" in `README.md`.