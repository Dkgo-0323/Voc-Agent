"""Traceable semantic retrieval over Milvus and PostgreSQL evidence."""

from __future__ import annotations

import asyncio
from datetime import date
from time import perf_counter
from typing import Any, Protocol
from uuid import UUID

from backend.app.agent.schemas import (
    AnswerCitation,
    ExpandedSourceMetadata,
    RagRetrievalPayload,
    RagToolArguments,
    RagToolResult,
    RetrievedEvidence,
    ToolError,
    ToolExecutionMetadata,
    ToolName,
    ToolStatus,
    ToolWarning,
)
from backend.app.core.settings import settings
from backend.app.db.repositories.schemas import RetrievedEvidenceRow, SkuMetadata
from pipelines.config.targets import LOCKED_SKU_CODES
from pipelines.embedding.milvus_repo import SearchResult
from pipelines.enrichment.prompts import ASPECT_LABELS


class EvidenceRepositoryProtocol(Protocol):
    async def get_enabled_skus(self) -> list[SkuMetadata]: ...

    async def hydrate_mentions(
        self, mention_ids: list[UUID], *, quality_threshold: float
    ) -> list[RetrievedEvidenceRow]: ...


class QueryEmbedderProtocol(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class MilvusSearchProtocol(Protocol):
    def search(self, query_vector: list[float], **kwargs: Any) -> list[SearchResult]: ...


def _is_valid_iso_week(week_id: int) -> bool:
    year, week = divmod(week_id, 100)
    try:
        date.fromisocalendar(year, week, 1)
    except ValueError:
        return False
    return True


class RagRetrievalService:
    def __init__(
        self,
        repository: EvidenceRepositoryProtocol,
        embedder: QueryEmbedderProtocol,
        milvus_repository: MilvusSearchProtocol,
        *,
        max_top_k: int = settings.max_rag_top_k,
        quality_threshold: float = settings.aspect_quality_threshold,
    ) -> None:
        if max_top_k < 1:
            raise ValueError("max_top_k must be positive")
        if not 0 <= quality_threshold <= 1:
            raise ValueError("quality_threshold must be between 0 and 1")
        self._repository = repository
        self._embedder = embedder
        self._milvus_repository = milvus_repository
        self._max_top_k = max_top_k
        self._quality_threshold = quality_threshold

    async def execute(self, arguments: RagToolArguments) -> RagToolResult:
        started = perf_counter()
        normalized_args = arguments.model_copy(update={"query": arguments.query.strip()})
        if normalized_args.top_k > self._max_top_k:
            return self._error(
                normalized_args,
                started,
                code="top_k_exceeds_limit",
                message=f"top_k must not exceed {self._max_top_k}.",
                details={"requested": normalized_args.top_k, "maximum": self._max_top_k},
            )
        if (
            normalized_args.aspect_label is not None
            and normalized_args.aspect_label not in ASPECT_LABELS
        ):
            return self._error(
                normalized_args,
                started,
                code="invalid_aspect",
                message="Aspect label is outside the enrichment taxonomy.",
                details={"aspect_label": normalized_args.aspect_label},
            )
        if normalized_args.week_range is not None:
            invalid_weeks = [
                week_id
                for week_id in (
                    normalized_args.week_range.start_week_id,
                    normalized_args.week_range.end_week_id,
                )
                if not _is_valid_iso_week(week_id)
            ]
            if invalid_weeks:
                return self._error(
                    normalized_args,
                    started,
                    code="invalid_week_range",
                    message="Week range contains an invalid ISO week identifier.",
                    details={"week_ids": ",".join(map(str, invalid_weeks))},
                )

        try:
            enabled_skus = await self._repository.get_enabled_skus()
        except Exception:
            return self._error(
                normalized_args,
                started,
                code="rag_hydration_failed",
                message="Evidence metadata is temporarily unavailable.",
                retryable=True,
            )
        enabled_locked = {
            sku.sku_code: sku
            for sku in enabled_skus
            if sku.sku_code in LOCKED_SKU_CODES
        }
        requested_codes = normalized_args.sku_codes or sorted(enabled_locked)
        normalized_args = normalized_args.model_copy(
            update={"sku_codes": requested_codes}
        )
        invalid_codes = [code for code in requested_codes if code not in enabled_locked]
        if invalid_codes:
            return self._error(
                normalized_args,
                started,
                code="unknown_or_disabled_sku",
                message="One or more SKU codes are not locked and dashboard-enabled.",
                details={"sku_codes": ",".join(invalid_codes)},
            )
        if not requested_codes:
            return self._error(
                normalized_args,
                started,
                code="no_enabled_skus",
                message="No locked dashboard-enabled SKUs are available.",
            )

        try:
            vectors = await self._embedder.embed([normalized_args.query])
            if len(vectors) != 1:
                raise RuntimeError("Embedding provider returned an incomplete result")
            query_vector = vectors[0]
        except Exception as exc:
            return self._error(
                normalized_args,
                started,
                code=(
                    "rag_embedding_timeout"
                    if isinstance(exc, TimeoutError)
                    else "rag_embedding_failed"
                ),
                message=(
                    "The semantic query embedding timed out."
                    if isinstance(exc, TimeoutError)
                    else "The semantic query could not be embedded."
                ),
                retryable=True,
            )

        week_range = None
        if normalized_args.week_range is not None:
            week_range = (
                normalized_args.week_range.start_week_id,
                normalized_args.week_range.end_week_id,
            )
        hits_by_id: dict[UUID, SearchResult] = {}
        try:
            for sku_code in requested_codes:
                hits = await asyncio.to_thread(
                    self._milvus_repository.search,
                    query_vector,
                    sku_code=sku_code,
                    aspect_label=normalized_args.aspect_label,
                    sentiment=(
                        normalized_args.sentiment.value
                        if normalized_args.sentiment is not None
                        else None
                    ),
                    week_id_range=week_range,
                    quality_threshold=self._quality_threshold,
                    top_k=normalized_args.top_k,
                )
                for hit in hits:
                    existing = hits_by_id.get(hit.id)
                    if existing is None or hit.score > existing.score:
                        hits_by_id[hit.id] = hit
        except Exception:
            return self._error(
                normalized_args,
                started,
                code="rag_vector_search_failed",
                message="Semantic evidence search is temporarily unavailable.",
                retryable=True,
            )

        ranked_hits = sorted(
            hits_by_id.values(), key=lambda hit: (-hit.score, str(hit.id))
        )[: normalized_args.top_k]
        if not ranked_hits:
            return self._empty(normalized_args, started)

        try:
            hydrated_rows = await self._repository.hydrate_mentions(
                [hit.id for hit in ranked_hits],
                quality_threshold=self._quality_threshold,
            )
        except Exception:
            return self._error(
                normalized_args,
                started,
                code="rag_hydration_failed",
                message="Source evidence could not be hydrated.",
                retryable=True,
            )

        rows_by_id = {row.mention_id: row for row in hydrated_rows}
        evidence: list[RetrievedEvidence] = []
        warnings: list[ToolWarning] = []
        for hit in ranked_hits:
            row = rows_by_id.get(hit.id)
            if row is None:
                warnings.append(self._provenance_warning("unhydrated_vector", hit.id))
                continue
            if not self._metadata_matches(hit, row):
                warnings.append(self._provenance_warning("provenance_mismatch", hit.id))
                continue
            if not self._matches_request(normalized_args, row):
                warnings.append(self._provenance_warning("filter_mismatch", hit.id))
                continue
            if row.mention_text not in row.review_text:
                warnings.append(self._provenance_warning("invalid_exact_evidence", hit.id))
                continue
            evidence.append(self._to_evidence(hit, row))

        if not evidence:
            return self._empty(normalized_args, started, warnings=warnings)
        payload = RagRetrievalPayload(
            query=normalized_args.query,
            retrieved_count=len(evidence),
            evidence=evidence,
        )
        return RagToolResult(
            status=(
                ToolStatus.PARTIAL
                if len(evidence) != len(ranked_hits)
                else ToolStatus.SUCCESS
            ),
            tool_name=ToolName.RAG,
            normalized_args=normalized_args,
            warnings=warnings,
            execution=self._execution(started, len(evidence)),
            payload=payload,
        )

    def _metadata_matches(
        self, hit: SearchResult, row: RetrievedEvidenceRow
    ) -> bool:
        metadata = hit.metadata
        quality = metadata.get("quality_score")
        return (
            metadata.get("sku_code") == row.sku_code
            and metadata.get("aspect_label") == row.aspect_label
            and metadata.get("sentiment") == row.sentiment
            and metadata.get("week_id") == row.week_id
            and quality is not None
            and float(quality) >= self._quality_threshold
            and abs(float(quality) - row.quality_score) <= 1e-5
        )

    @staticmethod
    def _matches_request(
        arguments: RagToolArguments, row: RetrievedEvidenceRow
    ) -> bool:
        if row.sku_code not in arguments.sku_codes:
            return False
        if (
            arguments.aspect_label is not None
            and row.aspect_label != arguments.aspect_label
        ):
            return False
        if (
            arguments.sentiment is not None
            and row.sentiment != arguments.sentiment.value
        ):
            return False
        return arguments.week_range is None or (
            arguments.week_range.start_week_id
            <= row.week_id
            <= arguments.week_range.end_week_id
        )

    @staticmethod
    def _to_evidence(
        hit: SearchResult, row: RetrievedEvidenceRow
    ) -> RetrievedEvidence:
        source = ExpandedSourceMetadata(
            document_id=row.document_id,
            sku_code=row.sku_code,
            platform=row.platform,
            published_at=row.published_at,
            source_url=row.source_url,
            title=row.title,
            rating=row.rating,
            review_text=row.review_text,
        )
        return RetrievedEvidence(
            mention_id=row.mention_id,
            document_id=row.document_id,
            sku_code=row.sku_code,
            aspect_label=row.aspect_label,
            sentiment=row.sentiment,
            week_id=row.week_id,
            mention_text=row.mention_text,
            context_window=row.context_window,
            quality_score=row.quality_score,
            similarity_score=hit.score,
            source=source,
        )

    @staticmethod
    def _provenance_warning(code: str, mention_id: UUID) -> ToolWarning:
        return ToolWarning(
            code=code,
            message="A vector result was excluded because provenance could not be verified.",
            details={"mention_id": str(mention_id)},
        )

    @staticmethod
    def _execution(started: float, count: int) -> ToolExecutionMetadata:
        return ToolExecutionMetadata(
            duration_ms=max(0, round((perf_counter() - started) * 1000)),
            result_count=count,
        )

    @classmethod
    def _empty(
        cls,
        arguments: RagToolArguments,
        started: float,
        *,
        warnings: list[ToolWarning] | None = None,
    ) -> RagToolResult:
        return RagToolResult(
            status=ToolStatus.EMPTY,
            tool_name=ToolName.RAG,
            normalized_args=arguments,
            warnings=warnings or [],
            execution=cls._execution(started, 0),
        )

    @classmethod
    def _error(
        cls,
        arguments: RagToolArguments,
        started: float,
        *,
        code: str,
        message: str,
        retryable: bool = False,
        details: dict[str, str | int | float | bool | None] | None = None,
    ) -> RagToolResult:
        return RagToolResult(
            status=ToolStatus.ERROR,
            tool_name=ToolName.RAG,
            normalized_args=arguments,
            execution=cls._execution(started, 0),
            error=ToolError(
                code=code,
                message=message,
                retryable=retryable,
                details=details or {},
            ),
        )


def build_answer_citations(
    retrieved_evidence: list[RetrievedEvidence], cited_mention_ids: list[UUID]
) -> list[AnswerCitation]:
    """Select only explicitly cited evidence and reject unknown provenance IDs."""
    if len(cited_mention_ids) != len(set(cited_mention_ids)):
        raise ValueError("cited_mention_ids must not contain duplicates")
    evidence_by_id = {item.mention_id: item for item in retrieved_evidence}
    unknown_ids = [item for item in cited_mention_ids if item not in evidence_by_id]
    if unknown_ids:
        raise ValueError(
            "Citations reference evidence that was not retrieved: "
            + ", ".join(map(str, unknown_ids))
        )
    return [
        AnswerCitation(
            mention_id=evidence_by_id[mention_id].mention_id,
            document_id=evidence_by_id[mention_id].document_id,
            evidence_preview=evidence_by_id[mention_id].mention_text,
            sku_code=evidence_by_id[mention_id].sku_code,
            aspect_label=evidence_by_id[mention_id].aspect_label,
            sentiment=evidence_by_id[mention_id].sentiment,
            week_id=evidence_by_id[mention_id].week_id,
            source=evidence_by_id[mention_id].source,
        )
        for mention_id in cited_mention_ids
    ]
