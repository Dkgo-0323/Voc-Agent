"""Real FastAPI dependency/lifespan and SDK wiring, fake storage and HTTP wire."""

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Annotated
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import Depends
from openai import APIConnectionError

from backend.app import main
from backend.app.agent.conversation import ConversationService
from backend.app.api.ask import get_conversation_service
from backend.app.api.reports import get_report_generation_service
from backend.app.core import model_resources as resources_module
from backend.app.core.database import get_db
from backend.app.reporting.service import ReportGenerationService
from shared.acceptance.runtime import acceptance_adapters
from shared.acceptance.transport import ProviderPolicy

POLICY = ProviderPolicy(
    "https://provider.invalid/v4", "chat-test", "embed-test",
    chat_requests=2, embedding_requests=2,
)


def embedding_response(dimensions=1024):
    return httpx.Response(200, json={
        "data": [{"index": 0, "embedding": [0.1] * dimensions,
                  "object": "embedding"}],
        "model": "embed-test", "object": "list",
        "usage": {"prompt_tokens": 2, "total_tokens": 2},
    })


def chat_response():
    return httpx.Response(200, json={
        "id": "test", "object": "chat.completion", "created": 0,
        "model": "chat-test", "choices": [{"index": 0,
            "message": {"role": "assistant", "content": "answer"},
            "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
    })


def fake_storage(monkeypatch):
    @asynccontextmanager
    async def db_context():
        yield object()

    monkeypatch.setattr(main, "init_db", AsyncMock())
    close = AsyncMock()
    monkeypatch.setattr(main, "close_db", close)
    monkeypatch.setattr(main, "get_db_context", db_context)
    monkeypatch.setattr(main.AspectRepository, "validate_locked_skus", AsyncMock())
    monkeypatch.setattr(main.MilvusRepository, "setup_collection", lambda self: None)
    return close


def forbidden(*args, **kwargs):
    raise AssertionError("Acceptance must not construct a separate provider client")


@pytest.mark.asyncio
async def test_startup_ask_report_and_later_request_share_one_allowance(monkeypatch):
    close = fake_storage(monkeypatch)
    calls = []

    def wire(request):
        calls.append(json.loads(request.content))
        return embedding_response() if request.url.path.endswith("embeddings") else chat_response()

    async with acceptance_adapters(
        POLICY, api_key="offline-only", transport=httpx.MockTransport(wire),
    ) as adapters:
        monkeypatch.setattr(resources_module, "AsyncOpenAI", forbidden)
        monkeypatch.setattr(main, "Embedder", forbidden)
        app = main.create_app(acceptance_adapters=adapters)
        app.dependency_overrides[get_db] = lambda: object()

        # Diagnostic endpoints exercise the real service dependencies, without
        # pretending to verify DB persistence, Agent answers or report quality.
        @app.get("/probe/ask")
        async def ask(service: Annotated[ConversationService, Depends(get_conversation_service)]):
            assert service._router._model is adapters.chat
            return (await service._router._model.complete(messages=[], tools=[])).content

        @app.get("/probe/report")
        async def report(service: Annotated[ReportGenerationService, Depends(get_report_generation_service)]):
            assert service._rag._embedder is adapters.embedder
            await service._rag._embedder.embed(["question"])
            return (await service._model.complete(messages=[], tools=[])).content

        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test",
            ) as client:
                assert (await client.get("/probe/ask")).json() == "answer"
                assert (await client.get("/probe/report")).json() == "answer"
                # Request teardown must not close the shared client; only quota
                # exhaustion may reject the next request, before the fake wire.
                with pytest.raises(APIConnectionError):
                    await client.get("/probe/ask")
            assert len(calls) == 4
            assert adapters.guard.summary()["outbound_attempts"] == {"chat": 2, "embedding": 2}
        close.assert_awaited_once()
        assert not hasattr(main.create_app().state, "acceptance_adapters")


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["http", "dimension", "cancel"])
async def test_failed_startup_stops_shared_run_and_closes_db(monkeypatch, failure):
    close = fake_storage(monkeypatch)
    calls = []

    async def wire(request):
        calls.append(request)
        if failure == "cancel":
            raise asyncio.CancelledError()
        if failure == "http":
            return httpx.Response(429, json={"error": {"message": "test"}})
        return embedding_response(768)

    async with acceptance_adapters(
        POLICY, api_key="offline-only", transport=httpx.MockTransport(wire),
    ) as adapters:
        app = main.create_app(acceptance_adapters=adapters)
        expected = {"http": APIConnectionError, "dimension": RuntimeError, "cancel": asyncio.CancelledError}[failure]
        with pytest.raises(expected):
            async with app.router.lifespan_context(app):
                pytest.fail("Invalid startup must not accept traffic")
        close.assert_awaited_once()
        assert adapters.guard.summary()["stopped"] is True
        with pytest.raises(APIConnectionError):
            await adapters.chat.complete(messages=[], tools=[])
        assert len(calls) == 1


@pytest.mark.asyncio
async def test_shutdown_closes_db_when_application_body_fails(monkeypatch):
    close = fake_storage(monkeypatch)
    async with acceptance_adapters(
        POLICY, api_key="offline-only",
        transport=httpx.MockTransport(lambda request: embedding_response()),
    ) as adapters:
        app = main.create_app(acceptance_adapters=adapters)
        with pytest.raises(RuntimeError, match="application failed"):
            async with app.router.lifespan_context(app):
                raise RuntimeError("application failed")
        close.assert_awaited_once()
