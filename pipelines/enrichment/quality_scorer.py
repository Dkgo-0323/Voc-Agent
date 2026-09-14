"""Deterministic quality scoring for extracted aspect mentions."""

import re
from dataclasses import dataclass

W_SPECIFICITY = 0.35
W_CONFIDENCE = 0.30
W_LENGTH = 0.20
W_SOURCE = 0.15

CORE_PERFORMANCE_ASPECTS = {
    "battery_capacity",
    "charging_speed",
    "solar_charging",
    "ac_output_power",
    "output_ports",
}
GENERIC_TERMS = {
    "great",
    "good",
    "bad",
    "awesome",
    "excellent",
    "terrible",
    "love",
    "hate",
}
GENERIC_PHRASE_PATTERN = re.compile(
    r"^(?:(?:a\s+)?(?:great|good|awesome|excellent|nice)(?:\s+product)?|"
    r"(?:i\s+)?love\s+it|so\s+far[, ]+so\s+good|"
    r"(?:i(?:'m| am)\s+)?happy\s+with\s+(?:it|the\s+purchase)|"
    r"(?:it\s+)?works?\s+(?:very\s+)?well|"
    r"(?:i(?:'ve| have)?\s+)?used\s+(?:it\s+)?(?:a\s+)?few\s+times|"
    r"(?:this|it)\s+feels\s+like\s+a\s+quality\s+unit)$",
    re.I,
)
COMPARISON_PATTERN = re.compile(
    r"\b(better|worse|than|faster|slower|more|less)\b", re.I
)
NUMBER_PATTERN = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:w|wh|hours?|hrs?|minutes?|mins?|%)?\b", re.I
)


@dataclass(frozen=True)
class QualityScore:
    score: float
    specificity: float
    confidence: float
    length: float
    source: float


def specificity_score(mention_text: str, aspect_label: str) -> float:
    text = mention_text.strip()
    normalized = text.lower().strip(".!? ,")
    if GENERIC_PHRASE_PATTERN.fullmatch(normalized):
        return 0.0
    score = 0.0
    if NUMBER_PATTERN.search(text):
        score += 0.3
    if COMPARISON_PATTERN.search(text):
        score += 0.2
    if normalized not in GENERIC_TERMS:
        score += 0.2
    if aspect_label in CORE_PERFORMANCE_ASPECTS:
        score += 0.2
    if 20 <= len(text) <= 60:
        score += 0.1
    return min(score, 1.0)


def length_score(mention_text: str, context_window: str | None) -> float:
    total_length = len(mention_text) + len(context_window or "")
    if total_length < 50:
        return 0.3
    if total_length <= 300:
        return 1.0
    return 0.6


def source_weight(
    platform: str, rating: int | None = None, source_score: int | None = None
) -> float:
    if platform.lower() == "amazon":
        return 0.9 if rating is not None else 0.7
    if platform.lower() == "reddit":
        return 0.8 if source_score is not None and source_score > 10 else 0.6
    return 0.5


def score_quality(
    *,
    mention_text: str,
    context_window: str | None,
    aspect_label: str,
    sentiment: str,
    confidence: float,
    platform: str,
    rating: int | None = None,
    source_score: int | None = None,
) -> QualityScore:
    """Calculate a normalized score and apply Amazon rating consistency rules."""
    adjusted_confidence = max(0.0, min(confidence, 1.0))
    if (
        platform.lower() == "amazon"
        and rating is not None
        and rating >= 4
        and sentiment == "negative"
    ):
        adjusted_confidence *= 0.7

    specificity = specificity_score(mention_text, aspect_label)
    length = length_score(mention_text, context_window)
    source = source_weight(platform, rating, source_score)
    score = (
        W_SPECIFICITY * specificity
        + W_CONFIDENCE * adjusted_confidence
        + W_LENGTH * length
        + W_SOURCE * source
    )
    if GENERIC_PHRASE_PATTERN.fullmatch(mention_text.lower().strip(".!? ,")):
        score = min(score, 0.35)
    return QualityScore(
        score=round(min(score, 1.0), 4),
        specificity=specificity,
        confidence=adjusted_confidence,
        length=length,
        source=source,
    )
