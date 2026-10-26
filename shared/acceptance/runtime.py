"""Explicit, run-scoped adapters with caller-supplied credentials and wire.

The caller owns this context for the entire run, rather than per HTTP request.
Production API dependencies do not enable it automatically.
"""

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx
from openai import AsyncOpenAI

from backend.app.agent.llm import ModelResponse, OpenAIChatCompletionsModel
from backend.app.db.repositories.schemas import DocumentRead
from pipelines.embedding.embedder import Embedder
from pipelines.enrichment.aspect_extractor import (
    AspectExtractor,
    BatchExtractionResult,
    ExtractionResponseError,
)
from shared.acceptance.transport import AcceptanceTransport, ProviderPolicy


@dataclass(frozen=True)
class AcceptanceAdapters:
    chat: OpenAIChatCompletionsModel
    embedder: Embedder
    guard: AcceptanceTransport
    extractor: AspectExtractor


class _AcceptanceChat(OpenAIChatCompletionsModel):
    def __init__(self, client: AsyncOpenAI, guard: AcceptanceTransport) -> None:
        super().__init__(client, model=guard.policy.chat_model,
                         max_tokens=guard.policy.max_output_tokens)
        self._guard = guard

    async def complete(
        self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]],
    ) -> ModelResponse:
        try:
            result = await super().complete(messages=messages, tools=tools)
            if not result.tool_calls and not (result.content or "").strip():
                raise ValueError("Acceptance chat returned no answer or tool call")
            if any(
                not call.call_id or not call.name or not isinstance(call.arguments, dict)
                for call in result.tool_calls
            ):
                raise ValueError("Acceptance chat returned an invalid tool call")
            return result
        except BaseException:
            self._guard.stop()
            raise


class _AcceptanceEmbedder(Embedder):
    def __init__(self, client: AsyncOpenAI, guard: AcceptanceTransport) -> None:
        super().__init__(client=client, model=guard.policy.embedding_model,
                         dimensions=1024, batch_size=64)
        self._guard = guard

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        try:
            return await super().embed(texts)
        except BaseException:
            self._guard.stop()
            raise


class _AcceptanceExtractor(AspectExtractor):
    """Propagate semantic failures to the same run latch used by HTTP failures."""

    def __init__(self, client: AsyncOpenAI, guard: AcceptanceTransport) -> None:
        super().__init__(
            client, model=guard.policy.chat_model,
            max_tokens=guard.policy.max_output_tokens, fail_fast=True,
        )
        self._guard = guard

    async def extract(self, documents: Sequence[DocumentRead]) -> BatchExtractionResult:
        try:
            result = await super().extract(documents)
            if result.failed_document_errors:
                raise ExtractionResponseError(
                    "Acceptance extraction contains failed documents"
                )
            return result
        except BaseException:
            # Includes cancellation. A later business attempt must not reach wire.
            self._guard.stop()
            raise


@asynccontextmanager
async def acceptance_adapters(
    policy: ProviderPolicy,
    *,
    api_key: str,
    transport: httpx.AsyncBaseTransport,
    timeout_seconds: float = 30,
) -> AsyncIterator[AcceptanceAdapters]:
    """Inject an explicit wire (MockTransport offline), sharing all run counters.

    No default network transport or credential fallback: a future live runner
    must supply both after approval. Importing Embedder still imports application
    settings; launch from an isolated environment as with the test runner. SDK retries are disabled; the guard also stops
    subsequent business attempts after a wire failure.
    """
    if not api_key.strip() or not 0 < timeout_seconds <= 120:
        raise ValueError("Explicit key and timeout in (0, 120] are required")
    guard = AcceptanceTransport(policy, transport)
    async with httpx.AsyncClient(
        transport=guard, timeout=timeout_seconds, follow_redirects=False,
        trust_env=False,
    ) as http_client, AsyncOpenAI(
        api_key=api_key, base_url=policy.base_url, http_client=http_client,
        max_retries=0, timeout=timeout_seconds,
    ) as client:
        yield AcceptanceAdapters(
            chat=_AcceptanceChat(client, guard),
            embedder=_AcceptanceEmbedder(client, guard),
            guard=guard,
            extractor=_AcceptanceExtractor(client, guard),
        )
