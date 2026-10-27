"""Model resources: production request ownership or explicit acceptance run ownership."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, Request
from openai import AsyncOpenAI

from backend.app.agent.llm import OpenAIChatCompletionsModel
from backend.app.core.settings import settings
from pipelines.embedding.embedder import Embedder


@dataclass(frozen=True)
class ModelResources:
    chat: OpenAIChatCompletionsModel
    embedder: Embedder


def stop_acceptance_run(request: Request) -> None:
    """Latch an injected run on business/stream failure; production is a no-op."""
    app = getattr(request, "app", None)
    adapters = getattr(getattr(app, "state", None), "acceptance_adapters", None)
    if adapters is not None:
        adapters.guard.stop()


def _normalized_base_url(value: str) -> str:
    return value.rstrip("/").lower()


def _uses_zhipu_json_mode() -> bool:
    return "bigmodel.cn" in _normalized_base_url(settings.llm_base_url)


def _resolve_llm_api_key() -> str:
    """Reuse the embedding key only when both clients target the same provider."""
    if settings.llm_api_key:
        return settings.llm_api_key
    if _normalized_base_url(settings.llm_base_url) == _normalized_base_url(
        settings.embedding_base_url
    ):
        return settings.embedding_api_key
    if "api.openai.com" in settings.llm_base_url:
        return settings.openai_api_key
    return ""


@asynccontextmanager
async def model_resources(app: FastAPI) -> AsyncIterator[ModelResources]:
    # This attribute is set only by the Python factory, never by HTTP/env input.
    adapters = getattr(app.state, "acceptance_adapters", None)
    if adapters is not None:
        yield ModelResources(adapters.chat, adapters.embedder)
        return  # The outer run, not a request, owns and closes these resources.
    llm_key = _resolve_llm_api_key()
    if not llm_key:
        raise RuntimeError("LLM_API_KEY is not configured and no same-provider key can be reused")
    async with AsyncOpenAI(
        api_key=llm_key, base_url=settings.llm_base_url,
        timeout=settings.llm_timeout_seconds, max_retries=settings.llm_max_retries,
    ) as llm_client, AsyncOpenAI(
        api_key=settings.embedding_api_key or settings.openai_api_key,
        base_url=settings.embedding_base_url,
        timeout=settings.llm_timeout_seconds, max_retries=settings.llm_max_retries,
    ) as embedding_client:
        yield ModelResources(
            OpenAIChatCompletionsModel(
                llm_client, model=settings.llm_model,
                max_tokens=settings.llm_max_tokens, extra_body=settings.llm_extra_body,
                final_response_format=(
                    {"type": "json_object"} if _uses_zhipu_json_mode() else None
                ),
            ),
            Embedder(client=embedding_client),
        )
