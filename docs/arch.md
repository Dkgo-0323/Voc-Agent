# Architecture & Key Decisions (Agent & RAG MVP)

## 0. Scope & Upgrades
- **Target**: Outdoor power stations VOC weekly intelligence + Interactive Agent.
- **Core Stack**: Python 3.11+, `uv`, FastAPI (Async), SQLAlchemy 2.0 (asyncio), PostgreSQL 15, Milvus 2.x.
- **Major Upgrades from v1**:
  - Completely abandoned SQLite to avoid Alembic migration incompatibilities with JSONB/ARRAY types.
  - Abandoned LangChain/LlamaIndex in favor of a **Pure Handwritten Function Calling Loop** for maximum transparency and control.
  - Chat history relies entirely on PostgreSQL with indexing (Abandoned Redis as over-engineering for MVP).
  - Independent Worker Process for APScheduler to prevent CPU-intensive pipelines from blocking the API event loop.

## 1. System Topology
- **Data Ingestion (Pipelines)**: Weekly batch processing. Fetches from PRAW (Reddit) & McAuley dataset (Amazon). Sanitizes via Presidio.
- **Worker Process**: Independent python process (`python -m backend.worker.main`) running APScheduler to execute the ingestion and enrichment pipelines.
- **Backend (FastAPI)**: Exposes REST APIs for dashboards AND a Stateful Chat API for the Agent. Single password + JWT authentication.
- **Agent Layer**: Multi-turn LLM Function Calling router.

## 2. Directory Structure

    voc-agent/
    ├── pyproject.toml               # uv package manager configs
    ├── alembic.ini                  # alembic configs
    ├── docs/                        # prompts.md, arch.md, todo.md
    ├── backend/                     # Async architecture
    │   ├── app/
    │   │   ├── main.py
    │   │   ├── core/                # settings, security.py (JWT), database.py (async engine)
    │   │   ├── api/
    │   │   ├── agent/               # ★ Core Agent Logic
    │   │   │   ├── tool_sql.py      # Structured data, trends, comparisons
    │   │   │   ├── tool_rag.py      # Quotes, aspect semantic search
    │   │   │   ├── tool_report.py   # Markdown summaries
    │   │   │   └── router.py        # Pure function calling loop
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
    ├── shared/
    │   └── eval/                    # rag_eval.py (LLM-as-a-Judge)
    ├── frontend/                    # Next.js
    └── docker-compose.yml           # PostgreSQL + Milvus

## 3. Agent Design & Tool Boundaries

The Agent operates on a handwritten multi-turn loop. It streams output to the frontend in two stages: ① Tool execution (loading state) → ② Final answer token streaming.

### Routing Priority & Tools
1. **`tool_report` (Priority 1)**: Triggered for macro/summary questions ("Last week's market summary"). Returns Markdown block. Fallback to `tool_rag` if report doesn't exist.
2. **`tool_rag` (Priority 2)**: Triggered when user explicitly wants "quotes/exact words/specific examples" ("How do users describe Delta 2 noise?"). Returns raw text + source metadata.
3. **`tool_sql` (Priority 3)**: Triggered for "data/trends/rankings/comparisons" ("Which brand had the most negative reviews?"). Returns structured numbers. *Comparisons are automatically restricted to the same `capacity_tier`.*

## 4. Storage & Schema Contracts

### Database Choices
- **RDBMS**: PostgreSQL 15. Managed by Alembic (`env.py` configured with `run_async_migrations`).
- **Vector DB**: Milvus 2.x (Docker). Uses Hybrid Search (Vector + Scalar Metadata filtering).

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
- `documents` (Raw reviews, handles PII `author_hash`, UNIQUE `platform` + `external_id`)
- `aspect_mentions` (Granular aspects, mapped 1:1 with Milvus Vectors)
- `weekly_reports` & `weekly_topics` (Summaries)
- `chat_sessions` & `chat_messages`
  - `chat_messages` stores `tool_calls` and `tool_results` as JSONB.
  - *Decision*: `tool_results` only stores execution metadata (count/time), NOT the raw data payload, to save DB space and keep debugging clean.

## 5. Flowchart

    flowchart TD
      %% Batch Pipeline (Worker Process)
      subgraph Pipeline [APScheduler Worker Process]
        A[Ingest: Reddit/Amazon] --> B[Sanitize: Presidio PII]
        B --> C[Enrich: Aspect/Sentiment]
        C --> D{Storage Router}
        D -->|Dim=1536 Embeddings| E[(Milvus Vector DB)]
        D -->|Sync UUID| F[(PostgreSQL)]
      end

      %% Real-time User Interaction (API Process)
      subgraph Interaction [FastAPI Process]
        U((User)) -->|Ask: 'Delta 2 noise?'| H[Next.js Frontend]
        H -->|POST /api/ask| I[Pure Function Calling Router]
        
        I -->|1. Macro| J[tool_report]
        I -->|2. Exact Quotes| K[tool_rag]
        I -->|3. Stats/Compare| L[tool_sql]
        
        J --> F
        K --> E
        K -.->|Fetch full text by UUID| F
        L --> F
        
        I --> M[Synthesize Answer with Citations]
        M -->|Two-stage Stream| H
      end