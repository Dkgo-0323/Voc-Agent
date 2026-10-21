"""The smoke provider must expose its fake nature and ignore requested dimensions."""

import json
import threading
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen

import pytest

from ops.smoke.provider import Handler, state
from scripts.run_container_smoke import request


@pytest.fixture
def provider():
    state.update(dimensions=1024, embedding_requests=0)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def post(url, body):
    request = Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=3) as response:
        return json.load(response)


def test_fixed_dimension_does_not_echo_client_request(provider):
    data = post(provider + "/v1/embeddings", {"input": ["probe"], "dimensions": 768})
    assert data["model"] == "smoke-fixed-vector"
    assert len(data["data"][0]["embedding"]) == 1024
    assert data["usage"]["total_tokens"] == 0


def test_wrong_dimension_is_explicitly_controllable(provider):
    updated = post(provider + "/dimensions", {"dimensions": 768})
    assert updated["test_double"] is True
    data = post(provider + "/v1/embeddings", {"input": ["probe"], "dimensions": 1024})
    assert len(data["data"][0]["embedding"]) == 768
    with urlopen(provider + "/stats", timeout=3) as response:
        assert json.load(response)["embedding_requests"] == 1


def test_unexpected_http_status_has_readable_diagnostic(provider):
    with pytest.raises(AssertionError, match="GET .*expected 400, got 200"):
        request(provider + "/health", status=400)
