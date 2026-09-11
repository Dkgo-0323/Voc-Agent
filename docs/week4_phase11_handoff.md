# Week 4 Phase 11 Handoff

## Completed phase

Phase 11 adds a separate, curated **50-case semantic Golden dataset** in
`shared/eval/semantic_golden.py`. It is intentionally a benchmark
specification only: no evaluator, LLM judge, Agent behavior, retrieval tuning,
or release gate execution was added.

The existing 19-query deterministic Week 3 suite remains unchanged at
`tests/test_week3_golden_queries.py` and is still the regression baseline.

## Dataset contract

Every case has a stable ID, category, question, explicit fixture/setup
assumption, visible conversation where applicable, required/allowed/forbidden
tools, scoped SKU/week/tier expectations, optional deterministic metrics,
evidence/citation requirement, abstention requirement, answer characteristics,
and human review notes.

Coverage is exactly:

- 7 quantitative
- 6 trend
- 7 comparison
- 10 evidence / qualitative RAG
- 6 SQL + RAG hybrid
- 5 conversational follow-up
- 5 no-data / abstention / invalid request
- 4 report-related

All cases are deliberately tied to the controlled router fixture used by the
Week 3 golden suite. This makes their data assumptions explicit and avoids
claiming that a live environment currently has equivalent inventory. A future
runner must provision equivalent fixtures, or report incompatible live-data
cases as infrastructure-invalid rather than score them as Agent failures.

## Preserved constraints

- `tool_sql`, `tool_rag`, and read-only `tool_report` remain the only Agent
  tools; the dataset does not introduce report generation as an Agent tool.
- Cross-tier cases expect server-side constraint enforcement and never a
  product winner.
- Evidence cases require used-citation provenance; abstention cases forbid
  citations and unsupported product claims.
- Follow-up cases define visible prior turns and do not rely on hidden state.
- Stored reports have no report-to-mention relation, so report citation cards
  remain out of scope.

## Validation

`tests/test_semantic_golden_dataset.py` validates the Pydantic dataset schema,
50-case uniqueness/order, exact category distribution, fixture assumptions,
tool-boundary invariants, citation/abstention rules, and follow-up context.

## Next phase

Phase 12 should build the evaluation runner around this dataset. It must keep
deterministic checks separate from structured LLM-judge dimensions and produce
per-case, per-dimension machine-readable results.
