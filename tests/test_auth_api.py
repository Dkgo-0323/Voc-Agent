from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app.api.ask import get_conversation_service
from backend.app.core.database import get_db
from backend.app.core.security import create_access_token
from backend.app.core.settings import settings
from backend.app.main import app
from tests.test_ask_api import FakeConversationService, FakeTransaction, agent_result


@pytest.fixture
def auth_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[
    tuple[TestClient, FakeConversationService]
]:
    monkeypatch.setattr(settings, "admin_password", "phase8-test-password")
    service = FakeConversationService(agent_result([]))
    transaction = FakeTransaction()
    app.dependency_overrides[get_conversation_service] = lambda: service
    app.dependency_overrides[get_db] = lambda: transaction
    client = TestClient(app, raise_server_exceptions=False)
    yield client, service
    client.close()
    app.dependency_overrides.clear()


def _login(client: TestClient) -> str:
    response = client.post("/api/auth/login", json={"password": "phase8-test-password"})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_correct_password_returns_bearer_token(auth_client: tuple[TestClient, FakeConversationService]) -> None:
    client, _ = auth_client

    response = client.post("/api/auth/login", json={"password": "phase8-test-password"})

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert isinstance(response.json()["access_token"], str)


def test_incorrect_password_is_rejected(auth_client: tuple[TestClient, FakeConversationService]) -> None:
    client, _ = auth_client

    response = client.post("/api/auth/login", json={"password": "wrong"})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("authorization", [None, "Bearer malformed", "Basic abc"])
def test_protected_routes_reject_missing_or_invalid_tokens(
    auth_client: tuple[TestClient, FakeConversationService], authorization: str | None
) -> None:
    client, _ = auth_client
    headers = {} if authorization is None else {"Authorization": authorization}

    response = client.get("/api/auth/me", headers=headers)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_ask_rejects_a_missing_token(
    auth_client: tuple[TestClient, FakeConversationService],
) -> None:
    client, service = auth_client

    response = client.post("/api/ask", json={"message": "Count Delta 2 reviews"})

    assert response.status_code == 401
    assert service.turns == []


def test_expired_token_is_rejected(auth_client: tuple[TestClient, FakeConversationService]) -> None:
    client, _ = auth_client
    expired = create_access_token("admin", expires_delta=timedelta(seconds=-1))

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"})

    assert response.status_code == 401


def test_valid_token_returns_identity_and_can_call_ask(
    auth_client: tuple[TestClient, FakeConversationService]
) -> None:
    client, service = auth_client
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    me = client.get("/api/auth/me", headers=headers)
    ask = client.post("/api/ask", json={"message": "Count Delta 2 reviews"}, headers=headers)

    assert me.status_code == 200
    assert me.json() == {"subject": "admin"}
    assert ask.status_code == 200
    assert "event: done" in ask.text
    assert service.created_by == "admin"


def test_dashboard_routes_remain_public(auth_client: tuple[TestClient, FakeConversationService]) -> None:
    client, _ = auth_client

    response = client.get("/api/weeks")

    assert response.status_code != 401
