# Week 4 Phase 12 Handoff

## Completed phase

`shared/eval/rag_eval.py` provides the repeatable evaluation framework for the
Phase 11 50-case Golden dataset. It does not alter Agent routing, prompts,
retrieval, or report generation.

The runner accepts either an async executor returning the normal
`AgentRunResult` for each Golden case, or a persisted JSON array of
`ObservedCase` records. The latter supports CI/review reruns without rerunning
providers. It writes a machine-readable `EvaluationReport` and renders a
concise human summary. Missing cases are recorded as infrastructure failures;
they are never silently omitted.

## Checks and judge boundary

Deterministic checks cover approved/required/forbidden tools, tool-call bounds,
numeric values where Gold provides them, citation requirement/provenance,
required abstention, visible follow-up scope, and cross-tier constraint/winner
violations. No-data cases require Agent abstention; invalid SKU/week and
cross-tier requests require their existing safe validation/constraint outcomes
instead of an incorrectly forced abstention.

`StructuredLlmJudge` uses the existing completion adapter with no tools and a
strict JSON schema only for semantic scores: answer correctness, retrieval
relevance, citation groundedness, and critical unsupported claims. A judge
failure is an explicit infrastructure failure, not a passing score.

## Release output

Reports retain per-case checks, judge output/errors, failure categories,
per-dimension scores, and the locked Week 4 release gates. Gates with no
measurement are marked failed/not measured rather than averaged away.

The JSON CLI is:

```powershell
.\.venv\Scripts\python.exe -m shared.eval.rag_eval `
  --observations path\to\observations.json `
  --judge-results path\to\structured-judge-results.json `
  --output path\to\evaluation-report.json
```

`--judge-results` is optional, but leaving it out leaves semantic gates not
measured and therefore fails the release report. The CLI returns nonzero until
every gate is both measured and passing. Provider execution wiring and
failure-driven tuning are intentionally Phase 13 work.

## Next phase

Phase 13 should run the deterministic Week 3 suite and this 50-case evaluation
against a provisioned executor, classify failures, and tune only demonstrated
root causes.
