"""Real loopback sockets; no database, provider network or browser required."""

import asyncio
from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from shared.acceptance.server import acceptance_server, http_exercise


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "error", "cancel"])
async def test_listener_borrows_lifespan_streams_and_closes(failure, monkeypatch):
    import uvicorn

    servers = []
    original = uvicorn.Server.startup

    async def capture(self, sockets):
        await original(self, sockets)
        servers.extend(self.servers)

    monkeypatch.setattr(uvicorn.Server, "startup", capture)
    events = []

    @asynccontextmanager
    async def lifespan(app):
        events.append("start")
        app.state.marker = "shared"
        yield
        events.append("stop")

    app = FastAPI(lifespan=lifespan)

    @app.get("/stream")
    async def stream():
        async def chunks():
            yield f"data: {app.state.marker}\n\n"
            await asyncio.sleep(0)
            yield "data: done\n\n"
        return StreamingResponse(chunks(), media_type="text/event-stream")

    url = None

    async def browser(base_url, run_id):
        nonlocal url
        url = base_url
        assert run_id == "run-marker"
        assert base_url.startswith("http://127.0.0.1:")
        async with httpx.AsyncClient(trust_env=False, timeout=3) as client:
            response = await client.get(base_url + "/stream")
        assert response.status_code == 200
        assert response.text == "data: shared\n\ndata: done\n\n"
        assert events == ["start"]
        if failure == "error":
            raise ValueError("browser failed")
        if failure == "cancel":
            raise asyncio.CancelledError()
        return {"ask": run_id}, {"report": run_id}

    async with app.router.lifespan_context(app):
        if failure:
            with pytest.raises(ValueError if failure == "error" else asyncio.CancelledError):
                await http_exercise(browser)(app, "run-marker")
        else:
            assert await http_exercise(browser)(app, "run-marker") == (
                {"ask": "run-marker"}, {"report": "run-marker"},
            )
        assert events == ["start"]
        assert servers and all(not server.is_serving() for server in servers)
        async with httpx.AsyncClient(trust_env=False, timeout=1) as client:
            with pytest.raises((httpx.ConnectError, httpx.ConnectTimeout)):
                await client.get(url + "/stream")
    assert events == ["start", "stop"]


@pytest.mark.asyncio
async def test_startup_failure_does_not_enter_callback(monkeypatch):
    import uvicorn

    async def broken(self, sockets):
        raise RuntimeError("startup failed")

    monkeypatch.setattr(uvicorn.Server, "startup", broken)
    with pytest.raises(RuntimeError, match="startup failed"):
        async with acceptance_server(FastAPI()):
            pytest.fail("must not expose an unready URL")
