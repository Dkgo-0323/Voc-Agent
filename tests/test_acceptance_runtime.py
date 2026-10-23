"""Business adapters through the real SDK, with no network or application DB."""

import json

import httpx
import pytest
from openai import APIConnectionError

from shared.acceptance.runtime import acceptance_adapters
from shared.acceptance.transport import ProviderPolicy

POLICY = ProviderPolicy("https://provider.invalid/v4", "chat-test", "embed-test")


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
