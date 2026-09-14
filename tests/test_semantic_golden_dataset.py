"""Schema and coverage gate for the Week 4 Phase 11 Golden dataset."""

from collections import Counter

from shared.eval.semantic_golden import (
    SEMANTIC_GOLDEN_DATASET,
    CitationExpectation,
    GoldenCategory,
    Tool,
)


def test_semantic_golden_dataset_has_reviewed_phase_11_coverage() -> None:
    dataset = SEMANTIC_GOLDEN_DATASET

    assert len(dataset.cases) == 50
    assert [case.case_id for case in dataset.cases] == [
        f"SG{number:02d}" for number in range(1, 51)
    ]
    assert Counter(case.category for case in dataset.cases) == {
        GoldenCategory.QUANTITATIVE: 7,
        GoldenCategory.TREND: 6,
        GoldenCategory.COMPARISON: 7,
        GoldenCategory.EVIDENCE: 10,
        GoldenCategory.HYBRID: 6,
        GoldenCategory.FOLLOW_UP: 5,
        GoldenCategory.ABSTENTION: 5,
        GoldenCategory.REPORT: 4,
    }
    assert "tests/test_week3_golden_queries.py" in dataset.fixture_assumptions


def test_semantic_golden_cases_preserve_controlled_agent_contracts() -> None:
    cases = SEMANTIC_GOLDEN_DATASET.cases

    assert all(set(case.required_tools).issubset(case.allowed_tools) for case in cases)
    assert all(not (set(case.allowed_tools) & set(case.forbidden_tools)) for case in cases)
    assert all(
        set(case.allowed_tools) | set(case.forbidden_tools) == set(Tool)
        for case in cases
    )
    assert all(case.human_notes for case in cases)
    assert all(case.setup for case in cases)
    assert all(case.fixture_id for case in cases)
    assert all(len(case.required_tools) <= 3 for case in cases)

    evidence_cases = [case for case in cases if case.category is GoldenCategory.EVIDENCE]
    hybrid_cases = [case for case in cases if case.category is GoldenCategory.HYBRID]
    follow_up_cases = [case for case in cases if case.category is GoldenCategory.FOLLOW_UP]
    report_cases = [case for case in cases if case.category is GoldenCategory.REPORT]
    abstention_cases = [case for case in cases if case.abstention_required]

    assert all(case.required_tools == (Tool.RAG,) for case in evidence_cases)
    assert all(case.citation_expectation is CitationExpectation.REQUIRED for case in evidence_cases)
    assert all(set(case.required_tools) == {Tool.SQL, Tool.RAG} for case in hybrid_cases)
    assert all(len(case.conversation) >= 2 for case in follow_up_cases)
    assert all(Tool.REPORT in case.required_tools for case in report_cases)
    assert all(case.citation_expectation is CitationExpectation.FORBIDDEN for case in abstention_cases)
