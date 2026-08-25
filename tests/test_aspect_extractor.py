import json
import logging
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from openai import RateLimitError

from backend.app.db.repositories.schemas import DocumentRead
from pipelines.enrichment.aspect_extractor import (
    AspectExtractor,
    ExtractionResponseError,
    PreparedDocument,
    build_aspect_mentions,
    detect_english,
    prepare_document,
)
from pipelines.enrichment.prompts import SYSTEM_PROMPT


def make_document(body: str) -> DocumentRead:
    return DocumentRead(
        id=uuid4(),
        sku_id=uuid4(),
        sku_code="ecoflow-delta2",
        sku_name="EcoFlow DELTA 2",
        platform="amazon",
        external_id="review-1",
        title=None,
        body=body,
        rating=5,
        author_hash=None,
        source_url=None,
        published_at=None,
        week_id=202632,
        ingested_at=datetime.now(),
        processing_status="raw",
        processing_error=None,
        processed_at=None,
    )


class FakeCompletions:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = 0
        self.last_kwargs = None

    async def create(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
        )


class FakeClient:
    def __init__(self, content: str) -> None:
        self.chat = SimpleNamespace(completions=FakeCompletions(content))


def test_prepare_document_filters_shipping_only_review() -> None:
    document = make_document(
        "The package arrived late and shipping was terrible today."
    )
    assert prepare_document(document, language_detector=lambda _: True) is None


def test_default_language_detector_accepts_english() -> None:
    assert detect_english("The battery charges quickly and the fan is quiet.")


def test_prepare_document_caps_long_review_at_sentence() -> None:
    document = make_document("The battery works very well. " * 200)
    prepared = prepare_document(document, language_detector=lambda _: True)
    assert prepared is not None
    assert len(prepared.body) <= 2000


def test_runtime_prompt_requires_empty_results_and_exact_evidence() -> None:
    assert "return an empty aspects list" in SYSTEM_PROMPT
    assert "exact contiguous substring" in SYSTEM_PROMPT
    assert "customer_service requires explicit" in SYSTEM_PROMPT
    assert "solar_charging requires explicit" in SYSTEM_PROMPT
    assert "build_quality requires specific evidence" in SYSTEM_PROMPT


def test_case_changed_excerpt_is_rejected() -> None:
    document = PreparedDocument(
        document_id=uuid4(), body="The Fan is extremely loud at night."
    )
    payload = {
        "documents": [
            {
                "document_id": str(document.document_id),
                "aspects": [
                    {
                        "aspect_label": "noise_level",
                        "sentiment": "negative",
                        "confidence": 0.9,
                        "mention_text": "fan is extremely loud",
                    }
                ],
            }
        ]
    }

    documents, failures = AspectExtractor._validate_payload(payload, [document])

    assert documents[0].aspects == []
    assert document.document_id in failures


@pytest.mark.asyncio
async def test_extracts_valid_structured_aspect() -> None:
    body = (
        "I use it in my bedroom. The fan is extremely loud and turns on unpredictably."
    )
    document = make_document(body)
    response = (
        '{"documents":[{"document_id":"'
        + str(document.id)
        + '","aspects":[{"aspect_label":"noise_level","sentiment":"negative",'
        '"confidence":0.92,"mention_text":"fan is extremely loud",'
        '"context_window":"The fan is extremely loud and turns on unpredictably."}]}]}'
    )
    client = FakeClient(response)
    extractor = AspectExtractor(
        client,
        model="glm-4.7-flash",
        language_detector=lambda _: True,
        request_extra_body={"thinking": {"type": "disabled"}},
    )
    result = await extractor.extract([document])
    assert result.skipped_document_ids == []
    assert result.documents[0].aspects[0].aspect_label == "noise_level"
    assert client.chat.completions.calls == 1
    assert client.chat.completions.last_kwargs["model"] == "glm-4.7-flash"
    assert client.chat.completions.last_kwargs["max_tokens"] == 4096
    assert client.chat.completions.last_kwargs["response_format"] == {
        "type": "json_object"
    }
    assert client.chat.completions.last_kwargs["extra_body"] == {
        "thinking": {"type": "disabled"}
    }
    mentions = build_aspect_mentions([document], result)
    assert mentions[0].sku_code == "ecoflow-delta2"
    assert mentions[0].quality_score is not None


@pytest.mark.asyncio
async def test_transient_rate_limit_is_retried() -> None:
    body = "The battery lasted eight hours and the charging fan was loud."
    document = make_document(body)
    content = '{"documents":[{"document_id":"' + str(document.id) + '","aspects":[]}]}'

    class RateLimitedCompletions(FakeCompletions):
        async def create(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                request = httpx.Request("POST", "https://example.test/chat/completions")
                response = httpx.Response(429, request=request)
                raise RateLimitError("busy", response=response, body={})
            self.last_kwargs = kwargs
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
            )

    async def no_sleep(_: float) -> None:
        return None

    client = FakeClient(content)
    client.chat.completions = RateLimitedCompletions(content)
    extractor = AspectExtractor(
        client,
        language_detector=lambda _: True,
        sleep=no_sleep,
    )

    result = await extractor.extract([document])

    assert result.documents[0].aspects == []
    assert client.chat.completions.calls == 2


@pytest.mark.asyncio
async def test_invalid_mention_is_discarded_without_failing_batch(caplog) -> None:
    first = make_document("The fan is loud, but the battery lasted eight hours.")
    second = make_document("Charging takes two hours and works reliably every day.")
    response = (
        '{"documents":['
        f'{{"document_id":"{first.id}","aspects":['
        '{"aspect_label":"noise_level","sentiment":"negative",'
        '"confidence":0.9,"mention_text":"fan is loud","context_window":null},'
        '{"aspect_label":"battery_capacity","sentiment":"positive",'
        '"confidence":0.9,"mention_text":"lasted nine hours",'
        '"context_window":null}]},'
        f'{{"document_id":"{second.id}","aspects":['
        '{"aspect_label":"charging_speed","sentiment":"positive",'
        '"confidence":0.9,"mention_text":"Charging takes two hours",'
        '"context_window":null}]}]}'
    )
    client = FakeClient(response)
    extractor = AspectExtractor(client, language_detector=lambda _: True)

    with caplog.at_level(logging.WARNING):
        result = await extractor.extract([first, second])

    assert client.chat.completions.calls == 1
    assert result.failed_document_errors == {}
    assert [aspect.mention_text for aspect in result.documents[0].aspects] == [
        "fan is loud"
    ]
    assert [aspect.mention_text for aspect in result.documents[1].aspects] == [
        "Charging takes two hours"
    ]
    event = json.loads(
        next(
            record.message
            for record in caplog.records
            if "aspect_mentions_discarded" in record.message
        )
    )
    assert event["document_id"] == str(first.id)
    assert event["discarded_count"] == 1
    assert "lasted nine hours" not in caplog.text
    assert first.body not in caplog.text


@pytest.mark.asyncio
async def test_document_with_only_invalid_mentions_is_isolated() -> None:
    invalid = make_document("The fan is loud throughout the entire night.")
    valid = make_document("The battery lasted eight hours during the outage.")
    response = (
        '{"documents":['
        f'{{"document_id":"{invalid.id}","aspects":['
        '{"aspect_label":"noise_level","sentiment":"negative",'
        '"confidence":0.9,"mention_text":"fan is silent",'
        '"context_window":null}]},'
        f'{{"document_id":"{valid.id}","aspects":['
        '{"aspect_label":"battery_capacity","sentiment":"positive",'
        '"confidence":0.9,"mention_text":"battery lasted eight hours",'
        '"context_window":null}]}]}'
    )
    extractor = AspectExtractor(FakeClient(response), language_detector=lambda _: True)

    result = await extractor.extract([invalid, valid])

    assert invalid.id in result.failed_document_errors
    assert result.documents[0].aspects == []
    assert len(result.documents[1].aspects) == 1


@pytest.mark.parametrize("violation", ["unknown", "duplicate", "missing"])
def test_document_id_violations_are_batch_protocol_errors(violation: str) -> None:
    first = PreparedDocument(document_id=uuid4(), body="First valid review body.")
    second = PreparedDocument(document_id=uuid4(), body="Second valid review body.")

    def empty(document_id):
        return {"document_id": str(document_id), "aspects": []}

    if violation == "unknown":
        documents = [empty(uuid4()), empty(second.document_id)]
    elif violation == "duplicate":
        documents = [empty(first.document_id), empty(first.document_id)]
    else:
        documents = [empty(first.document_id)]

    with pytest.raises(ExtractionResponseError):
        AspectExtractor._validate_payload(
            {"documents": documents},
            [first, second],
        )


@pytest.mark.asyncio
async def test_protocol_failure_falls_back_to_single_document_requests() -> None:
    first = make_document("The fan is loud throughout the night and wakes me up.")
    second = make_document("The battery lasted eight hours during the outage.")

    class FallbackCompletions(FakeCompletions):
        async def create(self, **kwargs):
            self.calls += 1
            prompt = kwargs["messages"][1]["content"]
            if self.calls <= 3:
                content = '{"documents":[]}'
            elif str(first.id) in prompt:
                content = (
                    '{"documents":[{"document_id":"'
                    + str(first.id)
                    + '","aspects":[{"aspect_label":"noise_level",'
                    '"sentiment":"negative","confidence":0.9,'
                    '"mention_text":"fan is loud","context_window":null}]}]}'
                )
            else:
                content = (
                    '{"documents":[{"document_id":"'
                    + str(second.id)
                    + '","aspects":[{"aspect_label":"battery_capacity",'
                    '"sentiment":"positive","confidence":0.9,'
                    '"mention_text":"battery lasted eight hours",'
                    '"context_window":null}]}]}'
                )
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

    async def no_sleep(_: float) -> None:
        return None

    client = FakeClient("")
    client.chat.completions = FallbackCompletions("")
    extractor = AspectExtractor(
        client,
        language_detector=lambda _: True,
        sleep=no_sleep,
    )

    result = await extractor.extract([first, second])

    assert client.chat.completions.calls == 5
    assert result.failed_document_errors == {}
    assert [document.document_id for document in result.documents] == [
        first.id,
        second.id,
    ]
    assert all(len(document.aspects) == 1 for document in result.documents)
