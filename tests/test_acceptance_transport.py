"""Real HTTP client/SDK serialization with a fake wire; never a live provider."""

import asyncio
import json

import httpx
import pytest
from openai import APIConnectionError, AsyncOpenAI

from shared.acceptance.transport import (
    AcceptanceStopped,
    AcceptanceTransport,
    ProviderPolicy,
)

BASE = "https://provider.invalid/v4"


def payload():
    return {
        "model": "chat-test",
        "messages": [{"role": "user", "content": "secret text"}],
        "max_tokens": 32,
    }


def guarded(handler, **limits):
    return AcceptanceTransport(
        ProviderPolicy(BASE, "chat-test", "embed-test", **limits),
        httpx.MockTransport(handler),
    )


def response(request):
    return httpx.Response(
        200,
        json={"usage": {"prompt_tokens": 2, "completion_tokens": 3}},
        request=request,
    )


@pytest.mark.asyncio
async def test_concurrent_requests_cannot_overrun_allowance():
    calls = []

    async def wire(request):
        calls.append(request)
        await asyncio.sleep(0)
        return response(request)

    transport = guarded(wire, chat_requests=1)
    async with httpx.AsyncClient(transport=transport) as client:
        results = await asyncio.gather(
            *[
                client.post(BASE + "/chat/completions", json=payload())
                for _ in range(2)
            ],
            return_exceptions=True,
        )
    assert len(calls) == 1
    assert sum(isinstance(result, AcceptanceStopped) for result in results) == 1
    assert transport.summary()["outbound_attempts"]["chat"] == 1
    assert "secret" not in json.dumps(transport.summary())


@pytest.mark.parametrize(
    "mutation", ["origin", "model", "tokens", "token_alias", "stream", "bytes"]
)
@pytest.mark.asyncio
async def test_out_of_plan_requests_never_reach_wire(mutation):
    calls = []
    transport = guarded(lambda req: calls.append(req) or response(req))
    url, body = BASE + "/chat/completions", payload()
    if mutation == "origin":
        url = "https://elsewhere.invalid/v4/chat/completions"
    elif mutation == "model":
        body["model"] = "unapproved-model"
    elif mutation == "tokens":
        body.pop("max_tokens")
    elif mutation == "token_alias":
        body["max_completion_tokens"] = 100000
    elif mutation == "stream":
        body["stream"] = True
    elif mutation == "bytes":
        body["extra"] = "x" * 262_145
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(AcceptanceStopped):
            await client.post(url, json=body)
    assert calls == []


@pytest.mark.asyncio
async def test_failure_blocks_even_sdk_automatic_retry_attempts():
    calls = []
    transport = guarded(
        lambda req: calls.append(req) or httpx.Response(429, json={"error": {}})
    )
    async with AsyncOpenAI(
        api_key="test-only",
        base_url=BASE,
        max_retries=2,
        http_client=httpx.AsyncClient(transport=transport),
    ) as client:
        with pytest.raises(APIConnectionError):
            await client.chat.completions.create(
                model="chat-test",
                max_tokens=32,
                messages=[{"role": "user", "content": "test"}],
            )
    assert len(calls) == 1
    assert transport.summary()["stopped"] is True


@pytest.mark.parametrize("kind", ["missing_usage", "timeout", "dimension", "batch"])
@pytest.mark.asyncio
async def test_embedding_contract_and_failure_stop(kind):
    calls = []

    def wire(request):
        calls.append(request)
        if kind == "timeout":
            raise httpx.ReadTimeout("fake", request=request)
        return httpx.Response(200, json={})

    transport = guarded(wire)
    body = {"model": "embed-test", "dimensions": 1024, "input": ["test"]}
    if kind == "dimension":
        body["dimensions"] = 768
    if kind == "batch":
        body["input"] = ["test"] * 65
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises((AcceptanceStopped, httpx.ReadTimeout)):
            await client.post(BASE + "/embeddings", json=body)
        with pytest.raises(AcceptanceStopped):
            await client.post(BASE + "/embeddings", json=body)
    assert len(calls) == (0 if kind in {"dimension", "batch"} else 1)


@pytest.mark.asyncio
async def test_sdk_chat_and_embedding_can_share_one_guard_and_usage_summary():
    calls = []

    def wire(request):
        calls.append(request)
        data = (
            {
                "id": "fake",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "test"},
                    }
                ],
            }
            if request.url.path.endswith("completions")
            else {"data": [{"index": 0, "embedding": [0.0] * 1024}]}
        )
        return httpx.Response(
            200, json={**data, "usage": {"prompt_tokens": 2, "completion_tokens": 0}}
        )

    transport = guarded(wire)
    async with AsyncOpenAI(
        api_key="test-only",
        base_url=BASE,
        max_retries=0,
        http_client=httpx.AsyncClient(transport=transport),
    ) as client:
        await client.chat.completions.create(
            model="chat-test",
            max_tokens=32,
            messages=[{"role": "user", "content": "test"}],
        )
        await client.embeddings.create(
            model="embed-test", dimensions=1024, input=["test"]
        )
    assert len(calls) == 2
    assert transport.summary()["outbound_attempts"] == {"chat": 1, "embedding": 1}
    assert transport.summary()["reported_tokens"] == {"prompt": 4, "completion": 0}
    assert transport.summary()["monetary_cap_enforced"] is False
