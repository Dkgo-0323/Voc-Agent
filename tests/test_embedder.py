from types import SimpleNamespace

import pytest

from pipelines.embedding.embedder import Embedder, EmbeddingInput, build_embed_text


def test_build_embed_text_uses_product_name_and_caps_context() -> None:
    text = build_embed_text(
        EmbeddingInput(
            sku_code="ecoflow-delta2",
            aspect_label="noise_level",
            mention_text="fan is loud",
            context_window="x" * 250,
        )
    )
    assert text.startswith("[EcoFlow DELTA 2] [noise_level]: fan is loud. Context: ")
    assert text.endswith("x" * 200)


class FakeEmbeddings:
    def __init__(self) -> None:
        self.batch_sizes: list[int] = []

    async def create(self, **kwargs):
        self.batch_sizes.append(len(kwargs["input"]))
        data = [
            SimpleNamespace(index=index, embedding=[float(index)] * kwargs["dimensions"])
            for index in reversed(range(len(kwargs["input"])))
        ]
        return SimpleNamespace(data=data)


@pytest.mark.asyncio
async def test_embedder_batches_and_restores_response_order() -> None:
    embeddings = FakeEmbeddings()
    client = SimpleNamespace(embeddings=embeddings)
    vectors = await Embedder(client=client, batch_size=100).embed(
        [f"text {index}" for index in range(101)]
    )
    assert embeddings.batch_sizes == [100, 1]
    assert len(vectors) == 101
    assert vectors[1][0] == 1.0


def test_embedder_requires_api_key_without_injected_client(monkeypatch) -> None:
    monkeypatch.setattr("pipelines.embedding.embedder.settings.embedding_api_key", "")
    monkeypatch.setattr("pipelines.embedding.embedder.settings.openai_api_key", "")
    with pytest.raises(ValueError, match="EMBEDDING_API_KEY"):
        Embedder(client=None)
