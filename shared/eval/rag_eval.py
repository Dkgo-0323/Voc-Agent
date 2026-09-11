"""Repeatable semantic evaluation for the controlled VOC Agent.

Phase 12 deliberately separates deterministic contract checks from an optional
structured LLM judge.  The runner does not create a second Agent or bypass the
normal router: callers provide an executor that returns ``AgentRunResult`` for
each reviewed Golden case.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from statistics import fmean
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.app.agent.llm import ChatModelProtocol
from backend.app.agent.schemas import AgentRunResult, AgentStatus, ToolStatus
from shared.eval.semantic_golden import (
    SEMANTIC_GOLDEN_DATASET,
    CitationExpectation,
    GoldenCategory,
    NumericExpectation,
    SemanticGoldenCase,
    SemanticGoldenDataset,
    Tool,
)


class EvaluationDimension(StrEnum):
    ROUTING = "routing_correctness"
    RETRIEVAL = "retrieval_relevance"
    ANSWER = "answer_correctness"
    CITATION = "citation_groundedness"
    ABSTENTION = "abstention_correctness"
    FOLLOW_UP = "follow_up_context_correctness"
    NUMERIC = "numeric_correctness"
    CROSS_TIER = "cross_tier_business_rule"
    PROVENANCE = "citation_provenance"
    UNSUPPORTED = "critical_unsupported_claim"


class FailureCategory(StrEnum):
    ROUTING = "routing"
    RETRIEVAL = "retrieval"
    ANALYTICS = "analytics_data"
    GROUNDING = "grounding_citation"
    CONVERSATION = "conversation"
    ABSTENTION = "abstention"
    REPORT = "report"
    INFRASTRUCTURE = "infrastructure"


class EvaluationCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension: EvaluationDimension
    name: str = Field(min_length=1)
    applicable: bool
    passed: bool | None = None
    details: str = Field(min_length=1)


class JudgeAssessment(BaseModel):
    """Strict, compact semantic assessment returned by an LLM judge."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    answer_correctness: float = Field(ge=0, le=1)
    retrieval_relevance: float | None = Field(default=None, ge=0, le=1)
    citation_groundedness: float | None = Field(default=None, ge=0, le=1)
    critical_unsupported_claim: bool
    rationale: str = Field(min_length=1, max_length=600)


class ObservedCase(BaseModel):
    """Machine-readable router result captured by a fixture or live executor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^SG[0-9]{2}$")
    result: AgentRunResult


class CaseEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    category: GoldenCategory
    checks: list[EvaluationCheck]
    judge: JudgeAssessment | None = None
    judge_error: str | None = None
    failure_categories: list[FailureCategory]


class DimensionScore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension: EvaluationDimension
    applicable_cases: int = Field(ge=0)
    passed_cases: int = Field(ge=0)
    score: float | None = Field(default=None, ge=0, le=1)


class ReleaseGate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    threshold: float | int
    actual: float | int | None
    passed: bool
    measured: bool


class EvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: str
    generated_at: datetime
    results: list[CaseEvaluation]
    dimensions: list[DimensionScore]
    gates: list[ReleaseGate]
    failures_by_category: dict[FailureCategory, list[str]]
    overall_passed: bool


class CaseExecutor(Protocol):
    async def __call__(self, case: SemanticGoldenCase) -> AgentRunResult: ...


class SemanticJudge(Protocol):
    async def assess(
        self, case: SemanticGoldenCase, result: AgentRunResult
    ) -> JudgeAssessment: ...


class StructuredLlmJudge:
    """Use the existing completion adapter only for semantic scoring."""

    def __init__(self, model: ChatModelProtocol) -> None:
        self._model = model

    async def assess(
        self, case: SemanticGoldenCase, result: AgentRunResult
    ) -> JudgeAssessment:
        payload = {
            "case": case.model_dump(mode="json"),
            "result": result.model_dump(mode="json"),
        }
        response = await self._model.complete(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a strict VOC evaluation judge. Score only semantic quality, "
                        "not tool mechanics. Return valid JSON only with exactly: "
                        "answer_correctness (0..1), retrieval_relevance (0..1 or null), "
                        "citation_groundedness (0..1 or null), critical_unsupported_claim "
                        "(boolean), rationale (one concise sentence). Treat unsupported causal "
                        "or comparative claims as critical when material."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                },
            ],
            tools=[],
        )
        if not response.content:
            raise ValueError("judge returned an empty response")
        return JudgeAssessment.model_validate_json(response.content)


def _tool_names(result: AgentRunResult) -> set[Tool]:
    names: set[Tool] = set()
    for trace in result.tool_trace:
        try:
            names.add(Tool(trace.tool_name))
        except ValueError:
            continue
    return names


def _check_routing(case: SemanticGoldenCase, result: AgentRunResult) -> EvaluationCheck:
    actual = _tool_names(result)
    required = set(case.required_tools)
    allowed = set(case.allowed_tools)
    forbidden = set(case.forbidden_tools)
    passed = (
        required.issubset(actual)
        and actual.issubset(allowed)
        and not (actual & forbidden)
        and result.execution.executed_tool_call_count <= result.execution.maximum_tool_calls
    )
    return EvaluationCheck(
        dimension=EvaluationDimension.ROUTING,
        name="approved_tool_selection",
        applicable=True,
        passed=passed,
        details=(
            f"required={sorted(required)}, actual={sorted(actual)}, "
            f"allowed={sorted(allowed)}, executed={result.execution.executed_tool_call_count}."
        ),
    )


def _numeric_strings(expectation: NumericExpectation) -> set[str]:
    value = expectation.value
    if isinstance(value, float) and not value.is_integer():
        return {str(value), f"{value * 100:g}%"}
    return {str(int(value)), str(float(value))}


def _check_numeric(case: SemanticGoldenCase, result: AgentRunResult) -> EvaluationCheck:
    if not case.numeric_expectations:
        return EvaluationCheck(
            dimension=EvaluationDimension.NUMERIC,
            name="expected_numeric_values",
            applicable=False,
            details="Case has no deterministic numeric expectation.",
        )
    answer = result.final_answer.lower()
    missing = [
        expectation.metric
        for expectation in case.numeric_expectations
        if not any(
            re.search(rf"(?<![0-9.]){re.escape(value.lower())}(?![0-9.])", answer)
            for value in _numeric_strings(expectation)
        )
    ]
    return EvaluationCheck(
        dimension=EvaluationDimension.NUMERIC,
        name="expected_numeric_values",
        applicable=True,
        passed=not missing,
        details=(
            "All expected numeric values were present."
            if not missing
            else f"Answer did not contain expected values for: {', '.join(missing)}."
        ),
    )


def _check_citations(case: SemanticGoldenCase, result: AgentRunResult) -> list[EvaluationCheck]:
    citations = result.citations
    has_successful_rag = any(
        trace.tool_name == Tool.RAG.value
        and trace.status in {ToolStatus.SUCCESS, ToolStatus.PARTIAL}
        for trace in result.tool_trace
    )
    if case.citation_expectation is CitationExpectation.OPTIONAL:
        required_check = EvaluationCheck(
            dimension=EvaluationDimension.CITATION,
            name="citation_requirement",
            applicable=False,
            details="Case permits citations but does not require them.",
        )
    elif case.citation_expectation is CitationExpectation.REQUIRED:
        required_check = EvaluationCheck(
            dimension=EvaluationDimension.CITATION,
            name="citation_requirement",
            applicable=True,
            passed=bool(citations) and has_successful_rag,
            details="Required citations must follow a successful RAG tool result.",
        )
    else:
        required_check = EvaluationCheck(
            dimension=EvaluationDimension.CITATION,
            name="citation_requirement",
            applicable=True,
            passed=not citations,
            details="Case forbids citations.",
        )
    provenance_ok = all(
        citation.document_id == citation.source.document_id
        and citation.sku_code == citation.source.sku_code
        and citation.evidence_preview.strip()
        for citation in citations
    ) and len({citation.mention_id for citation in citations}) == len(citations)
    return [
        required_check,
        EvaluationCheck(
            dimension=EvaluationDimension.PROVENANCE,
            name="citation_provenance",
            applicable=bool(citations),
            passed=provenance_ok if citations else None,
            details="Citations must retain unique mention IDs and matching source metadata.",
        ),
    ]


def _check_abstention(case: SemanticGoldenCase, result: AgentRunResult) -> EvaluationCheck:
    return EvaluationCheck(
        dimension=EvaluationDimension.ABSTENTION,
        name="required_abstention",
        applicable=case.abstention_required,
        passed=(result.status is AgentStatus.ABSTAINED)
        if case.abstention_required
        else None,
        details="Abstention is required for this case." if case.abstention_required else "Not an abstention case.",
    )


def _trace_sku_codes(result: AgentRunResult) -> set[str]:
    codes: set[str] = set()
    for trace in result.tool_trace:
        arguments = trace.normalized_arguments or {}
        value = arguments.get("sku_codes", arguments.get("sku_code"))
        if isinstance(value, list):
            codes.update(item for item in value if isinstance(item, str))
        elif isinstance(value, str):
            codes.add(value)
    return codes


def _check_follow_up(case: SemanticGoldenCase, result: AgentRunResult) -> EvaluationCheck:
    applies = case.category is GoldenCategory.FOLLOW_UP
    expected_codes = set(case.scope.sku_codes)
    actual_codes = _trace_sku_codes(result)
    return EvaluationCheck(
        dimension=EvaluationDimension.FOLLOW_UP,
        name="visible_context_resolution",
        applicable=applies,
        passed=expected_codes.issubset(actual_codes) if applies else None,
        details=(
            f"visible scope expected={sorted(expected_codes)}, routed={sorted(actual_codes)}."
            if applies
            else "Not a follow-up case."
        ),
    )


def _check_cross_tier(case: SemanticGoldenCase, result: AgentRunResult) -> EvaluationCheck:
    applies = (
        case.category is GoldenCategory.COMPARISON
        and len(case.scope.sku_codes) >= 2
        and not case.scope.requires_same_tier
    ) or case.abstention_required and len(case.scope.sku_codes) >= 2
    answer = result.final_answer.lower()
    disallowed_winner = any(word in answer for word in ("winner", "wins", "superior"))
    has_constraint = any(
        trace.error and trace.error.code == "capacity_tier_mismatch"
        for trace in result.tool_trace
    ) or "capacity tier" in answer
    return EvaluationCheck(
        dimension=EvaluationDimension.CROSS_TIER,
        name="cross_tier_constraint",
        applicable=applies,
        passed=(has_constraint and not disallowed_winner) if applies else None,
        details="Cross-tier cases must disclose the constraint and never choose a winner.",
    )


def _failure_categories(checks: Sequence[EvaluationCheck], judge: JudgeAssessment | None) -> list[FailureCategory]:
    categories: set[FailureCategory] = set()
    for check in checks:
        if check.applicable and check.passed is False:
            mapping = {
                EvaluationDimension.ROUTING: FailureCategory.ROUTING,
                EvaluationDimension.NUMERIC: FailureCategory.ANALYTICS,
                EvaluationDimension.CITATION: FailureCategory.GROUNDING,
                EvaluationDimension.PROVENANCE: FailureCategory.GROUNDING,
                EvaluationDimension.ABSTENTION: FailureCategory.ABSTENTION,
                EvaluationDimension.FOLLOW_UP: FailureCategory.CONVERSATION,
                EvaluationDimension.CROSS_TIER: FailureCategory.ROUTING,
            }
            categories.add(mapping.get(check.dimension, FailureCategory.INFRASTRUCTURE))
    if judge is not None:
        if judge.retrieval_relevance is not None and judge.retrieval_relevance < 0.85:
            categories.add(FailureCategory.RETRIEVAL)
        if judge.answer_correctness < 0.85 or judge.critical_unsupported_claim:
            categories.add(FailureCategory.GROUNDING)
    return sorted(categories)


async def evaluate_case(
    case: SemanticGoldenCase,
    result: AgentRunResult,
    *,
    judge: SemanticJudge | None = None,
) -> CaseEvaluation:
    checks = [
        _check_routing(case, result),
        _check_numeric(case, result),
        *_check_citations(case, result),
        _check_abstention(case, result),
        _check_follow_up(case, result),
        _check_cross_tier(case, result),
    ]
    assessment: JudgeAssessment | None = None
    judge_error: str | None = None
    if judge is not None:
        try:
            assessment = await judge.assess(case, result)
        except Exception:
            judge_error = "Structured semantic judge could not score this case."
    return CaseEvaluation(
        case_id=case.case_id,
        category=case.category,
        checks=checks,
        judge=assessment,
        judge_error=judge_error,
        failure_categories=_failure_categories(checks, assessment),
    )


def _dimension_scores(results: Sequence[CaseEvaluation]) -> list[DimensionScore]:
    scores: list[DimensionScore] = []
    deterministic_dimensions = (
        EvaluationDimension.ROUTING,
        EvaluationDimension.ABSTENTION,
        EvaluationDimension.FOLLOW_UP,
        EvaluationDimension.NUMERIC,
        EvaluationDimension.CROSS_TIER,
        EvaluationDimension.PROVENANCE,
    )
    for dimension in deterministic_dimensions:
        checks = [
            check
            for result in results
            for check in result.checks
            if check.dimension is dimension and check.applicable
        ]
        scores.append(
            DimensionScore(
                dimension=dimension,
                applicable_cases=len(checks),
                passed_cases=sum(check.passed is True for check in checks),
                score=(sum(check.passed is True for check in checks) / len(checks))
                if checks
                else None,
            )
        )
    for dimension, field_name in (
        (EvaluationDimension.RETRIEVAL, "retrieval_relevance"),
        (EvaluationDimension.ANSWER, "answer_correctness"),
        (EvaluationDimension.CITATION, "citation_groundedness"),
    ):
        values = [
            getattr(result.judge, field_name)
            for result in results
            if result.judge is not None
            and getattr(result.judge, field_name) is not None
            and (
                dimension is EvaluationDimension.ANSWER
                or any(
                    check.dimension is EvaluationDimension.CITATION
                    and check.name == "citation_requirement"
                    and check.applicable
                    for check in result.checks
                )
            )
        ]
        scores.append(
            DimensionScore(
                dimension=dimension,
                applicable_cases=len(values),
                passed_cases=sum(value >= 0.5 for value in values),
                score=fmean(values) if values else None,
            )
        )
    unsupported = [
        result.judge.critical_unsupported_claim
        for result in results
        if result.judge is not None
    ]
    scores.append(
        DimensionScore(
            dimension=EvaluationDimension.UNSUPPORTED,
            applicable_cases=len(unsupported),
            passed_cases=sum(not item for item in unsupported),
            score=(sum(not item for item in unsupported) / len(unsupported))
            if unsupported
            else None,
        )
    )
    return scores


def _score_by_dimension(scores: Sequence[DimensionScore], dimension: EvaluationDimension) -> float | None:
    return next((score.score for score in scores if score.dimension is dimension), None)


def _gates(scores: Sequence[DimensionScore]) -> list[ReleaseGate]:
    threshold_gates = (
        ("Tool / routing correctness", EvaluationDimension.ROUTING, 0.90),
        ("Answer correctness", EvaluationDimension.ANSWER, 0.85),
        ("Retrieval relevance", EvaluationDimension.RETRIEVAL, 0.85),
        ("Citation groundedness", EvaluationDimension.CITATION, 0.95),
        ("Abstention correctness", EvaluationDimension.ABSTENTION, 0.90),
        ("Follow-up context correctness", EvaluationDimension.FOLLOW_UP, 0.90),
        ("Deterministic numeric correctness", EvaluationDimension.NUMERIC, 1.00),
    )
    gates = [
        ReleaseGate(
            name=name,
            threshold=threshold,
            actual=_score_by_dimension(scores, dimension),
            measured=_score_by_dimension(scores, dimension) is not None,
            passed=(_score_by_dimension(scores, dimension) or 0) >= threshold,
        )
        for name, dimension, threshold in threshold_gates
    ]
    for name, dimension in (
        ("Cross-tier business-rule violations", EvaluationDimension.CROSS_TIER),
        ("Citation provenance violations", EvaluationDimension.PROVENANCE),
        ("Critical unsupported claims", EvaluationDimension.UNSUPPORTED),
    ):
        score = _score_by_dimension(scores, dimension)
        violations = None if score is None else round((1 - score) * next(
            item.applicable_cases for item in scores if item.dimension is dimension
        ))
        gates.append(
            ReleaseGate(
                name=name,
                threshold=0,
                actual=violations,
                measured=violations is not None,
                passed=violations == 0,
            )
        )
    return gates


def build_report(dataset: SemanticGoldenDataset, results: Sequence[CaseEvaluation]) -> EvaluationReport:
    scores = _dimension_scores(results)
    gates = _gates(scores)
    failures: dict[FailureCategory, list[str]] = defaultdict(list)
    for result in results:
        for category in result.failure_categories:
            failures[category].append(result.case_id)
        if result.judge_error:
            failures[FailureCategory.INFRASTRUCTURE].append(result.case_id)
    return EvaluationReport(
        dataset_id=dataset.dataset_id,
        generated_at=datetime.now(UTC),
        results=list(results),
        dimensions=scores,
        gates=gates,
        failures_by_category=dict(sorted(failures.items())),
        overall_passed=(
            all(gate.passed and gate.measured for gate in gates)
            and not failures.get(FailureCategory.INFRASTRUCTURE)
        ),
    )


async def run_dataset(
    executor: CaseExecutor,
    *,
    dataset: SemanticGoldenDataset = SEMANTIC_GOLDEN_DATASET,
    judge: SemanticJudge | None = None,
) -> EvaluationReport:
    results = []
    for case in dataset.cases:
        try:
            result = await executor(case)
            results.append(await evaluate_case(case, result, judge=judge))
        except Exception:
            results.append(
                CaseEvaluation(
                    case_id=case.case_id,
                    category=case.category,
                    checks=[],
                    judge_error="Case executor could not produce a valid Agent result.",
                    failure_categories=[FailureCategory.INFRASTRUCTURE],
                )
            )
    return build_report(dataset, results)


def evaluate_observations(
    observations: Sequence[ObservedCase],
    *,
    dataset: SemanticGoldenDataset = SEMANTIC_GOLDEN_DATASET,
    judge_results: dict[str, JudgeAssessment] | None = None,
) -> EvaluationReport:
    """Evaluate a persisted run; intended for CI and reproducible review."""
    known_ids = {case.case_id for case in dataset.cases}
    observed_ids = [observation.case_id for observation in observations]
    unknown_ids = sorted(set(observed_ids) - known_ids)
    if unknown_ids:
        raise ValueError(f"observations contain unknown Golden cases: {', '.join(unknown_ids)}")
    if len(observed_ids) != len(set(observed_ids)):
        raise ValueError("observations must contain at most one result per Golden case")
    by_id = {observation.case_id: observation.result for observation in observations}
    results = []
    for case in dataset.cases:
        result = by_id.get(case.case_id)
        if result is None:
            results.append(
                CaseEvaluation(
                    case_id=case.case_id,
                    category=case.category,
                    checks=[],
                    judge_error="No observed Agent result was supplied for this Golden case.",
                    failure_categories=[FailureCategory.INFRASTRUCTURE],
                )
            )
            continue
        checks = [
            _check_routing(case, result),
            _check_numeric(case, result),
            *_check_citations(case, result),
            _check_abstention(case, result),
            _check_follow_up(case, result),
            _check_cross_tier(case, result),
        ]
        assessment = (judge_results or {}).get(case.case_id)
        results.append(
            CaseEvaluation(
                case_id=case.case_id,
                category=case.category,
                checks=checks,
                judge=assessment,
                failure_categories=_failure_categories(checks, assessment),
            )
        )
    return build_report(dataset, results)


def write_report(report: EvaluationReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")


def render_summary(report: EvaluationReport) -> str:
    lines = [f"Semantic evaluation: {'PASS' if report.overall_passed else 'FAIL'}"]
    for score in report.dimensions:
        value = "not evaluated" if score.score is None else f"{score.score:.1%} ({score.passed_cases}/{score.applicable_cases})"
        lines.append(f"- {score.dimension}: {value}")
    lines.append("Release gates:")
    for gate in report.gates:
        actual = "not evaluated" if gate.actual is None else str(gate.actual)
        lines.append(f"- {'PASS' if gate.passed else 'FAIL'} {gate.name}: {actual} (target {gate.threshold})")
    if report.failures_by_category:
        lines.append("Failures:")
        lines.extend(f"- {category}: {', '.join(case_ids)}" for category, case_ids in report.failures_by_category.items())
    return "\n".join(lines)


def _load_observations(path: Path) -> list[ObservedCase]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("observation file must contain a JSON array")
    return [ObservedCase.model_validate(item) for item in raw]


def _load_judge_results(path: Path) -> dict[str, JudgeAssessment]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("judge result file must contain a JSON object keyed by case ID")
    return {case_id: JudgeAssessment.model_validate(value) for case_id, value in raw.items()}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate VOC Agent Golden observations")
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument(
        "--judge-results",
        type=Path,
        help="Optional JSON object of structured judge assessments keyed by Golden case ID.",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = evaluate_observations(
            _load_observations(args.observations),
            judge_results=(
                _load_judge_results(args.judge_results)
                if args.judge_results is not None
                else None
            ),
        )
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as exc:
        parser.error(f"invalid observations: {exc}")
    write_report(report, args.output)
    print(render_summary(report))
    return 0 if report.overall_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
