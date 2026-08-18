"""OpenAI embedding adapter and canonical aspect text construction."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from openai import AsyncOpenAI

from backend.app.core.settings import settings
from pipelines.config.targets import TARGETS

EMBEDDING_MODEL = settings.embedding_model
EMBEDDING_DIMENSION = settings.embedding_dimensions
EMBEDDING_BATCH_SIZE = settings.embedding_batch_size
MAX_EMBEDDING_BATCH_SIZE = 100


class EmbeddingsClient(Protocol):
    embeddings: Any


@dataclass(frozen=True)
class EmbeddingInput:
    """The PostgreSQL fields required to build one canonical embedding text."""

    sku_code: str
    aspect_label: str
    mention_text: str
    context_window: str | None = None


def sku_name(sku_code: str) -> str:
    """Resolve a locked SKU slug to its customer-facing product name."""
    target = TARGETS.get(sku_code)
    if target is None:
        raise ValueError(f"Unknown sku_code: {sku_code}")
    return f"{target['brand']} {target['model']}"


def build_embed_text(item: EmbeddingInput) -> str:
    """Build the stable text persisted in PostgreSQL and sent for embedding."""
    mention = item.mention_text.strip()
    if not mention:
        raise ValueError("mention_text must not be empty")
    text = f"[{sku_name(item.sku_code)}] [{item.aspect_label}]: {mention}"
    if item.context_window and (context := item.context_window.strip()):
        text += f". Context: {context[:200]}"
    return text


class Embedder:
    """Generate embeddings in bounded batches while preserving input order."""

    def __init__(
        self,
        client: EmbeddingsClient | None = None,
        model: str | None = None,
        dimensions: int | None = None,
        batch_size: int | None = None,
    ) -> None:
        model = model or settings.embedding_model
        dimensions = dimensions or settings.embedding_dimensions
        batch_size = batch_size or settings.embedding_batch_size
        if batch_size < 1 or batch_size > MAX_EMBEDDING_BATCH_SIZE:
            raise ValueError(
                f"batch_size must be between 1 and {MAX_EMBEDDING_BATCH_SIZE}"
            )
        api_key = settings.embedding_api_key or settings.openai_api_key
        if client is None and not api_key:
            raise ValueError("EMBEDDING_API_KEY is not configured")
        self._client = client or AsyncOpenAI(
            api_key=api_key,
            base_url=settings.embedding_base_url,
        )
        self._model = model
        self._dimensions = dimensions
        self._batch_size = batch_size

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed non-empty texts; an API failure is left to the pipeline to retry."""
        if any(not text.strip() for text in texts):
            raise ValueError("Embedding input must not contain empty text")
        vectors: list[list[float]] = []
        for offset in range(0, len(texts), self._batch_size):
            batch = list(texts[offset : offset + self._batch_size])
            response = await self._client.embeddings.create(
                model=self._model,
                input=batch,
                dimensions=self._dimensions,
            )
            ordered = sorted(response.data, key=lambda item: item.index)
            if len(ordered) != len(batch):
                raise RuntimeError("Embedding API returned an incomplete batch")
            batch_vectors = [list(item.embedding) for item in ordered]
            if any(len(vector) != self._dimensions for vector in batch_vectors):
                raise RuntimeError("Embedding API returned an unexpected vector dimension")
            vectors.extend(batch_vectors)
        return vectors

    async def embed_inputs(
        self, items: Sequence[EmbeddingInput]
    ) -> tuple[list[str], list[list[float]]]:
        texts = [build_embed_text(item) for item in items]
        return texts, await self.embed(texts)
