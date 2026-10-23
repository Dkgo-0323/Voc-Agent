# Validation evidence

This index separates what each validation layer establishes. Results below are
historical; documentation and screenshots were updated on 2026-10-23 without
rerunning business acceptance or calling model providers.

## Deterministic checks and delivery

Implementation revision: `89789826e290d359b826ca0df5ca3b87806adf78`.
On 2026-10-23, the GitHub Actions API was read again: all three linked runs
were `completed / success` and referenced this exact revision.
Counts and job details below come from the [2026-10-22 delivery record](development/journal.md).

| Evidence | Recorded outcome | What it establishes / excludes |
| --- | --- | --- |
| [Backend CI](https://github.com/Dkgo-0323/Voc-Agent/actions/runs/39722565442) | Linux: 307 passed, 4 warnings; wheel content and six installed imports passed | Deterministic contracts and packaging; no real provider/database integration claim. |
| [Frontend CI](https://github.com/Dkgo-0323/Voc-Agent/actions/runs/39722565505) | 54 tests passed; production build passed | Component behavior and compilation; not browser E2E. |
| [Container CI](https://github.com/Dkgo-0323/Voc-Agent/actions/runs/39722565560) | Startup/repeated seed/internal network/worker initialization, 768-D rejection, init failure and recovery passed | Isolated runtime delivery using a fixed-vector test provider; not semantic retrieval or scheduled task execution. |
| Local Windows checks, same delivery record | 306 passed, 1 POSIX-only test skipped, 3 warnings; Ruff passed | Cross-platform offline checks, separately recorded from Linux CI. |

Reproduction commands and environment boundaries:
[verification guide](development/verification.md), [container contract](../ops/README.md),
and [technical guide](technical-guide.md#tests-evaluation-and-release-gates).

## Controlled semantic evaluation

- Dataset: `week4_semantic_golden_v1`, 50 cases.
- [Machine-readable per-case report](../artifacts/eval/phase13_fixture_live_judge.json),
  generated `2026-09-12T03:40:24.101681Z`.
- [Phase 13 methodology and review](week4_phase13_handoff.md): controlled fixture
  responses with deterministic checks and a configured live LLM judge.
- Recorded metrics: tool/routing 100%, average answer correctness 99%, retrieval
  relevance 100%, citation groundedness 100%, abstention 100%, follow-up 100%,
  deterministic numeric correctness 100%; cross-tier, provenance, and critical
  unsupported-claim violations all zero.

The 99% is an average judge score, not a measured real-world success rate.
This run did not execute 50 live Agent/database requests. Judge nondeterminism
and the deliberately constructed fixture limit what these results imply.

## Historical browser integration

The [Phase 14 handoff](week4_phase14_handoff.md) records a final four-test
browser suite using an isolated synthetic dataset, PostgreSQL, Milvus, and
configured real providers. It records SQL/RAG/hybrid tools, visible-history
follow-up, no-data abstention, and citation ID auditing.

That handoff is a historical narrative record, not a fresh exact-run receipt.
The revised harness introduced at `8978982` records specific session/message/report
IDs and requires a fresh run UUID. Its offline behavior is tested; current live
Windows/Linux browser acceptance has not yet been completed. Historical Phase 14
success must not be presented as validation of the revised harness.

## Product screenshots

[Screenshot provenance](images/README.md) documents real frontend rendering
with browser-intercepted synthetic responses. Screenshots establish presentation
only: they do not validate the backend, data ingestion, or model answer quality.

## Open acceptance work

- Confirm public-review source conditions and preserve actual dates/SKU mappings.
- Wire request limits into the real runner and confirm model/token/cost boundaries.
- Run the revised browser and exact-ID audit workflow against isolated services.
- Evaluate representative real-data quality separately from synthetic regressions.
- Public deployment, multi-user security, and production load are outside the
  current delivered scope.

The [current plan](development/plan.md) tracks this work. A passing release gate,
a fixture score, and a screenshot are different evidence and remain separate here.
