"""Business adapters through the real SDK, with no network or application DB."""

import asyncio
import json
from datetime import datetime
from uuid import uuid4

import httpx
import pytest
from openai import APIConnectionError

from backend.app.db.repositories.schemas import DocumentRead
from pipelines.enrichment.aspect_extractor import ExtractionResponseError
from shared.acceptance.runtime import acceptance_adapters
from shared.acceptance.transport import ProviderPolicy

POLICY = ProviderPolicy("https://provider.invalid/v4", "chat-test", "embed-test")


def review():
    return DocumentRead(
        id=uuid4(), sku_id=uuid4(), sku_code="ecoflow-delta2",
        sku_name="EcoFlow DELTA 2", platform="amazon", external_id="synthetic-test",
        body="The battery lasted eight hours during the power outage at home.",
        week_id=202643, ingested_at=datetime.now(), processing_status="raw",
        title=None, rating=None, author_hash=None, source_url=None,
        published_at=None, processing_error=None, processed_at=None,
    )


def chat_response(content):
    return httpx.Response(200, json={
        "id": "extract-test", "object": "chat.completion", "created": 0,
        "model": "chat-test", "choices": [{"index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
    })


@pytest.mark.asyncio
async def test_chat_and_embedding_share_run_and_batch_contract():
    calls = []

    def wire(request):
        body = json.loads(request.content)
        calls.append(body)
        if request.url.path.endswith("/embeddings"):
            return httpx.Response(200, json={
                "data": [{"index": i, "embedding": [0.1] * 1024,
                          "object": "embedding"} for i in range(len(body["input"]))],
                "model": "embed-test", "object": "list",
                "usage": {"prompt_tokens": 2, "total_tokens": 2},
            })
        return httpx.Response(200, json={
            "id": "chat-test", "object": "chat.completion", "created": 0,
            "model": "chat-test", "choices": [{"index": 0,
                "message": {"role": "assistant", "content": "answer"},
                "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        })

    async with acceptance_adapters(
        POLICY, api_key="offline-only", transport=httpx.MockTransport(wire),
    ) as adapters:
        answer = await adapters.chat.complete(
            messages=[{"role": "user", "content": "question"}], tools=[],
        )
        vectors = await adapters.embedder.embed(["text"] * 65)
        assert answer.content == "answer"
        assert len(vectors) == 65
        assert [len(item["input"]) for item in calls[1:]] == [64, 1]
        summary = adapters.guard.summary()
        assert summary["outbound_attempts"] == {"chat": 1, "embedding": 2}
        assert summary["reported_tokens"] == {"prompt": 6, "completion": 3}
        assert "question" not in json.dumps(summary)


@pytest.mark.asyncio
async def test_embedding_failure_stops_later_chat_without_another_wire_attempt():
    calls = []
    async with acceptance_adapters(
        POLICY, api_key="offline-only", transport=httpx.MockTransport(
            lambda request: calls.append(request) or httpx.Response(429, json={})
        ),
    ) as adapters:
        with pytest.raises(APIConnectionError):
            await adapters.embedder.embed(["text"])
        with pytest.raises(APIConnectionError):
            await adapters.chat.complete(
                messages=[{"role": "user", "content": "question"}], tools=[],
            )
        assert len(calls) == 1
        assert adapters.guard.summary()["stopped"] is True


@pytest.mark.asyncio
async def test_extraction_and_chat_share_allowance_and_explicit_model():
    document = review()
    calls = []

    def wire(request):
        body = json.loads(request.content)
        calls.append(body)
        return chat_response(json.dumps({"documents": [{
            "document_id": str(document.id), "aspects": [],
        }]}))

    policy = ProviderPolicy(
        POLICY.base_url, POLICY.chat_model, POLICY.embedding_model, chat_requests=1,
    )
    async with acceptance_adapters(
        policy, api_key="offline-only", transport=httpx.MockTransport(wire),
    ) as adapters:
        result = await adapters.extractor.extract([document])
        assert result.documents[0].document_id == document.id
        assert result.failed_document_errors == {}
        assert calls[0]["model"] == policy.chat_model
        assert calls[0]["max_tokens"] == policy.max_output_tokens
        with pytest.raises(APIConnectionError):
            await adapters.chat.complete(messages=[], tools=[])
        assert len(calls) == 1
        assert adapters.guard.summary()["outbound_attempts"] == {
            "chat": 1, "embedding": 0,
        }


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["invalid_json", "missing_id", "invalid_mention", "http", "cancel"])
async def test_extraction_failure_stops_run_without_retry_or_fallback(failure):
    documents = [review(), review()]
    calls = []

    def wire(request):
        calls.append(request)
        if failure == "cancel":
            raise asyncio.CancelledError
        if failure == "http":
            return httpx.Response(429, json={})
        if failure == "invalid_json":
            return chat_response("not JSON")
        if failure == "missing_id":
            return chat_response('{"documents":[]}')
        return chat_response(json.dumps({"documents": [{
            "document_id": str(document.id), "aspects": [{
                "aspect_label": "battery_capacity", "sentiment": "positive",
                "confidence": 0.9, "mention_text": "invented evidence",
            }],
        } for document in documents]}))

    async with acceptance_adapters(
        POLICY, api_key="offline-only", transport=httpx.MockTransport(wire),
    ) as adapters:
        expected = asyncio.CancelledError if failure == "cancel" else ExtractionResponseError
        with pytest.raises(expected):
            await adapters.extractor.extract(documents)
        with pytest.raises(APIConnectionError):
            await adapters.embedder.embed(["text"])
        # A caller retry must also remain blocked before reaching the wire.
        with pytest.raises(ExtractionResponseError):
            await adapters.extractor.extract(documents)
        assert len(calls) == 1
        summary = adapters.guard.summary()
        assert summary["stopped"] is True
        assert summary["outbound_attempts"] == {"chat": 1, "embedding": 0}
        assert documents[0].body not in json.dumps(summary)
