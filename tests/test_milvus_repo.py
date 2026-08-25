from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.app.core.settings import settings
from pipelines.embedding.milvus_repo import (
    INDEX_CONFIGS,
    MilvusRecord,
    MilvusRepository,
    _partition_name,
)


def test_partition_name_is_milvus_safe() -> None:
    assert _partition_name("ecoflow-delta2") == "sku_ecoflow_delta2"


def test_scalar_index_types_match_milvus_field_types() -> None:
    assert INDEX_CONFIGS["sku_code"]["index_type"] == "Trie"
    assert INDEX_CONFIGS["aspect_label"]["index_type"] == "Trie"
    assert INDEX_CONFIGS["sentiment"]["index_type"] == "Trie"
    assert INDEX_CONFIGS["week_id"]["index_type"] == "STL_SORT"
    assert INDEX_CONFIGS["quality_score"]["index_type"] == "STL_SORT"


def test_ensure_indexes_repairs_partially_initialized_collection() -> None:
    class Index:
        field_name = "vector"

    class Collection:
        indexes = [Index()]

        def __init__(self) -> None:
            self.created: list[tuple[str, dict]] = []

        def create_index(self, field_name: str, params: dict) -> None:
            self.created.append((field_name, params))

    collection = Collection()
    MilvusRepository._ensure_indexes(collection)

    assert [field for field, _ in collection.created] == [
        "sku_code",
        "aspect_label",
        "sentiment",
        "week_id",
        "quality_score",
    ]


def test_record_validation_rejects_wrong_vector_dimension() -> None:
    record = MilvusRecord(
        id=uuid4(),
        vector=[0.0],
        sku_code="ecoflow-delta2",
        aspect_label="noise_level",
        sentiment="negative",
        week_id=202603,
        quality_score=0.8,
    )
    repository = MilvusRepository()
    with pytest.raises(ValueError, match=str(settings.embedding_dimensions)):
        repository._validate_record(record)


def test_record_validation_accepts_contract_compliant_record() -> None:
    record = MilvusRecord(
        id=uuid4(),
        vector=[0.0] * settings.embedding_dimensions,
        sku_code="ecoflow-delta2",
        aspect_label="noise_level",
        sentiment="negative",
        week_id=202603,
        quality_score=0.8,
    )
    MilvusRepository()._validate_record(record)


def test_collection_schema_accepts_configured_dimension() -> None:
    collection = SimpleNamespace(
        schema=SimpleNamespace(
            fields=[
                SimpleNamespace(
                    name="vector", params={"dim": settings.embedding_dimensions}
                )
            ]
        )
    )

    MilvusRepository()._validate_collection_dimension(collection)


def test_collection_schema_rejects_wrong_dimension() -> None:
    wrong_dimension = settings.embedding_dimensions + 1
    collection = SimpleNamespace(
        schema=SimpleNamespace(
            fields=[SimpleNamespace(name="vector", params={"dim": wrong_dimension})]
        )
    )

    with pytest.raises(
        RuntimeError,
        match=(
            f"EMBEDDING_DIMENSIONS={settings.embedding_dimensions}.*"
            f"collection_dimension={wrong_dimension}"
        ),
    ):
        MilvusRepository()._validate_collection_dimension(collection)


def test_search_uses_configured_quality_threshold_by_default(monkeypatch) -> None:
    class Collection:
        def __init__(self) -> None:
            self.expression = ""

        def load(self) -> None:
            pass

        def search(self, **kwargs):
            self.expression = kwargs["expr"]
            return [[]]

    collection = Collection()
    repository = MilvusRepository(dimension=2)
    monkeypatch.setattr(repository, "setup_collection", lambda: collection)

    assert repository.search([0.0, 0.0]) == []
    assert (
        f"quality_score >= {settings.aspect_quality_threshold}"
        in collection.expression
    )
