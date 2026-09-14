# Week 4 Thread Closing Handoff

## Actual completed scope

Week 4 Phases 0 through 13 are complete in code and commits. Phases 11–13
added the curated 50-case semantic dataset, the gated evaluation framework,
and a fixture-backed provider-judged evaluation run. No product Agent routing,
RAG, SQL analytics, report generation, frontend behavior, HTTP API, database
schema, Alembic migration, or SSE contract was changed by these phases.

The next planned work is **Phase 14 — Release Verification**. It must validate
a fresh PostgreSQL migration/seed setup, Milvus and embedding prerequisites,
and the browser release flow. Do not treat fixture evaluation as that live
environment validation. Phase 15 remains the README/runbook and demo-polish
phase.

## Preserved architecture and contracts

- PostgreSQL remains the relational source of truth. Milvus vector IDs are the
  matching `aspect_mentions.id` UUIDs; citations preserve that provenance to
  `documents.id`.
- The handwritten bounded Agent remains the architecture. Deterministic
  calculation, SKU/taxonomy validation, and capacity-tier restrictions remain
  in application code, not the LLM. Cross-tier comparison remains enforced
  server-side.
- `tool_sql`, `tool_rag`, and read-only `tool_report` remain the only Agent
  tools. The router retains its maximum of three attempted tool calls.
- Conversation state remains persisted PostgreSQL recent-N messages (default
  8). There is no hidden active filter, summary, or Agent state.
- `POST /api/ask` retains the established structured SSE lifecycle:
  `tool_started`/`tool_completed`, answer deltas, used-citation events, and a
  committed terminal `done`, or a safe structured `error`. Report-generation
  SSE remains separate and unchanged.
- `shared/eval/rag_eval.py` treats deterministic checks and structured LLM
  judging separately. Its JSON report preserves per-case checks, judge
  outcomes/errors, dimensions, gates, and failure categories. Unmeasured
  semantic gates fail instead of disappearing into an average.

## Evaluation evidence and limitations

`artifacts/eval/phase13_fixture_live_judge.json` is the final 50-case result:
all locked release gates pass (routing 100%, answer correctness 99%, retrieval
100%, citation groundedness 100%, abstention 100%, follow-up 100%, numeric
100%; all three zero-tolerance violation counts are zero). All 50 individual
answer-correctness checks passed; 99% is the mean judge score.

The artifact retains `SG37` under `grounding_citation` as a non-blocking
judge-quality review item. The controlled fixture executor is intentionally
not browser E2E or live PostgreSQL/Milvus Agent execution. LLM judges are
non-deterministic, so Phase 14 should inspect failures/borderline cases and a
sample of passing cases again. README remains intentionally unfinished until
Phase 15.

## Passing validation commands

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_week3_golden_queries.py tests/test_eval_fixture_execution.py tests/test_rag_eval.py tests/test_semantic_golden_dataset.py -q
.\.venv\Scripts\python.exe -m ruff check shared/eval tests/test_eval_fixture_execution.py tests/test_rag_eval.py
.\.venv\Scripts\python.exe -m pytest -q
```

The first command is the focused deterministic/evaluation set. The final
command is the complete backend regression suite. A configured provider is
required to repeat the full semantic judge run:

```powershell
.\.venv\Scripts\python.exe -m shared.eval.fixture_live_run --output artifacts/eval/phase13_fixture_live_judge.json
```
