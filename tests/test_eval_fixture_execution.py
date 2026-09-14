"""Tests for the controlled 50-case semantic evaluation fixture adapter."""

import pytest

from backend.app.agent.schemas import AgentStatus
from shared.eval.fixture_execution import fixture_observations, fixture_result
from shared.eval.rag_eval import EvaluationDimension, evaluate_case
from shared.eval.semantic_golden import SEMANTIC_GOLDEN_DATASET


def test_fixture_executor_produces_one_valid_observation_per_golden_case() -> None:
    observations = fixture_observations(SEMANTIC_GOLDEN_DATASET)

    assert len(observations) == 50
    assert {item.case_id for item in observations} == {
        case.case_id for case in SEMANTIC_GOLDEN_DATASET.cases
    }


@pytest.mark.asyncio
async def test_fixture_cross_tier_case_is_counted_and_safe() -> None:
    case = next(item for item in SEMANTIC_GOLDEN_DATASET.cases if item.case_id == "SG46")
    result = fixture_result(case)
    evaluation = await evaluate_case(case, result)

    cross_tier = next(
        check for check in evaluation.checks if check.dimension is EvaluationDimension.CROSS_TIER
    )
    assert cross_tier.applicable and cross_tier.passed
    assert result.status is AgentStatus.SUCCESS
