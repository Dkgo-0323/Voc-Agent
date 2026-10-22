"""Opt-in transport for a future serial acceptance runner; no settings are loaded.

Caps actual outbound attempts, including SDK retries. It is NOT a monetary cap.
No application client uses it automatically; live execution remains unapproved.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import httpx


class AcceptanceStopped(RuntimeError):
    """Acceptance request is outside its plan or a prior request failed."""


@dataclass(frozen=True)
class ProviderPolicy:
    base_url: str
    chat_model: str
    embedding_model: str
    chat_requests: int = 72
    embedding_requests: int = 24
    max_output_tokens: int = 4096
    max_payload_bytes: int = 262_144

    def __post_init__(self) -> None:
        url = httpx.URL(self.base_url)
        if (
            url.scheme != "https"
            or not url.host
            or url.userinfo
            or url.query
            or url.fragment
        ):
            raise ValueError(
                "Use an explicit HTTPS provider base URL without credentials/query"
            )
        if not self.chat_model or not self.embedding_model:
            raise ValueError("Both approved model identifiers are required")
        if any(
            type(value) is not int or value < 1
            for value in (
                self.chat_requests,
                self.embedding_requests,
                self.max_output_tokens,
                self.max_payload_bytes,
            )
        ):
            raise ValueError("Acceptance limits must be positive integers")


class AcceptanceTransport(httpx.AsyncBaseTransport):
    """Serialize sends, reserve attempts before I/O and halt after any failure.

    Reports only counters/usage, never URLs, headers, prompts, keys or responses.
    Use one instance for both OpenAI clients so they share the same run limits.
    """

    def __init__(self, policy: ProviderPolicy, transport: httpx.AsyncBaseTransport):
        self.policy, self.transport = policy, transport
        self._lock = asyncio.Lock()
        self._stopped = False
        self._counts = {"chat": 0, "embedding": 0}
        self._tokens = {"prompt": 0, "completion": 0}

    def summary(self) -> dict[str, Any]:
        return {
            "outbound_attempts": dict(self._counts),
            "reported_tokens": dict(self._tokens),
            "stopped": self._stopped,
            "cost_cny": None,
            "monetary_cap_enforced": False,
        }

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        async with self._lock:
            if self._stopped:
                raise AcceptanceStopped(
                    "Acceptance has stopped; start a new reviewed run"
                )
            try:
                return await self._send(request)
            except BaseException:
                self._stopped = True
                raise

    async def _send(self, request: httpx.Request) -> httpx.Response:
        base = self.policy.base_url.rstrip("/")
        endpoints = {
            base + "/chat/completions": "chat",
            base + "/embeddings": "embedding",
        }
        kind = endpoints.get(str(request.url))
        if request.method != "POST" or kind is None:
            raise AcceptanceStopped(
                "Acceptance endpoint is outside the approved provider"
            )
        body = await request.aread()
        if len(body) > self.policy.max_payload_bytes:
            raise AcceptanceStopped("Acceptance payload exceeds its byte limit")
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeError):
            raise AcceptanceStopped("Acceptance requires a JSON request") from None
        if not isinstance(payload, dict) or payload.get("stream", False) is not False:
            raise AcceptanceStopped(
                "Only non-streaming provider requests are supported"
            )
        model = (
            self.policy.chat_model if kind == "chat" else self.policy.embedding_model
        )
        if payload.get("model") != model:
            raise AcceptanceStopped("Acceptance model differs from the approved plan")
        if kind == "chat":
            limit = payload.get("max_tokens")
            if (
                "max_completion_tokens" in payload
                or type(limit) is not int
                or not 1 <= limit <= self.policy.max_output_tokens
            ):
                raise AcceptanceStopped(
                    "Chat request lacks a bounded output token limit"
                )
        else:
            texts = payload.get("input")
            if isinstance(texts, str):
                texts = [texts]
            if (
                payload.get("dimensions") != 1024
                or not isinstance(texts, list)
                or not 1 <= len(texts) <= 64
                or any(not isinstance(text, str) or not text.strip() for text in texts)
            ):
                raise AcceptanceStopped(
                    "Embedding input violates the 1024-dimension/batch contract"
                )
        cap = (
            self.policy.chat_requests
            if kind == "chat"
            else self.policy.embedding_requests
        )
        if self._counts[kind] >= cap:
            raise AcceptanceStopped("Acceptance exhausted its request allowance")
        self._counts[kind] += 1
        response = await self.transport.handle_async_request(request)
        try:
            raw = await response.aread()
            if not 200 <= response.status_code < 300:
                raise AcceptanceStopped(
                    "Provider failed; automatic acceptance retries are blocked"
                )
            result = json.loads(raw)
            usage = result.get("usage", {})
            prompt = usage.get("prompt_tokens")
            completion = usage.get(
                "completion_tokens", 0 if kind == "embedding" else None
            )
            if any(
                type(value) is not int or value < 0 for value in (prompt, completion)
            ):
                raise AcceptanceStopped(
                    "Provider usage is missing; acceptance cannot continue"
                )
            self._tokens["prompt"] += prompt
            self._tokens["completion"] += completion
        except BaseException:
            await response.aclose()
            raise
        return response

    async def aclose(self) -> None:
        await self.transport.aclose()
