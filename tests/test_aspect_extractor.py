from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.app.db.repositories.schemas import DocumentRead
from pipelines.enrichment.aspect_extractor import (
    AspectExtractor,
    build_aspect_mentions,
    detect_english,
    prepare_document,
)


def make_document(body: str) -> DocumentRead:
    return DocumentRead(
        id=uuid4(), sku_id=uuid4(), sku_code="ecoflow-delta2", platform="amazon", external_id="review-1",
        title=None, body=body, rating=5, author_hash=None, source_url=None,
        published_at=None, week_id=202632, ingested_at=datetime.now(),
        processing_status="raw", processing_error=None, processed_at=None,
    )


class FakeCompletions:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))])


class FakeClient:
    def __init__(self, content: str) -> None:
        self.chat = SimpleNamespace(completions=FakeCompletions(content))


def test_prepare_document_filters_shipping_only_review() -> None:
    document = make_document("The package arrived late and shipping was terrible today.")
    assert prepare_document(document, language_detector=lambda _: True) is None


def test_default_language_detector_accepts_english() -> None:
    assert detect_english("The battery charges quickly and the fan is quiet.")


def test_prepare_document_caps_long_review_at_sentence() -> None:
    document = make_document("The battery works very well. " * 200)
    prepared = prepare_document(document, language_detector=lambda _: True)
    assert prepared is not None
    assert len(prepared.body) <= 2000


@pytest.mark.asyncio
async def test_extracts_valid_structured_aspect() -> None:
    body = "I use it in my bedroom. The fan is extremely loud and turns on unpredictably."
    document = make_document(body)
    response = (
        '{"documents":[{"document_id":"' + str(document.id) +
        '","aspects":[{"aspect_label":"noise_level","sentiment":"negative",'
        '"confidence":0.92,"mention_text":"fan is extremely loud",'
        '"context_window":"The fan is extremely loud and turns on unpredictably."}]}]}'
    )
    client = FakeClient(response)
    extractor = AspectExtractor(client, language_detector=lambda _: True)
    result = await extractor.extract([document])
    assert result.skipped_document_ids == []
    assert result.documents[0].aspects[0].aspect_label == "noise_level"
    assert client.chat.completions.calls == 1
    mentions = build_aspect_mentions([document], result)
    assert mentions[0].sku_code == "ecoflow-delta2"
    assert mentions[0].quality_score is not None
