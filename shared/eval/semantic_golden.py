"""Curated Week 4 semantic Golden dataset.

This module deliberately contains expectations, not an evaluation runner.  The
runner belongs to Phase 12.  Cases use the controlled Week 3 router fixture as
their explicit baseline so they can be reviewed without asserting unavailable
production data or brittle model prose.
"""

from __future__ import annotations

from collections import Counter
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

FIXTURE_ID = "week3_controlled_router_fixture"
FIXTURE_WEEK = 202403
FIXTURE_RANGE = (202402, 202403)
DELTA_2 = "ecoflow-delta2"
JACKERY_1000 = "jackery-explorer-1000"
JACKERY_240 = "jackery-explorer-240"
JACKERY_300 = "jackery-explorer-300"
ANKER_F2000 = "anker-solix-f2000"


class GoldenCategory(StrEnum):
    QUANTITATIVE = "quantitative"
    TREND = "trend"
    COMPARISON = "comparison"
    EVIDENCE = "evidence"
    HYBRID = "sql_rag_hybrid"
    FOLLOW_UP = "follow_up"
    ABSTENTION = "no_data_abstention_invalid"
    REPORT = "report_related"


class Tool(StrEnum):
    SQL = "tool_sql"
    RAG = "tool_rag"
    REPORT = "tool_report"


class CitationExpectation(StrEnum):
    REQUIRED = "required"
    FORBIDDEN = "forbidden"
    OPTIONAL = "optional"


class ConversationTurn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1)


class NumericExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    metric: str = Field(min_length=1)
    value: float | int
    comparison: str = Field(pattern="^(equals|at_least|at_most)$")


class ScopeExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sku_codes: tuple[str, ...] = ()
    week_ids: tuple[int, ...] = ()
    capacity_tier: str | None = None
    requires_same_tier: bool = False


class SemanticGoldenCase(BaseModel):
    """A reviewed semantic expectation that Phase 12 can execute and score."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^SG[0-9]{2}$")
    category: GoldenCategory
    question: str = Field(min_length=8)
    fixture_id: str = Field(min_length=1)
    setup: str = Field(min_length=12)
    conversation: tuple[ConversationTurn, ...] = ()
    required_tools: tuple[Tool, ...] = ()
    allowed_tools: tuple[Tool, ...] = ()
    forbidden_tools: tuple[Tool, ...] = ()
    scope: ScopeExpectation = Field(default_factory=ScopeExpectation)
    numeric_expectations: tuple[NumericExpectation, ...] = ()
    evidence_expectation: str | None = None
    abstention_required: bool = False
    citation_expectation: CitationExpectation
    answer_characteristics: tuple[str, ...] = Field(min_length=1)
    human_notes: str = Field(min_length=12)

    @model_validator(mode="after")
    def validate_expectations(self) -> SemanticGoldenCase:
        required = set(self.required_tools)
        allowed = set(self.allowed_tools)
        forbidden = set(self.forbidden_tools)
        if not required.issubset(allowed):
            raise ValueError("required_tools must be included in allowed_tools")
        if required & forbidden or allowed & forbidden:
            raise ValueError("forbidden tools must not overlap allowed tools")
        if self.category is GoldenCategory.FOLLOW_UP and len(self.conversation) < 2:
            raise ValueError("follow-up cases require visible prior conversation")
        if self.abstention_required:
            if self.citation_expectation is not CitationExpectation.FORBIDDEN:
                raise ValueError("abstention cases must forbid citations")
            if self.numeric_expectations:
                raise ValueError("abstention cases cannot require numeric output")
        if self.citation_expectation is CitationExpectation.REQUIRED and not self.evidence_expectation:
            raise ValueError("required citations need an evidence expectation")
        return self


class SemanticGoldenDataset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: str = "week4_semantic_golden_v1"
    fixture_assumptions: str
    cases: tuple[SemanticGoldenCase, ...]

    @model_validator(mode="after")
    def validate_catalog(self) -> SemanticGoldenDataset:
        if len(self.cases) != 50:
            raise ValueError("Week 4 semantic Golden dataset must contain exactly 50 cases")
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("semantic Golden case IDs must be unique")
        expected = {
            GoldenCategory.QUANTITATIVE: 7,
            GoldenCategory.TREND: 6,
            GoldenCategory.COMPARISON: 7,
            GoldenCategory.EVIDENCE: 10,
            GoldenCategory.HYBRID: 6,
            GoldenCategory.FOLLOW_UP: 5,
            GoldenCategory.ABSTENTION: 5,
            GoldenCategory.REPORT: 4,
        }
        if Counter(case.category for case in self.cases) != expected:
            raise ValueError("semantic Golden category distribution does not match Phase 11")
        return self


def _case(
    case_id: str,
    category: GoldenCategory,
    question: str,
    *,
    required: tuple[Tool, ...],
    allowed: tuple[Tool, ...],
    forbidden: tuple[Tool, ...] = (),
    skus: tuple[str, ...] = (),
    weeks: tuple[int, ...] = (),
    tier: str | None = None,
    same_tier: bool = False,
    numeric: tuple[NumericExpectation, ...] = (),
    evidence: str | None = None,
    abstain: bool = False,
    citations: CitationExpectation = CitationExpectation.FORBIDDEN,
    conversation: tuple[ConversationTurn, ...] = (),
    answer: tuple[str, ...] = ("State only supported VOC findings.",),
    notes: str = "Reviewed against the controlled Week 3 router fixture and current tool contracts.",
) -> SemanticGoldenCase:
    if not forbidden:
        forbidden = tuple(tool for tool in Tool if tool not in allowed)
    return SemanticGoldenCase(
        case_id=case_id,
        category=category,
        question=question,
        fixture_id=FIXTURE_ID,
        setup=(
            "Use the deterministic router fixture in tests/test_week3_golden_queries.py; "
            "do not infer facts from external product knowledge."
        ),
        conversation=conversation,
        required_tools=required,
        allowed_tools=allowed,
        forbidden_tools=forbidden,
        scope=ScopeExpectation(
            sku_codes=skus,
            week_ids=weeks,
            capacity_tier=tier,
            requires_same_tier=same_tier,
        ),
        numeric_expectations=numeric,
        evidence_expectation=evidence,
        abstention_required=abstain,
        citation_expectation=citations,
        answer_characteristics=answer,
        human_notes=notes,
    )


N12 = NumericExpectation(metric="negative_mentions", value=12, comparison="equals")
R8 = NumericExpectation(metric="review_count", value=8, comparison="equals")
NOISE7 = NumericExpectation(metric="noise_mentions", value=7, comparison="equals")
CHARGING5 = NumericExpectation(metric="charging_mentions", value=5, comparison="equals")
NEG_50 = NumericExpectation(metric="delta2_negative_rate", value=0.5, comparison="equals")
JACKERY_NEG_25 = NumericExpectation(metric="jackery1000_negative_rate", value=0.25, comparison="equals")

PRIOR_COMPARISON = (
    ConversationTurn(role="user", content="Compare Delta 2 and Jackery Explorer 1000."),
    ConversationTurn(role="assistant", content="I can compare those same-tier SKUs with VOC data."),
)
PRIOR_NOISE = PRIOR_COMPARISON + (
    ConversationTurn(role="user", content="Focus on noise."),
    ConversationTurn(role="assistant", content="Noise is the current visible comparison topic."),
)
PRIOR_DELTA = (
    ConversationTurn(role="user", content="Tell me about Delta 2 complaints."),
    ConversationTurn(role="assistant", content="I will use only retrieved VOC evidence and deterministic metrics."),
)


CASES = (
    # Seven deterministic quantitative cases.
    _case("SG01", GoldenCategory.QUANTITATIVE, "How many negative Delta 2 mentions are in fixture week 202403?", required=(Tool.SQL,), allowed=(Tool.SQL,), skus=(DELTA_2,), weeks=(FIXTURE_WEEK,), numeric=(N12, R8), answer=("Report the exact count and review denominator.",)),
    _case("SG02", GoldenCategory.QUANTITATIVE, "What is the complaint-aspect breakdown for Delta 2 in fixture week 202403?", required=(Tool.SQL,), allowed=(Tool.SQL,), skus=(DELTA_2,), weeks=(FIXTURE_WEEK,), numeric=(NOISE7, CHARGING5), answer=("Name noise and charging with their exact counts.",)),
    _case("SG03", GoldenCategory.QUANTITATIVE, "Give the Delta 2 sentiment distribution for fixture week 202403.", required=(Tool.SQL,), allowed=(Tool.SQL,), skus=(DELTA_2,), weeks=(FIXTURE_WEEK,), numeric=(N12,), answer=("Use deterministic distribution values without retrieved quotes.",)),
    _case("SG04", GoldenCategory.QUANTITATIVE, "How many reviews and mentions match negative charging feedback for Delta 2?", required=(Tool.SQL,), allowed=(Tool.SQL,), skus=(DELTA_2,), numeric=(CHARGING5,), answer=("Keep review and mention measures distinct.",)),
    _case("SG05", GoldenCategory.QUANTITATIVE, "Which negative aspect has the most Delta 2 mentions in the fixture?", required=(Tool.SQL,), allowed=(Tool.SQL,), skus=(DELTA_2,), numeric=(NOISE7,), answer=("Identify noise as the leading fixture aspect.",)),
    _case("SG06", GoldenCategory.QUANTITATIVE, "Count all Delta 2 VOC mentions in fixture week 202403.", required=(Tool.SQL,), allowed=(Tool.SQL,), skus=(DELTA_2,), weeks=(FIXTURE_WEEK,), numeric=(N12,), answer=("Return the deterministic count; do not add an unsupported cause.",)),
    _case("SG07", GoldenCategory.QUANTITATIVE, "What is the exact negative rate for Delta 2 in the fixture comparison?", required=(Tool.SQL,), allowed=(Tool.SQL,), skus=(DELTA_2, JACKERY_1000), tier="mid", same_tier=True, numeric=(NEG_50,), answer=("Use the comparison metric without declaring a product winner.",)),
    # Six trend cases.
    _case("SG08", GoldenCategory.TREND, "How did Delta 2 negative sentiment change from 202402 to 202403?", required=(Tool.SQL,), allowed=(Tool.SQL,), skus=(DELTA_2,), weeks=FIXTURE_RANGE, numeric=(NEG_50,), answer=("Describe the deterministic change from 25% to 50%.",)),
    _case("SG09", GoldenCategory.TREND, "Show the Delta 2 noise trend across the fixture weeks.", required=(Tool.SQL,), allowed=(Tool.SQL,), skus=(DELTA_2,), weeks=FIXTURE_RANGE, answer=("Use aspect_trend and preserve weekly ordering.",)),
    _case("SG10", GoldenCategory.TREND, "Did Delta 2 negativity improve or worsen over the two fixture weeks?", required=(Tool.SQL,), allowed=(Tool.SQL,), skus=(DELTA_2,), weeks=FIXTURE_RANGE, answer=("Say it worsened only because the calculated rate increased.",)),
    _case("SG11", GoldenCategory.TREND, "Compare the weekly negative rates for Delta 2 over 202402 and 202403.", required=(Tool.SQL,), allowed=(Tool.SQL,), skus=(DELTA_2,), weeks=FIXTURE_RANGE, answer=("Include both time points and their rates.",)),
    _case("SG12", GoldenCategory.TREND, "What is the historical trend for Delta 2 charging feedback?", required=(Tool.SQL,), allowed=(Tool.SQL,), skus=(DELTA_2,), weeks=FIXTURE_RANGE, answer=("Use the approved aspect trend rather than semantic retrieval.",)),
    _case("SG13", GoldenCategory.TREND, "Was the latest fixture week higher in negative sentiment than the prior week for Delta 2?", required=(Tool.SQL,), allowed=(Tool.SQL,), skus=(DELTA_2,), weeks=FIXTURE_RANGE, answer=("Answer yes with deterministic support and no causal speculation.",)),
    # Seven comparison cases, including a server-side invalid comparison.
    _case("SG14", GoldenCategory.COMPARISON, "Compare Delta 2 and Jackery Explorer 1000 sentiment in the fixture.", required=(Tool.SQL,), allowed=(Tool.SQL,), skus=(DELTA_2, JACKERY_1000), tier="mid", same_tier=True, numeric=(NEG_50, JACKERY_NEG_25), answer=("Compare same-tier metrics neutrally and disclose sample warnings.",)),
    _case("SG15", GoldenCategory.COMPARISON, "Compare Delta 2 and Jackery Explorer 1000 on negative-rate feedback.", required=(Tool.SQL,), allowed=(Tool.SQL,), skus=(DELTA_2, JACKERY_1000), tier="mid", same_tier=True, numeric=(NEG_50, JACKERY_NEG_25), answer=("Do not call either SKU a winner.",)),
    _case("SG16", GoldenCategory.COMPARISON, "How do Delta 2 and Jackery Explorer 1000 compare on noise feedback?", required=(Tool.SQL,), allowed=(Tool.SQL,), skus=(DELTA_2, JACKERY_1000), tier="mid", same_tier=True, answer=("Use a same-tier aspect comparison with no quotation.",)),
    _case("SG17", GoldenCategory.COMPARISON, "Compare Delta 2 directly with Anker Solix F2000.", required=(Tool.SQL,), allowed=(Tool.SQL,), skus=(DELTA_2, ANKER_F2000), answer=("Explain the capacity-tier constraint and avoid a product verdict.",), notes="Reviewed invalid comparison: Delta 2 is mid-tier and F2000 is large-tier; server enforcement is required."),
    _case("SG18", GoldenCategory.COMPARISON, "Can I compare Jackery Explorer 240 and Explorer 300 as direct competitors?", required=(Tool.SQL,), allowed=(Tool.SQL,), skus=(JACKERY_240, JACKERY_300), tier="entry", same_tier=True, answer=("Allow only if both enabled SKU metadata confirms the entry tier.",)),
    _case("SG19", GoldenCategory.COMPARISON, "Compare the number of negative mentions for the two mid-tier fixture SKUs.", required=(Tool.SQL,), allowed=(Tool.SQL,), skus=(DELTA_2, JACKERY_1000), tier="mid", same_tier=True, answer=("Use mention-count comparison and retain low-sample disclosure.",)),
    _case("SG20", GoldenCategory.COMPARISON, "Which SKU has less negative feedback, Delta 2 or Jackery Explorer 1000?", required=(Tool.SQL,), allowed=(Tool.SQL,), skus=(DELTA_2, JACKERY_1000), tier="mid", same_tier=True, numeric=(NEG_50, JACKERY_NEG_25), answer=("State the observed metric, caveat the fixture sample, and avoid broad superiority claims.",)),
    # Ten evidence/RAG cases.
    _case("SG21", GoldenCategory.EVIDENCE, "Show actual Delta 2 fan-noise complaints.", required=(Tool.RAG,), allowed=(Tool.RAG,), skus=(DELTA_2,), evidence="Retrieve a negative noise_level mention whose exact review excerpt is traceable.", citations=CitationExpectation.REQUIRED, answer=("Use a retrieved exact example with its citation.",)),
    _case("SG22", GoldenCategory.EVIDENCE, "Give me an exact customer comment about negative Delta 2 charging.", required=(Tool.RAG,), allowed=(Tool.RAG,), skus=(DELTA_2,), evidence="Retrieve negative charging_experience evidence.", citations=CitationExpectation.REQUIRED, answer=("Quote only retrieved wording and cite it.",)),
    _case("SG23", GoldenCategory.EVIDENCE, "What words do users use about Delta 2 noise issues?", required=(Tool.RAG,), allowed=(Tool.RAG,), skus=(DELTA_2,), evidence="Retrieve traceable noise evidence, not general product knowledge.", citations=CitationExpectation.REQUIRED, answer=("Present a grounded excerpt and citation.",)),
    _case("SG24", GoldenCategory.EVIDENCE, "Find a representative Delta 2 complaint in fixture week 202403.", required=(Tool.RAG,), allowed=(Tool.RAG,), skus=(DELTA_2,), weeks=(FIXTURE_WEEK,), evidence="Retrieved evidence must belong to the requested week.", citations=CitationExpectation.REQUIRED, answer=("Cite only a hydrated, scope-matching mention.",)),
    _case("SG25", GoldenCategory.EVIDENCE, "Show a negative Delta 2 noise review, not a summary.", required=(Tool.RAG,), allowed=(Tool.RAG,), skus=(DELTA_2,), evidence="The source mention must be negative and noise_level.", citations=CitationExpectation.REQUIRED, answer=("Do not substitute an aggregate for evidence.",)),
    _case("SG26", GoldenCategory.EVIDENCE, "Find feedback about Jackery Explorer 1000 noise.", required=(Tool.RAG,), allowed=(Tool.RAG,), skus=(JACKERY_1000,), evidence="Retrieve only Jackery Explorer 1000 evidence.", citations=CitationExpectation.REQUIRED, answer=("Keep SKU filtering intact and cite any quoted evidence.",)),
    _case("SG27", GoldenCategory.EVIDENCE, "Give me a positive customer example for Delta 2.", required=(Tool.RAG,), allowed=(Tool.RAG,), skus=(DELTA_2,), evidence="Use only a positive hydrated mention if one is returned.", citations=CitationExpectation.REQUIRED, answer=("Do not invent praise if retrieval is empty.",)),
    _case("SG28", GoldenCategory.EVIDENCE, "Retrieve a customer example related to Delta 2 charging experience.", required=(Tool.RAG,), allowed=(Tool.RAG,), skus=(DELTA_2,), evidence="Apply the enrichment taxonomy charging_experience.", citations=CitationExpectation.REQUIRED, answer=("Cite the selected evidence only.",)),
    _case("SG29", GoldenCategory.EVIDENCE, "What did customers say about the loud fan under load?", required=(Tool.RAG,), allowed=(Tool.RAG,), skus=(DELTA_2,), evidence="Expected fixture phrase is the exact loud-fan evidence, if returned.", citations=CitationExpectation.REQUIRED, answer=("Preserve exact-evidence citation discipline.",)),
    _case("SG30", GoldenCategory.EVIDENCE, "Show two traceable Delta 2 complaints from the fixture.", required=(Tool.RAG,), allowed=(Tool.RAG,), skus=(DELTA_2,), evidence="Retrieve up to two quality-qualified complaints with document provenance.", citations=CitationExpectation.REQUIRED, answer=("Cite every exact example actually used.",)),
    # Six SQL + RAG hybrid cases.
    _case("SG31", GoldenCategory.HYBRID, "What are Delta 2's main complaints in fixture week 202403, with an example?", required=(Tool.SQL, Tool.RAG), allowed=(Tool.SQL, Tool.RAG), skus=(DELTA_2,), weeks=(FIXTURE_WEEK,), numeric=(NOISE7,), evidence="Provide a representative retrieved complaint for the calculated leading aspect.", citations=CitationExpectation.REQUIRED, answer=("Separate deterministic counts from cited qualitative evidence.",)),
    _case("SG32", GoldenCategory.HYBRID, "Why did Delta 2 negativity rise in the fixture? Include a customer example.", required=(Tool.SQL, Tool.RAG), allowed=(Tool.SQL, Tool.RAG), skus=(DELTA_2,), weeks=FIXTURE_RANGE, evidence="Evidence may illustrate feedback but must not prove an unsupported causal claim.", citations=CitationExpectation.REQUIRED, answer=("Describe the calculated change; qualify any explanation as evidence, not certainty.",)),
    _case("SG33", GoldenCategory.HYBRID, "Which Delta 2 complaint category is most common and what does a review say?", required=(Tool.SQL, Tool.RAG), allowed=(Tool.SQL, Tool.RAG), skus=(DELTA_2,), numeric=(NOISE7,), evidence="Retrieve evidence for the leading noise aspect.", citations=CitationExpectation.REQUIRED, answer=("Return the exact deterministic leader plus a cited example.",)),
    _case("SG34", GoldenCategory.HYBRID, "Compare Delta 2 and Jackery 1000 noise metrics and show one customer example.", required=(Tool.SQL, Tool.RAG), allowed=(Tool.SQL, Tool.RAG), skus=(DELTA_2, JACKERY_1000), tier="mid", same_tier=True, evidence="Retrieved example must come from one of the explicit comparison SKUs.", citations=CitationExpectation.REQUIRED, answer=("Keep the metric comparison neutral and cite the example.",)),
    _case("SG35", GoldenCategory.HYBRID, "How many negative Delta 2 mentions are there, and show a supporting complaint.", required=(Tool.SQL, Tool.RAG), allowed=(Tool.SQL, Tool.RAG), skus=(DELTA_2,), numeric=(N12,), evidence="Retrieve a negative Delta 2 complaint.", citations=CitationExpectation.REQUIRED, answer=("Do not use the quote as the source of the count.",)),
    _case("SG36", GoldenCategory.HYBRID, "Summarize fixture-week Delta 2 negative feedback with counts and one citation.", required=(Tool.SQL, Tool.RAG), allowed=(Tool.SQL, Tool.RAG), skus=(DELTA_2,), weeks=(FIXTURE_WEEK,), numeric=(N12, NOISE7), evidence="Use a week-scoped negative evidence record.", citations=CitationExpectation.REQUIRED, answer=("Include only supported metrics and used citations.",)),
    # Five recent-N follow-up cases.
    _case("SG37", GoldenCategory.FOLLOW_UP, "What about noise specifically?", required=(Tool.SQL,), allowed=(Tool.SQL,), skus=(DELTA_2, JACKERY_1000), tier="mid", same_tier=True, conversation=PRIOR_COMPARISON, answer=("Resolve both SKU references from visible history.",), notes="Follow-up must use only the supplied recent conversation; no hidden comparison state is permitted."),
    _case("SG38", GoldenCategory.FOLLOW_UP, "Show actual comments.", required=(Tool.RAG,), allowed=(Tool.RAG,), skus=(DELTA_2, JACKERY_1000), tier="mid", same_tier=True, conversation=PRIOR_NOISE, evidence="Retrieve evidence for the visible noise comparison topic.", citations=CitationExpectation.REQUIRED, answer=("Cite only the selected retrieved comment.",), notes="Follow-up depends on visible SKU and topic turns, not browser-only state."),
    _case("SG39", GoldenCategory.FOLLOW_UP, "How many were negative?", required=(Tool.SQL,), allowed=(Tool.SQL,), skus=(DELTA_2,), conversation=PRIOR_DELTA, numeric=(N12,), answer=("Resolve Delta 2 from prior user-visible context.",), notes="Recent-N context must preserve the prior SKU reference."),
    _case("SG40", GoldenCategory.FOLLOW_UP, "Can you give me the source for that?", required=(Tool.RAG,), allowed=(Tool.RAG,), skus=(DELTA_2,), conversation=PRIOR_DELTA, evidence="Retrieve a source rather than fabricate a citation for an uncited prior claim.", citations=CitationExpectation.REQUIRED, answer=("Provide newly retrieved, traceable evidence.",), notes="The system persists compact metadata only, so the follow-up must re-retrieve evidence."),
    _case("SG41", GoldenCategory.FOLLOW_UP, "Compare the trend instead.", required=(Tool.SQL,), allowed=(Tool.SQL,), skus=(DELTA_2, JACKERY_1000), tier="mid", same_tier=True, conversation=PRIOR_COMPARISON, answer=("Use explicit visible SKUs and a deterministic trend request.",), notes="No active SKU/week/aspect state may be inferred beyond visible recent messages."),
    # Five no-data, abstention, or invalid requests.
    _case("SG42", GoldenCategory.ABSTENTION, "Show Delta 2 complaints about an unsupported fixture issue in week 202403.", required=(Tool.RAG,), allowed=(Tool.RAG,), skus=(DELTA_2,), weeks=(FIXTURE_WEEK,), abstain=True, answer=("Abstain instead of using product prior knowledge.",), notes="Controlled fixture has no matching evidence for this request."),
    _case("SG43", GoldenCategory.ABSTENTION, "Find positive quiet-operation evidence for Delta 2 in fixture week 202403.", required=(Tool.RAG,), allowed=(Tool.RAG,), skus=(DELTA_2,), weeks=(FIXTURE_WEEK,), abstain=True, answer=("Return the standard no-data abstention without citations.",), notes="Strict positive noise filters intentionally produce no fixture evidence."),
    _case("SG44", GoldenCategory.ABSTENTION, "Give me data for an unknown power station SKU.", required=(Tool.SQL,), allowed=(Tool.SQL,), answer=("Surface the safe invalid-SKU outcome and make no product claims.",), notes="Unknown or disabled SKUs are rejected before deterministic queries."),
    _case("SG45", GoldenCategory.ABSTENTION, "Find Delta 2 evidence for ISO week 202453.", required=(Tool.RAG,), allowed=(Tool.RAG,), skus=(DELTA_2,), weeks=(202453,), abstain=True, answer=("Reject the invalid ISO week safely and do not search.",), notes="Week 202453 is invalid and must fail validation before external calls."),
    _case("SG46", GoldenCategory.ABSTENTION, "Compare Delta 2 with Anker F2000 and choose the winner.", required=(Tool.SQL,), allowed=(Tool.SQL,), skus=(DELTA_2, ANKER_F2000), answer=("Reject the cross-tier request and never name a winner.",), notes="Cross-tier comparison is an application-enforced constraint, not an LLM preference."),
    # Four stored-report cases. Generation remains outside the Agent tool boundary.
    _case("SG47", GoldenCategory.REPORT, "Show the stored Delta 2 weekly report for fixture week 202403.", required=(Tool.REPORT,), allowed=(Tool.REPORT,), skus=(DELTA_2,), weeks=(FIXTURE_WEEK,), answer=("Return stored report content verbatim when it exists.",), notes="tool_report is read-only and must not regenerate or synthesize a replacement."),
    _case("SG48", GoldenCategory.REPORT, "Summarize Delta 2 fixture week 202403 when the stored report is missing.", required=(Tool.REPORT, Tool.SQL), allowed=(Tool.REPORT, Tool.SQL, Tool.RAG), skus=(DELTA_2,), weeks=(FIXTURE_WEEK,), numeric=(N12,), answer=("Disclose the missing report and use supported analytics fallback only.",), notes="A report miss may be followed by Router-selected deterministic analytics; it never creates a report."),
    _case("SG49", GoldenCategory.REPORT, "Is there a stored report for Delta 2 in invalid week 202453?", required=(Tool.REPORT,), allowed=(Tool.REPORT,), skus=(DELTA_2,), weeks=(202453,), answer=("Return the safe invalid-week result; do not generate a report.",), notes="Stored report lookup validates ISO week before repository access."),
    _case("SG50", GoldenCategory.REPORT, "Give me a cited customer quote from the stored weekly report.", required=(Tool.REPORT,), allowed=(Tool.REPORT,), skus=(DELTA_2,), weeks=(FIXTURE_WEEK,), answer=("Explain that stored reports have no durable report-to-mention citation mapping.",), notes="Report-level interactive citations must not be invented without a reviewed persistence contract."),
)


SEMANTIC_GOLDEN_DATASET = SemanticGoldenDataset(
    fixture_assumptions=(
        "All cases are reviewed against the controlled Week 3 router fixture in "
        "tests/test_week3_golden_queries.py (fixture weeks 202402-202403, Delta 2, "
        "Jackery Explorer 1000, and its explicit deterministic metrics/evidence). "
        "They are a semantic benchmark specification, not a claim about live production "
        "inventory. A Phase 12 runner must provision equivalent fixtures or mark an "
        "incompatible live-data case as infrastructure-invalid rather than scoring it."
    ),
    cases=CASES,
)
