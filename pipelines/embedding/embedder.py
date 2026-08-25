"""OpenAI embedding adapter and canonical aspect text construction."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from openai import AsyncOpenAI

from backend.app.core.settings import settings

MAX_EMBEDDING_BATCH_SIZE = 100
DIMENSION_PROBE_TEXT = "portable power station embedding dimension check"


class EmbeddingsClient(Protocol):
    embeddings: Any


@dataclass(frozen=True)
class EmbeddingInput:
    """The PostgreSQL fields required to build one canonical embedding text."""

    sku_name: str
    aspect_label: str
    mention_text: str
    context_window: str | None = None


def build_embed_text(item: EmbeddingInput) -> str:
    """Build the stable text persisted in PostgreSQL and sent for embedding."""
    mention = item.mention_text.strip()
    if not mention:
        raise ValueError("mention_text must not be empty")
    product_name = item.sku_name.strip()
    if not product_name:
        raise ValueError("sku_name must not be empty")
    text = f"[{product_name}] [{item.aspect_label}]: {mention}"
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
        dimensions = settings.embedding_dimensions if dimensions is None else dimensions
        batch_size = batch_size or settings.embedding_batch_size
        if dimensions <= 0:
            raise ValueError("EMBEDDING_DIMENSIONS must be positive")
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
            invalid_dimensions = {
                len(vector)
                for vector in batch_vectors
                if len(vector) != self._dimensions
            }
            if invalid_dimensions:
                raise RuntimeError(
                    "Embedding API dimension mismatch: "
                    f"EMBEDDING_DIMENSIONS={self._dimensions}, "
                    f"model={self._model}, returned={sorted(invalid_dimensions)}"
                )
            vectors.extend(batch_vectors)
        return vectors

    async def validate_dimension_contract(self) -> None:
        """Probe the configured provider before the application accepts traffic."""
        vectors = await self.embed([DIMENSION_PROBE_TEXT])
        if len(vectors) != 1:
            raise RuntimeError("Embedding API dimension probe returned no vector")

    async def embed_inputs(
        self, items: Sequence[EmbeddingInput]
    ) -> tuple[list[str], list[list[float]]]:
        texts = [build_embed_text(item) for item in items]
        return texts, await self.embed(texts)
