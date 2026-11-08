"""Conservative source checks; uncertain attribution is not usable evidence."""

import re


def sentiment_label_conflict(sentiment: str, text: str) -> bool:
    """Flag explicit criticism stored as positive, without guessing a new label."""
    return sentiment == "positive" and bool(
        re.search(
            r"\bneeds (?:some )?(?:refinement|improvement)\b|\bwill have trouble\b|\bdoes not match\b",
            text,
            re.I,
        )
    )


def source_model_conflict(sku_code: str, review_text: str) -> bool:
    # DELTA Max/Pro are distinct products. A catalog join alone cannot prove
    # which device a mixed/incorrectly attached customer review describes.
    return sku_code == "ecoflow-delta2" and bool(
        re.search(r"\bdelta\s*(?:max|pro|mini)\b|\briver\s*\d", review_text, re.I)
    )


def complete_context(review_text: str, mention_text: str) -> str:
    position = review_text.find(mention_text)
    if position < 0:
        return mention_text
    start = max(0, position - 160)
    end = min(len(review_text), position + len(mention_text) + 400)
    while start > 0 and not review_text[start - 1].isspace():
        start -= 1
    while end < len(review_text) and not review_text[end].isspace():
        end += 1
    return review_text[start:end]
