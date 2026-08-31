# Week 3 Smoke/Golden Query Acceptance

## Scope and environment

This is the Phase 10 seed set for Week 4 evaluation. It exercises the production
`FunctionCallingRouter` and typed tool contracts with deterministic LLM/tool fakes.
It does not claim a live PostgreSQL, Milvus, or external LLM run. Week `202403` and
the reported values are controlled fixture data chosen to make expected results
stable and reviewable.

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_week3_golden_queries.py -q
```

Every case verifies raw and normalized arguments, actual tool order, the three-call
limit, final status, warnings, and citation count. The suite additionally verifies
visible recent-message context for follow-ups, deterministic abstention, cross-tier
enforcement, fallback disclosure, and evidence-ID citation provenance.

## Results

| ID | Category | Query | Expected sequence | Actual sequence | Fixture duration | Status | Key acceptance result |
|---|---|---|---|---|---|---|---|
| Q01 | Count/distribution | Negative Delta 2 mentions in fixture week 202403 | `tool_sql` | `tool_sql` | 4 ms | PASS | 12 fixture mentions across 8 reviews; arguments preserved. |
| Q02 | Count/distribution | Main Delta 2 complaint aspects in fixture week 202403 | `tool_sql` | `tool_sql` | 4 ms | PASS | Deterministic aspect distribution: noise 7, charging 5. |
| Q03 | Trend | Delta 2 negative sentiment over fixture weeks | `tool_sql` | `tool_sql` | 4 ms | PASS | Trend is grounded in typed points: 25% to 50%. |
| Q04 | Trend | Delta 2 fan/noise sentiment over fixture weeks | `tool_sql` | `tool_sql` | 4 ms | PASS | `aspect_trend` retains `noise_level` and week filters. |
| Q05 | Comparison | Delta 2 versus Jackery 1000 | `tool_sql` | `tool_sql` | 4 ms | PASS | Same-tier comparison succeeds and surfaces the low-sample warning. |
| Q06 | Comparison | Compare noise feedback and show an example | `tool_sql → tool_rag` | `tool_sql → tool_rag` | 7 ms | PASS | Metrics and exact evidence remain separately grounded; one used citation. |
| Q07 | Comparison | Deliberate Delta 2 versus Anker F2000 cross-tier comparison | `tool_sql` | `tool_sql` | 4 ms | PASS | `capacity_tier_mismatch` is surfaced; no winner is declared. |
| Q08 | Evidence | Actual Delta 2 fan-noise complaints | `tool_rag` | `tool_rag` | 3 ms | PASS | Exact excerpt maps to one retrieved mention citation. |
| Q09 | Evidence | Negative Delta 2 charging examples | `tool_rag` | `tool_rag` | 3 ms | PASS | Structured sentiment/aspect filters are preserved; citation is traceable. |
| Q10 | Evidence | Exact user wording for noise | `tool_rag` | `tool_rag` | 3 ms | PASS | Exact evidence cannot appear without its retrieved mention ID. |
| Q11 | Combined | Main complaints in fixture week 202403 | `tool_sql → tool_rag` | `tool_sql → tool_rag` | 7 ms | PASS | Quantitative ranking comes from SQL; example comes from RAG. |
| Q12 | Combined | Why fixture negativity rose | `tool_sql → tool_rag` | `tool_sql → tool_rag` | 7 ms | PASS | Direction is supported by fixture trend before qualitative context is cited. |
| Q13 | Combined | Most common complaint plus representative comment | `tool_sql → tool_rag` | `tool_sql → tool_rag` | 7 ms | PASS | Category count and exact comment use their approved sources. |
| Q14 | Follow-up | “What about noise specifically?” | `tool_sql` | `tool_sql` | 4 ms | PASS | Prior two-SKU context is present as recent visible messages. |
| Q15 | Follow-up | “Show me some actual comments.” | `tool_rag` | `tool_rag` | 3 ms | PASS | Same products/topic are resolved from recent visible messages; one citation. |
| Q16 | No data | Unsupported fixture issue | `tool_rag` | `tool_rag` | 3 ms | PASS | Model-prior answer is replaced by deterministic VOC abstention. |
| Q17 | No data | Over-restrictive valid noise filters | `tool_rag` | `tool_rag` | 3 ms | PASS | Empty retrieval abstains with no citation. |
| Q18 | Failure/fallback | Analytics available while RAG is unavailable | `tool_sql → tool_rag` | `tool_sql → tool_rag` | 7 ms | PASS | Partial quantitative answer discloses RAG failure and emits no quote/citation. |
| Q19 | Failure/fallback | Missing stored report | `tool_report → tool_sql` | `tool_report → tool_sql` | 6 ms | PASS | Report is read-only; Router explicitly chooses deterministic analytics fallback. |

## Acceptance dimensions

- Routing and argument correctness: asserted from actual `ToolCallTrace` values for
  every case, including schema-normalized defaults.
- Quantitative correctness: deterministic typed payloads support every numeric claim.
- Comparison constraints and warnings: Q05 verifies low-sample disclosure; Q07 verifies
  application-enforced capacity tiers.
- Citation correctness: exact excerpts in evidence cases cite only the deterministic
  retrieved `aspect_mentions`-style UUID; Q18 emits none when RAG fails.
- Unsupported claims: Q16–Q17 prove model-prior text is discarded on no-data.
- Follow-ups: Q14–Q15 inspect the actual message list passed to the Router.
- Call bound: all 19 cases assert attempted calls never exceed three.
- Latency: deterministic execution metadata is recorded by the fake tools, but it is
  not representative of live provider latency.

## Known limitation

This suite validates deterministic orchestration and safety contracts, not live data
availability or provider quality. A live external-service review remains separate
evidence and must not be inferred from these PASS results.
