"""Milvus repository for aspect-level semantic vectors."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)

from backend.app.core.settings import settings
from pipelines.config.targets import TARGETS

UPSERT_BATCH_SIZE = 500
INDEX_CONFIGS: dict[str, dict[str, Any]] = {
    "vector": {
        "index_type": "HNSW",
        "metric_type": "COSINE",
        "params": {"M": 16, "efConstruction": 256},
    },
    # Milvus 2.3 requires the case-sensitive value "Trie" for VARCHAR fields.
    "sku_code": {"index_type": "Trie"},
    "aspect_label": {"index_type": "Trie"},
    "sentiment": {"index_type": "Trie"},
    # STL_SORT is the supported sorted scalar index for numeric fields.
    "week_id": {"index_type": "STL_SORT"},
    "quality_score": {"index_type": "STL_SORT"},
}


@dataclass(frozen=True)
class MilvusRecord:
    id: UUID
    vector: list[float]
    sku_code: str
    aspect_label: str
    sentiment: str
    week_id: int
    quality_score: float


@dataclass(frozen=True)
class SearchResult:
    id: UUID
    score: float
    metadata: dict[str, Any]


def _quote(value: str) -> str:
    """Escape a string literal used by Milvus' scalar expression parser."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _partition_name(sku_code: str) -> str:
    """Convert a SKU slug to a Milvus-safe, deterministic partition name."""
    if sku_code not in TARGETS:
        raise ValueError(f"Unknown sku_code: {sku_code}")
    return f"sku_{sku_code.replace('-', '_')}"


class MilvusRepository:
    def __init__(
        self,
        host: str = settings.milvus_host,
        port: int = settings.milvus_port,
        collection_name: str = settings.milvus_collection_name,
        collection_factory: Callable[..., Any] = Collection,
        dimension: int | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self.collection_name = collection_name
        self._collection_factory = collection_factory
        self._dimension = (
            settings.embedding_dimensions if dimension is None else dimension
        )
        if self._dimension <= 0:
            raise ValueError("EMBEDDING_DIMENSIONS must be positive")

    def connect(self) -> None:
        connections.connect(alias="default", host=self._host, port=str(self._port))

    def setup_collection(self) -> Any:
        """Create the collection, indexes, and locked SKU partitions idempotently."""
        self.connect()
        if utility.has_collection(self.collection_name):
            collection = self._collection_factory(self.collection_name)
        else:
            fields = [
                FieldSchema("id", DataType.VARCHAR, is_primary=True, max_length=36),
                FieldSchema("vector", DataType.FLOAT_VECTOR, dim=self._dimension),
                FieldSchema("sku_code", DataType.VARCHAR, max_length=50),
                FieldSchema("aspect_label", DataType.VARCHAR, max_length=50),
                FieldSchema("sentiment", DataType.VARCHAR, max_length=20),
                FieldSchema("week_id", DataType.INT64),
                FieldSchema("quality_score", DataType.FLOAT),
            ]
            collection = self._collection_factory(
                self.collection_name,
                schema=CollectionSchema(fields, description="Aspect mention vectors"),
            )
        self._validate_collection_dimension(collection)
        self._ensure_indexes(collection)
        existing = {partition.name for partition in collection.partitions}
        for sku_code in TARGETS:
            partition_name = _partition_name(sku_code)
            if partition_name not in existing:
                collection.create_partition(partition_name)
        return collection

    def _validate_collection_dimension(self, collection: Any) -> None:
        vector_field = next(
            (field for field in collection.schema.fields if field.name == "vector"),
            None,
        )
        if vector_field is None:
            raise RuntimeError(
                f"Milvus collection '{self.collection_name}' has no vector field"
            )
        actual_dimension = int(vector_field.params.get("dim", 0))
        if actual_dimension != self._dimension:
            raise RuntimeError(
                "Milvus vector dimension mismatch: "
                f"collection='{self.collection_name}', "
                f"EMBEDDING_DIMENSIONS={self._dimension}, "
                f"collection_dimension={actual_dimension}. Refusing to write; "
                "use a compatible collection instead."
            )

    @staticmethod
    def _ensure_indexes(collection: Any) -> None:
        """Create missing indexes, including after an interrupted initial setup."""
        indexed_fields = {index.field_name for index in collection.indexes}
        for field_name, index_params in INDEX_CONFIGS.items():
            if field_name not in indexed_fields:
                collection.create_index(field_name, index_params)

    def upsert_vectors(self, records: Sequence[MilvusRecord]) -> int:
        """Upsert records per SKU partition in batches of 500."""
        if not records:
            return 0
        collection = self.setup_collection()
        inserted = 0
        by_sku: dict[str, list[MilvusRecord]] = {}
        for record in records:
            self._validate_record(record)
            by_sku.setdefault(record.sku_code, []).append(record)
        for sku_code, sku_records in by_sku.items():
            for offset in range(0, len(sku_records), UPSERT_BATCH_SIZE):
                batch = sku_records[offset : offset + UPSERT_BATCH_SIZE]
                collection.upsert(
                    [
                        {
                            "id": str(record.id),
                            "vector": record.vector,
                            "sku_code": record.sku_code,
                            "aspect_label": record.aspect_label,
                            "sentiment": record.sentiment,
                            "week_id": record.week_id,
                            "quality_score": record.quality_score,
                        }
                        for record in batch
                    ],
                    partition_name=_partition_name(sku_code),
                )
                inserted += len(batch)
        collection.flush()
        return inserted

    def search(
        self,
        query_vector: Sequence[float],
        sku_code: str | None = None,
        aspect_label: str | None = None,
        sentiment: str | None = None,
        week_id_range: tuple[int, int] | None = None,
        quality_threshold: float | None = None,
        top_k: int = 20,
    ) -> list[SearchResult]:
        if len(query_vector) != self._dimension:
            raise ValueError(f"query_vector must have {self._dimension} dimensions")
        effective_threshold = (
            settings.aspect_quality_threshold
            if quality_threshold is None
            else quality_threshold
        )
        if not 0 <= effective_threshold <= 1:
            raise ValueError("quality_threshold must be between 0 and 1")
        if top_k < 1:
            raise ValueError("top_k must be positive")
        if sentiment is not None and sentiment not in {
            "positive",
            "negative",
            "neutral",
        }:
            raise ValueError("Unsupported sentiment")
        if week_id_range is not None and week_id_range[0] > week_id_range[1]:
            raise ValueError("week_id_range start must not exceed end")

        expressions = [f"quality_score >= {effective_threshold}"]
        if sku_code:
            expressions.append(f"sku_code == {_quote(sku_code)}")
        if aspect_label:
            expressions.append(f"aspect_label == {_quote(aspect_label)}")
        if sentiment:
            expressions.append(f"sentiment == {_quote(sentiment)}")
        if week_id_range:
            expressions.extend(
                (f"week_id >= {week_id_range[0]}", f"week_id <= {week_id_range[1]}")
            )
        collection = self.setup_collection()
        collection.load()
        results = collection.search(
            data=[list(query_vector)],
            anns_field="vector",
            param={"metric_type": "COSINE", "params": {"ef": max(64, top_k)}},
            limit=top_k,
            expr=" and ".join(expressions),
            output_fields=[
                "sku_code",
                "aspect_label",
                "sentiment",
                "week_id",
                "quality_score",
            ],
            partition_names=[_partition_name(sku_code)] if sku_code else None,
        )
        return [
            SearchResult(
                id=UUID(str(hit.id)),
                score=float(hit.score),
                metadata={
                    field: hit.entity.get(field)
                    for field in (
                        "sku_code",
                        "aspect_label",
                        "sentiment",
                        "week_id",
                        "quality_score",
                    )
                },
            )
            for hit in results[0]
        ]

    def delete_by_sku(self, sku_code: str) -> None:
        if sku_code not in TARGETS:
            raise ValueError(f"Unknown sku_code: {sku_code}")
        collection = self.setup_collection()
        collection.delete(
            f"sku_code == {_quote(sku_code)}",
            partition_name=_partition_name(sku_code),
        )
        collection.flush()

    def _validate_record(self, record: MilvusRecord) -> None:
        if record.sku_code not in TARGETS:
            raise ValueError(f"Unknown sku_code: {record.sku_code}")
        if len(record.vector) != self._dimension:
            raise ValueError(f"vector must have {self._dimension} dimensions")
        if record.sentiment not in {"positive", "negative", "neutral"}:
            raise ValueError("Unsupported sentiment")
        if not 0 <= record.quality_score <= 1:
            raise ValueError("quality_score must be between 0 and 1")
