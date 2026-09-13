# Week 4 Phase 15 Handoff

Phase 15 documentation and demo polish completed on 2026-09-13. No product
functionality was added.

## Documentation synchronized

- `README.md` now states the problem/user, implemented architecture and stack,
  pipeline, Agent/tool boundaries, provenance, frontend routes/state, report
  workflow, evaluation layers/gates, environment, exact local commands, demo
  flow, and limitations.
- `docs/arch.md` now describes the final code contracts rather than the
  pre-frontend/phase-planning state.
- `docs/todo.md` closes Week 4 and links the release and documentation audits.
- `docs/week4_codex_development_plan.md` is explicitly marked as a completed
  historical plan so its future-tense acceptance text is not mistaken for
  implementation evidence.

Historical contract-freeze and per-phase handoffs were not rewritten: they
record what was true at their phase. Current behavior is authoritative in code
and summarized by the README and architecture document.

## Accuracy boundaries retained

- PostgreSQL is the relational source of truth and Milvus IDs equal
  `aspect_mentions.id`.
- deterministic calculations, quality rules, and capacity tiers remain
  server-side;
- the handwritten Agent has fixed report/SQL/RAG tools, recent-N visible
  context, bounded calls/rounds, and no hidden state;
- Ask citations remain traceable, while weekly reports have no report-to-
  mention citation relation;
- report SSE chunks a validated candidate and is not token streaming;
- the Phase 13 semantic result is controlled-fixture execution with a live LLM
  judge, while Phase 14 is the smaller real-service browser regression;
- the repository is documented as an engineering/demo MVP, not production
  ready.

## Verified baseline carried into Phase 15

Phase 14 recorded:

- Python: 234 tests passed; Ruff passed;
- frontend: 35 Vitest tests passed across 8 files; lint, typecheck, and build
  passed;
- Playwright release suite: 4 tests passed against disposable PostgreSQL,
  isolated Milvus, and configured real providers;
- fresh Alembic upgrade reached `f7a8b9c0d1e2 (head)` and the demo fixture
  verified PostgreSQL/Milvus UUID and 1024-dimension contracts;
- Phase 13: all 50 controlled semantic cases passed every release gate (99%
  average answer score, 100% on other measured percentage gates, zero
  zero-tolerance violations).

## Phase 15 final checks

After the documentation edits:

- Ruff passed;
- all 234 Python tests passed with the same three known dependency warnings;
- frontend lint and typecheck passed;
- all 35 Vitest tests in 8 files passed;
- the Next.js production build passed and emitted every implemented route;
- Alembic reported `f7a8b9c0d1e2 (head)`, both evaluation CLIs accepted their
  documented arguments, all documented local links resolved, and
  `git diff --check` passed;
- the saved Phase 13 artifact parsed as 50 cases with `overall_passed=true`
  and all ten release gates passing.

The live judge was not rerun for this documentation-only change because it is
nondeterministic and incurs provider calls. The Phase 14 browser suite was also
not repeated; its verified real-service result remains the release baseline.
