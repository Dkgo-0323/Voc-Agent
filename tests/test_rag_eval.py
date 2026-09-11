"""Focused contract tests for the Phase 12 semantic evaluation runner."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from backend.app.agent.schemas import (
    AgentExecutionMetadata,
    AgentRunResult,
    AgentStatus,
    AnswerCitation,
    ExpandedSourceMetadata,
    ToolCallTrace,
    ToolName,
    ToolStatus,
)
from shared.eval.rag_eval import (
    EvaluationDimension,
    JudgeAssessment,
    ObservedCase,
    build_report,
    evaluate_case,
    evaluate_observations,
    render_summary,
    run_dataset,
    write_report,
)
from shared.eval.semantic_golden import SEMANTIC_GOLDEN_DATASET


def _result(*, answer: str, tools: list[ToolName], status: AgentStatus = AgentStatus.SUCCESS, citations: list[AnswerCitation] | None = None) -> AgentRunResult:
    return AgentRunResult(
        status=status,
        final_answer=answer,
        citations=citations or [],
        tool_trace=[
            ToolCallTrace(
                call_id=f"call-{index}",
                tool_name=tool.value,
                normalized_arguments={"sku_codes": ["ecoflow-delta2", "jackery-explorer-1000"]},
                executed=True,
                status=ToolStatus.SUCCESS,
                duration_ms=1,
                result_count=1,
            )
            for index, tool in enumerate(tools)
        ],
        execution=AgentExecutionMetadata(
            model_round_count=1,
            attempted_tool_call_count=len(tools),
            executed_tool_call_count=len(tools),
            maximum_tool_calls=3,
        ),
    )


def _citation() -> AnswerCitation:
    document_id = uuid4()
    return AnswerCitation(
        mention_id=uuid4(),
        document_id=document_id,
        evidence_preview="the fan is very loud under load",
        sku_code="ecoflow-delta2",
        aspect_label="noise_level",
        sentiment="negative",
        week_id=202403,
        source=ExpandedSourceMetadata(
            document_id=document_id,
            sku_code="ecoflow-delta2",
            platform="amazon",
            published_at=datetime.now(UTC),
        ),
    )


class PassingJudge:
    async def assess(self, _case, _result) -> JudgeAssessment:
        return JudgeAssessment(
            answer_correctness=1,
            retrieval_relevance=1,
            citation_groundedness=1,
            critical_unsupported_claim=False,
            rationale="All supported expectations are met.",
        )


@pytest.mark.asyncio
async def test_case_evaluation_keeps_deterministic_and_semantic_checks_separate() -> None:
    case = next(item for item in SEMANTIC_GOLDEN_DATASET.cases if item.case_id == "SG31")
    evaluation = await evaluate_case(
        case,
        _result(answer="Noise has 7 mentions and 12 negative mentions.", tools=[ToolName.SQL, ToolName.RAG], citations=[_citation()]),
        judge=PassingJudge(),
    )

    assert all(check.passed is not False for check in evaluation.checks if check.applicable)
    assert evaluation.judge is not None
    assert not evaluation.failure_categories


@pytest.mark.asyncio
async def test_case_evaluation_detects_tool_numeric_and_required_citation_failures() -> None:
    case = next(item for item in SEMANTIC_GOLDEN_DATASET.cases if item.case_id == "SG31")
    evaluation = await evaluate_case(
        case,
        _result(answer="There are several complaints.", tools=[ToolName.SQL]),
    )

    failed = {check.dimension for check in evaluation.checks if check.passed is False}
    assert EvaluationDimension.ROUTING in failed
    assert EvaluationDimension.NUMERIC in failed
    assert EvaluationDimension.CITATION in failed


@pytest.mark.asyncio
async def test_numeric_check_does_not_accept_a_larger_number_with_the_same_suffix() -> None:
    case = next(item for item in SEMANTIC_GOLDEN_DATASET.cases if item.case_id == "SG01")
    evaluation = await evaluate_case(
        case,
        _result(answer="112 negative mentions across 80 reviews.", tools=[ToolName.SQL]),
    )

    numeric = next(check for check in evaluation.checks if check.dimension is EvaluationDimension.NUMERIC)
    assert numeric.passed is False


@pytest.mark.asyncio
async def test_abstention_and_follow_up_checks_are_deterministic() -> None:
    abstain_case = next(item for item in SEMANTIC_GOLDEN_DATASET.cases if item.case_id == "SG42")
    follow_up_case = next(item for item in SEMANTIC_GOLDEN_DATASET.cases if item.case_id == "SG37")
    abstain = await evaluate_case(
        abstain_case,
        _result(answer="No matching VOC evidence is available.", tools=[ToolName.RAG], status=AgentStatus.ABSTAINED),
    )
    follow_up = await evaluate_case(
        follow_up_case,
        _result(answer="Delta 2 and Jackery 1000 have compared noise feedback.", tools=[ToolName.SQL]),
    )

    assert next(check for check in abstain.checks if check.dimension is EvaluationDimension.ABSTENTION).passed
    assert next(check for check in follow_up.checks if check.dimension is EvaluationDimension.FOLLOW_UP).passed


def test_observation_report_is_machine_readable_and_never_hides_missing_cases(tmp_path: Path) -> None:
    observed = [
        ObservedCase(
            case_id="SG01",
            result=_result(answer="12 negative mentions across 8 reviews.", tools=[ToolName.SQL]),
        )
    ]
    report = evaluate_observations(observed)
    output = tmp_path / "evaluation.json"
    write_report(report, output)

    assert len(report.results) == 50
    assert report.overall_passed is False
    assert "infrastructure" in {str(key) for key in report.failures_by_category}
    assert output.exists()
    assert "Semantic evaluation: FAIL" in render_summary(report)


def test_observations_reject_unknown_or_duplicate_case_ids() -> None:
    observation = ObservedCase(
        case_id="SG01",
        result=_result(answer="12 negative mentions across 8 reviews.", tools=[ToolName.SQL]),
    )

    with pytest.raises(ValueError, match="at most one"):
        evaluate_observations([observation, observation])


def test_persisted_structured_judge_scores_contribute_to_semantic_dimensions() -> None:
    case = next(item for item in SEMANTIC_GOLDEN_DATASET.cases if item.case_id == "SG21")
    report = evaluate_observations(
        [
            ObservedCase(
                case_id=case.case_id,
                result=_result(
                    answer="A review says the fan is loud under load.",
                    tools=[ToolName.RAG],
                    citations=[_citation()],
                ),
            )
        ],
        judge_results={
            case.case_id: JudgeAssessment(
                answer_correctness=0.9,
                retrieval_relevance=0.95,
                citation_groundedness=1,
                critical_unsupported_claim=False,
                rationale="The cited evidence supports the answer.",
            )
        },
    )

    scores = {score.dimension: score.score for score in report.dimensions}
    assert scores[EvaluationDimension.RETRIEVAL] == 0.95
    assert scores[EvaluationDimension.CITATION] == 1


@pytest.mark.asyncio
async def test_run_dataset_records_executor_failures_per_case() -> None:
    async def failing_executor(_case):
        raise RuntimeError("fixture unavailable")

    report = await run_dataset(failing_executor)

    assert len(report.results) == 50
    assert all(result.failure_categories for result in report.results)
    assert build_report(SEMANTIC_GOLDEN_DATASET, report.results).overall_passed is False
