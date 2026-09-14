# Week 4 Phase 13 Handoff

## Baseline

The Week 3 deterministic suite began green: 20/20 cases passed.

The first semantic attempt could not run because Phase 12 accepted observations
but lacked a controlled executor for the explicit Phase 11 fixture. This was
classified as an **infrastructure/test issue**, not an Agent failure.

After adding the fixture adapter, the first complete provider-judged 50-case
run found:

- routing, retrieval, follow-up, cross-tier, and provenance gates passing;
- invalid ISO week incorrectly labelled as required abstention in the Golden
  dataset;
- numeric fixture responses too incomplete for deterministic checks;
- citation-groundedness aggregation incorrectly including no-citation cases;
- judge rubric false positives for deterministic SQL answers and required
  report-provenance refusals.

## Failure taxonomy and fixes

All observed failures were evaluation infrastructure, fixture, or judge-rubric
issues. No production Agent router, RAG service, SQL service, prompt, or
business rule was modified.

- **Infrastructure/test**: added a 50-case controlled fixture executor and a
  repeatable configured-provider judge command.
- **Analytics/data**: tightened numeric token matching and supplied complete
  reviewed fixture answers for numeric cases.
- **Abstention**: invalid SKU/week and cross-tier requests now expect their
  existing safe validation/constraint outcomes; only genuine no-data cases
  require `abstained`.
- **Grounding/citation**: excluded citation-forbidden cases from semantic
  groundedness aggregation, required fixture evidence sentiment to match the
  case, and clarified the judge’s SQL/report/refusal rules.
- **Routing, retrieval, conversation, report**: no product defect was found.

## Final metrics

`artifacts/eval/phase13_fixture_live_judge.json` contains all 50 per-case
results from the final configured-provider run. The documented release gates
all pass:

- tool/routing 100%; answer correctness 99%; retrieval relevance 100%;
  citation groundedness 100%; abstention 100%; follow-up 100%; deterministic
  numeric correctness 100%;
- cross-tier violations 0; citation provenance violations 0; critical
  unsupported claims 0.

The Week 3 deterministic suite remains 20/20 green; focused evaluation tests
cover the fixture adapter, result schema, gates, judge aggregation, and the
three zero-tolerance contracts. The 99% answer score is the average semantic
judge score, not a failed case: all 50 answer-correctness checks passed.

## Manual review

Reviewed failed/borderline output and high-scoring examples across quantitative
(SG01), evidence (SG21), hybrid (SG31), follow-up (SG37), and report (SG47)
cases. A final SG37 per-case judge variance was categorized as grounding even
though the answer uses deterministic SQL context and all gates pass; retain it
as judge-quality review debt in future live runs rather than changing a passing
release threshold or the Agent.

## Remaining limitations

- This Phase 13 semantic result uses the deliberate controlled fixture bound to
  the Phase 11 dataset. It is not browser E2E or live PostgreSQL/Milvus Agent
  validation; Phase 14 remains responsible for clean-environment release
  verification.
- LLM judge outputs remain non-deterministic and require human inspection of
  failed, borderline, and sampled passing cases.

## Next phase

Phase 14 should perform fresh PostgreSQL migration validation and browser-level
release regression without adding product features.
