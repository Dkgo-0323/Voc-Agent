from pipelines.enrichment.quality_scorer import score_quality


def test_specific_mention_scores_higher_than_generic_mention() -> None:
    specific = score_quality(
        mention_text="It charged from 20% to full in 2 hours.",
        context_window="A detailed charging test from my first camping trip.",
        aspect_label="charging_speed",
        sentiment="positive",
        confidence=0.9,
        platform="amazon",
        rating=5,
    )
    generic = score_quality(
        mention_text="great",
        context_window=None,
        aspect_label="camping_outdoor_use",
        sentiment="positive",
        confidence=0.9,
        platform="amazon",
        rating=5,
    )
    assert specific.score > generic.score
    assert 0 <= specific.score <= 1


def test_high_rating_reduces_confidence_for_negative_mention() -> None:
    result = score_quality(
        mention_text="The fan is loud after 10 minutes of charging.",
        context_window="I still like the station overall, but the fan is loud.",
        aspect_label="noise_level",
        sentiment="negative",
        confidence=0.9,
        platform="amazon",
        rating=4,
    )
    assert result.confidence == 0.63


def test_high_llm_confidence_cannot_rescue_generic_praise() -> None:
    result = score_quality(
        mention_text="So far so good",
        context_window="So far so good after three weeks.",
        aspect_label="customer_service",
        sentiment="positive",
        confidence=1.0,
        platform="amazon",
        rating=5,
    )

    assert result.specificity == 0
    assert result.score <= 0.35
