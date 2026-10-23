"""Explicit, run-scoped adapters with caller-supplied credentials and wire.

The caller owns this context for the entire run, rather than per HTTP request.
Production API dependencies do not enable it automatically.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from openai import AsyncOpenAI

from backend.app.agent.llm import OpenAIChatCompletionsModel
from pipelines.embedding.embedder import Embedder
from shared.acceptance.transport import AcceptanceTransport, ProviderPolicy


@dataclass(frozen=True)
class AcceptanceAdapters:
    chat: OpenAIChatCompletionsModel
    embedder: Embedder
    guard: AcceptanceTransport


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
            chat=OpenAIChatCompletionsModel(
                client, model=policy.chat_model,
                max_tokens=policy.max_output_tokens,
            ),
            embedder=Embedder(
                client=client, model=policy.embedding_model,
                dimensions=1024, batch_size=64,
            ),
            guard=guard,
        )
