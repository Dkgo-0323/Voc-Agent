import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from backend.app.core import model_resources as module


@pytest.mark.asyncio
async def test_parallel_requests_share_clients_and_request_teardown_does_not_close_them(
    monkeypatch,
):
    events = []
    resources = SimpleNamespace(chat=object(), embedder=object())

    @asynccontextmanager
    async def fresh():
        events.append("open")
        await asyncio.sleep(0)
        try:
            yield resources
        finally:
            events.append("close")

    monkeypatch.setattr(module, "_fresh_model_resources", fresh)
    app = FastAPI()
    pool = module.ModelResourcePool()
    app.state.model_resource_pool = pool

    async def request():
        async with module.model_resources(app) as current:
            assert current is resources

    await asyncio.gather(*(request() for _ in range(5)))
    assert events == ["open"]
    await pool.aclose()
    assert events == ["open", "close"]
    with pytest.raises(RuntimeError):
        await pool.get()


@pytest.mark.asyncio
async def test_failed_open_can_be_retried_without_caching_broken_resources(monkeypatch):
    attempts = 0

    @asynccontextmanager
    async def fresh():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("failed open")
        yield "working"

    monkeypatch.setattr(module, "_fresh_model_resources", fresh)
    pool = module.ModelResourcePool()
    with pytest.raises(RuntimeError):
        await pool.get()
    assert await pool.get() == "working"
    assert attempts == 2
    await pool.aclose()
