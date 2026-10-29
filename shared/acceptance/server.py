"""Loopback HTTP bridge for an app whose lifespan is owned by the workflow."""

from __future__ import annotations

import asyncio
import socket
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI


@asynccontextmanager
async def acceptance_server(app: FastAPI) -> AsyncIterator[str]:
    """Borrow an already-started app; never run lifespan or install signals.

    Bind before handing the socket to Uvicorn, so port selection has no race.
    The workflow must enclose this context and remains responsible for DB/SDK
    cleanup. Only the local listener is owned here; no subprocess is created.
    """
    config = uvicorn.Config(
        app, host="127.0.0.1", port=0, lifespan="off", workers=1,
        access_log=False, log_config=None, log_level="warning", ws="none",
        timeout_graceful_shutdown=2,
    )
    config.load()
    server = uvicorn.Server(config)
    server.lifespan = config.lifespan_class(config)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        listener.setblocking(False)
        port = listener.getsockname()[1]
        try:
            await asyncio.wait_for(server.startup(sockets=[listener]), timeout=5)
            if not server.started:
                raise RuntimeError("Acceptance HTTP listener did not start")
            yield f"http://127.0.0.1:{port}"
        finally:
            # startup may fail after creating a listener. Close partial servers
            # too, and let shutdown finish even when the exercise was cancelled.
            if server.started or getattr(server, "servers", None):
                await server.shutdown(sockets=[listener])


def http_exercise(
    exercise: Callable[[str, str], Awaitable[tuple[dict, dict]]],
) -> Callable[[FastAPI, str], Awaitable[tuple[dict, dict]]]:
    """Adapt an HTTP/browser callback to the shared workflow exercise contract.

    The callback must connect to this URL and return this run's receipts. It must
    not launch the legacy API webServer. No browser process or live call is
    started merely by constructing the adapter.
    """
    async def run(app: FastAPI, run_id: str) -> tuple[dict, dict]:
        async with acceptance_server(app) as base_url:
            return await exercise(base_url, run_id)

    return run
