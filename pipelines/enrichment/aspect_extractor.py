"""Batch LLM aspect extraction with deterministic input/output guardrails."""

import asyncio
import json
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError

from backend.app.db.repositories.schemas import AspectMentionCreate, DocumentRead
from pipelines.enrichment.prompts import ASPECT_LABELS, SYSTEM_PROMPT, build_user_prompt
from pipelines.enrichment.quality_scorer import score_quality

MAX_BATCH_SIZE = 10
MAX_MENTION_LENGTH = 60
MAX_CONTEXT_LENGTH = 200
MAX_RETRIES = 2
LOGISTICS_KEYWORDS = {"shipping", "arrived", "package", "delivery", "fedex", "ups"}
PRODUCT_KEYWORDS = {
    "battery", "power", "charge", "charging", "solar", "watt", "port", "fan",
    "noise", "app", "display", "quality", "capacity", "inverter", "outlet",
}


class ChatCompletions(Protocol):
    async def create(self, **kwargs: Any) -> Any: ...


class AsyncChatClient(Protocol):
    chat: Any


class ExtractedAspect(BaseModel):
    aspect_label: str
    sentiment: str
    confidence: float = Field(ge=0, le=1)
    mention_text: str = Field(min_length=1, max_length=MAX_MENTION_LENGTH)
    context_window: str | None = Field(default=None, max_length=MAX_CONTEXT_LENGTH)


class ExtractedDocument(BaseModel):
    document_id: UUID
    aspects: list[ExtractedAspect] = Field(default_factory=list, max_length=3)


class ExtractionPayload(BaseModel):
    documents: list[ExtractedDocument]


@dataclass(frozen=True)
class PreparedDocument:
    document_id: UUID
    body: str


@dataclass(frozen=True)
class BatchExtractionResult:
    documents: list[ExtractedDocument]
    skipped_document_ids: list[UUID]


class ExtractionResponseError(ValueError):
    """Raised after an LLM response cannot satisfy the structured contract."""


def _fallback_detect_language(text: str) -> str:
    """Conservative fallback used only when the declared langdetect dependency is absent."""
    letters = sum(char.isascii() and char.isalpha() for char in text)
    return "en" if letters >= max(10, len(text) * 0.45) else "unknown"


def detect_english(text: str) -> bool:
    try:
        from langdetect import DetectorFactory, detect

        DetectorFactory.seed = 0
        return detect(text) == "en"
    except ImportError:
        return _fallback_detect_language(text) == "en"
    except Exception:
        return False


def prepare_document(
    document: DocumentRead, language_detector: Callable[[str], bool] = detect_english
) -> PreparedDocument | None:
    """Filter noise and cap long reviews before an LLM request."""
    body = document.body.strip()
    if len(body) < 30:
        return None
    lowered = body.lower()
    has_logistics = any(keyword in lowered for keyword in LOGISTICS_KEYWORDS)
    has_product_content = any(keyword in lowered for keyword in PRODUCT_KEYWORDS)
    if has_logistics and not has_product_content:
        return None
    if not language_detector(body):
        return None
    if len(body) > 3000:
        body = _truncate_at_sentence(body, 2000)
    return PreparedDocument(document_id=document.id, body=body)


def _truncate_at_sentence(text: str, limit: int) -> str:
    shortened = text[:limit]
    endings = [match.end() for match in re.finditer(r"[.!?](?:\s|$)", shortened)]
    return shortened[: endings[-1]].strip() if endings else shortened.strip()


class AspectExtractor:
    def __init__(
        self,
        client: AsyncChatClient,
        model: str = "gpt-4o-mini",
        language_detector: Callable[[str], bool] = detect_english,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._client = client
        self._model = model
        self._language_detector = language_detector
        self._sleep = sleep

    async def extract(self, documents: Sequence[DocumentRead]) -> BatchExtractionResult:
        if len(documents) > MAX_BATCH_SIZE:
            raise ValueError(f"A batch can contain at most {MAX_BATCH_SIZE} documents")
        prepared = [
            candidate
            for document in documents
            if (candidate := prepare_document(document, self._language_detector)) is not None
        ]
        prepared_ids = {document.document_id for document in prepared}
        skipped = [document.id for document in documents if document.id not in prepared_ids]
        if not prepared:
            return BatchExtractionResult(documents=[], skipped_document_ids=skipped)

        valid_documents = await self._request_with_retry(prepared)
        return BatchExtractionResult(documents=valid_documents, skipped_document_ids=skipped)

    async def _request_with_retry(
        self, documents: Sequence[PreparedDocument]
    ) -> list[ExtractedDocument]:
        request_documents = [
            {"document_id": str(document.document_id), "body": document.body}
            for document in documents
        ]
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    temperature=0,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": build_user_prompt(request_documents)},
                    ],
                )
                content = response.choices[0].message.content
                if not content:
                    raise ExtractionResponseError("LLM returned an empty response")
                decoded = json.loads(content)
                if not isinstance(decoded, dict):
                    raise ExtractionResponseError("LLM response must be a JSON object")
                return self._validate_payload(decoded, documents)
            except (
                json.JSONDecodeError,
                AttributeError,
                IndexError,
                TypeError,
                ExtractionResponseError,
            ) as error:
                last_error = error
            if attempt < MAX_RETRIES:
                await self._sleep(2**attempt)
        raise ExtractionResponseError("Invalid LLM response after retries") from last_error

    @staticmethod
    def _validate_payload(
        payload: dict[str, Any], prepared: Sequence[PreparedDocument]
    ) -> list[ExtractedDocument]:
        prepared_by_id = {document.document_id: document.body for document in prepared}
        try:
            parsed = ExtractionPayload.model_validate(payload)
        except ValidationError as error:
            raise ExtractionResponseError("LLM response does not match extraction schema") from error

        seen_ids: set[UUID] = set()
        valid_documents: list[ExtractedDocument] = []
        for extracted in parsed.documents:
            if extracted.document_id not in prepared_by_id or extracted.document_id in seen_ids:
                raise ExtractionResponseError("LLM returned an unknown or duplicate document ID")
            seen_ids.add(extracted.document_id)
            body = prepared_by_id[extracted.document_id]
            for aspect in extracted.aspects:
                if aspect.aspect_label not in ASPECT_LABELS:
                    raise ExtractionResponseError("LLM returned an unsupported aspect label")
                if aspect.sentiment not in {"positive", "negative", "neutral"}:
                    raise ExtractionResponseError("LLM returned an unsupported sentiment")
                if aspect.mention_text not in body:
                    raise ExtractionResponseError("mention_text must be a direct review excerpt")
            valid_documents.append(extracted)
        if seen_ids != set(prepared_by_id):
            raise ExtractionResponseError("LLM response is missing one or more documents")
        return valid_documents


def build_aspect_mentions(
    documents: Sequence[DocumentRead], extraction: BatchExtractionResult
) -> list[AspectMentionCreate]:
    """Convert validated LLM output to repository-ready records with quality scores."""
    documents_by_id = {document.id: document for document in documents}
    mentions: list[AspectMentionCreate] = []
    for extracted_document in extraction.documents:
        document = documents_by_id[extracted_document.document_id]
        for aspect in extracted_document.aspects:
            quality = score_quality(
                mention_text=aspect.mention_text,
                context_window=aspect.context_window,
                aspect_label=aspect.aspect_label,
                sentiment=aspect.sentiment,
                confidence=aspect.confidence,
                platform=document.platform,
                rating=document.rating,
            )
            mentions.append(
                AspectMentionCreate(
                    document_id=document.id,
                    sku_code=document.sku_code,
                    week_id=document.week_id,
                    aspect_label=aspect.aspect_label,
                    sentiment=aspect.sentiment,
                    sentiment_score={"positive": 1.0, "negative": -1.0, "neutral": 0.0}[aspect.sentiment],
                    confidence=aspect.confidence,
                    mention_text=aspect.mention_text,
                    context_window=aspect.context_window,
                    quality_score=quality.score,
                )
            )
    return mentions
