"""Batch LLM aspect extraction with deterministic input/output guardrails."""

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)
from pydantic import BaseModel, Field, ValidationError

from backend.app.db.repositories.schemas import AspectMentionCreate, DocumentRead
from pipelines.enrichment.prompts import ASPECT_LABELS, SYSTEM_PROMPT, build_user_prompt
from pipelines.enrichment.quality_scorer import score_quality

MAX_BATCH_SIZE = 10
MAX_MENTION_LENGTH = 60
MAX_CONTEXT_LENGTH = 200
MAX_RETRIES = 2
logger = logging.getLogger(__name__)
LOGISTICS_KEYWORDS = {"shipping", "arrived", "package", "delivery", "fedex", "ups"}
PRODUCT_KEYWORDS = {
    "battery",
    "power",
    "charge",
    "charging",
    "solar",
    "watt",
    "port",
    "fan",
    "noise",
    "app",
    "display",
    "quality",
    "capacity",
    "inverter",
    "outlet",
}
GENERIC_MENTION_PATTERNS = (
    re.compile(r"^(?:a\s+)?(?:great|good|awesome|excellent|nice)(?:\s+product)?$", re.I),
    re.compile(r"^(?:i\s+)?love\s+it$", re.I),
    re.compile(r"^so\s+far[, ]+so\s+good$", re.I),
    re.compile(r"^(?:i(?:'m| am)\s+)?happy\s+with\s+(?:it|the\s+purchase)$", re.I),
    re.compile(r"^(?:it\s+)?works?\s+(?:very\s+)?well$", re.I),
    re.compile(r"^(?:i(?:'ve| have)?\s+)?used\s+(?:it\s+)?(?:a\s+)?few\s+times$", re.I),
    re.compile(r"^(?:this|it)\s+feels\s+like\s+a\s+quality\s+unit$", re.I),
)
LABEL_EVIDENCE_PATTERNS = {
    "build_quality": re.compile(
        r"\b(?:build|built|well[ -]?made|material(?:s)?|durab(?:le|ility)|"
        r"sturd(?:y|iness)|solid|construction|workmanship|casing|housing|"
        r"enclosure|flimsy|crack(?:ed|ing)?|broken|defect(?:ive)?|damage[ds]?)\b",
        re.I,
    ),
    "customer_service": re.compile(
        r"\b(?:customer\s+)?(?:support|service)|\breturns?\b|\brefund(?:ed|s)?\b|"
        r"\breplacement\b|\bcontact(?:ed|ing)?\s+(?:the\s+)?company\b",
        re.I,
    ),
    "price_value": re.compile(
        r"[$€£]\s*\d|\b\d+(?:\.\d+)?\s*(?:dollars?|usd|eur|gbp)\b|"
        r"\bprice[dy]?\b|\bcost\b|\baffordab(?:le|ility)\b|\bexpensive\b|"
        r"\bcheap(?:er|est)?\b|\bvalue\b|\bworth\b|\bbargain\b|\bdeal\b",
        re.I,
    ),
    "setup_complexity": re.compile(
        r"\bset[ -]?up\b|\binstall(?:ation|ed|ing)?\b|\bconfigur(?:e|ed|ation|ing)\b|"
        r"\binstructions?\b|\bmanual\b|\b(?:easy|hard|difficult|simple)\s+to\s+"
        r"(?:use|operate)\b",
        re.I,
    ),
    "solar_charging": re.compile(
        r"\bsolar\b|\bpanel(?:s)?\b|\bphotovoltaic\b|\bpv\b",
        re.I,
    ),
    "home_backup_use": re.compile(
        r"\bhome\b|\bhouse(?:hold)?\b|\boutage\b|\bblackout\b|"
        r"\bemergency\s+power\b|\bbackup\s+(?:power|use|for)\b",
        re.I,
    ),
}
SCENARIO_LABELS = {"van_rv_use", "camping_outdoor_use", "home_backup_use"}
SCENARIO_EVIDENCE_PATTERNS = {
    "van_rv_use": re.compile(r"\bvan\b|\brv\b|\bcampervan\b|\bvehicle\b|\bcar\b|\broad trip\b", re.I),
    "camping_outdoor_use": re.compile(r"\bcamp(?:ing|site)?\b|\boutdoors?\b|\btent\b|\bhiking\b", re.I),
    "home_backup_use": LABEL_EVIDENCE_PATTERNS["home_backup_use"],
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


class RawExtractedDocument(BaseModel):
    """Envelope fields validated before each mention is checked independently."""

    document_id: UUID
    aspects: list[Any] = Field(default_factory=list)


class ExtractionPayload(BaseModel):
    documents: list[RawExtractedDocument]


@dataclass(frozen=True)
class PreparedDocument:
    document_id: UUID
    body: str


@dataclass(frozen=True)
class BatchExtractionResult:
    documents: list[ExtractedDocument]
    skipped_document_ids: list[UUID]
    failed_document_errors: dict[UUID, str] = field(default_factory=dict)


class ExtractionResponseError(ValueError):
    """Raised after an LLM response cannot satisfy the structured contract."""

    def __init__(self, message: str, raw_response: str | None = None) -> None:
        super().__init__(message)
        self.raw_response = raw_response


def _exact_excerpt(candidate: str, body: str) -> str | None:
    """Accept only an exact, character-for-character contiguous review excerpt."""
    return candidate if candidate in body else None


def _evidence_window(mention_text: str, body: str) -> str:
    start = body.find(mention_text)
    surrounding_budget = max(0, MAX_CONTEXT_LENGTH - len(mention_text))
    left_budget = surrounding_budget // 2
    right_budget = surrounding_budget - left_budget
    left = max(0, start - left_budget)
    right = min(len(body), start + len(mention_text) + right_budget)
    return body[left:right]


def _evidence_rejection_reason(aspect: ExtractedAspect, body: str) -> str | None:
    normalized = aspect.mention_text.strip().strip(".!?,;:")
    if any(pattern.fullmatch(normalized) for pattern in GENERIC_MENTION_PATTERNS):
        return "mention_text is generic praise or vague usage"
    evidence = _evidence_window(aspect.mention_text, body)
    required = LABEL_EVIDENCE_PATTERNS.get(aspect.aspect_label)
    if required is not None and required.search(evidence) is None:
        return f"insufficient explicit evidence for {aspect.aspect_label}"
    if aspect.aspect_label in SCENARIO_LABELS:
        pattern = SCENARIO_EVIDENCE_PATTERNS[aspect.aspect_label]
        if pattern.search(evidence) is None:
            return f"insufficient explicit evidence for {aspect.aspect_label}"
    return None


def _deduplicate_scenarios(
    aspects: list[tuple[int, ExtractedAspect]], body: str
) -> tuple[list[tuple[int, ExtractedAspect]], list[tuple[int, str]]]:
    """Keep one scenario label when candidates reuse the same semantic evidence."""
    kept: list[tuple[int, ExtractedAspect]] = []
    rejected: list[tuple[int, str]] = []
    scenario_windows: list[tuple[str, str]] = []
    for index, aspect in aspects:
        if aspect.aspect_label not in SCENARIO_LABELS:
            kept.append((index, aspect))
            continue
        window = _evidence_window(aspect.mention_text, body)
        overlap = next(
            (
                label
                for label, prior_window in scenario_windows
                if window == prior_window
                or aspect.mention_text in prior_window
                or prior_window.find(aspect.mention_text) >= 0
            ),
            None,
        )
        if overlap is not None:
            rejected.append(
                (index, f"scenario evidence overlaps existing {overlap} mention")
            )
            continue
        scenario_windows.append((aspect.aspect_label, window))
        kept.append((index, aspect))
    return kept, rejected


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
        model: str = "glm-4-flashx-250414",
        max_tokens: int = 4096,
        language_detector: Callable[[str], bool] = detect_english,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        request_extra_body: dict[str, Any] | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens
        self._language_detector = language_detector
        self._sleep = sleep
        self._request_extra_body = dict(request_extra_body or {})

    async def extract(self, documents: Sequence[DocumentRead]) -> BatchExtractionResult:
        if len(documents) > MAX_BATCH_SIZE:
            raise ValueError(f"A batch can contain at most {MAX_BATCH_SIZE} documents")
        prepared = [
            candidate
            for document in documents
            if (candidate := prepare_document(document, self._language_detector))
            is not None
        ]
        prepared_ids = {document.document_id for document in prepared}
        skipped = [
            document.id for document in documents if document.id not in prepared_ids
        ]
        if not prepared:
            return BatchExtractionResult(documents=[], skipped_document_ids=skipped)

        valid_documents, failed_document_errors = await self._request_with_retry(
            prepared
        )
        return BatchExtractionResult(
            documents=valid_documents,
            skipped_document_ids=skipped,
            failed_document_errors=failed_document_errors,
        )

    async def _request_with_retry(
        self,
        documents: Sequence[PreparedDocument],
        *,
        allow_single_document_fallback: bool = True,
    ) -> tuple[list[ExtractedDocument], dict[UUID, str]]:
        request_documents = [
            {"document_id": str(document.document_id), "body": document.body}
            for document in documents
        ]
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                request: dict[str, Any] = {
                    "model": self._model,
                    "temperature": 0,
                    "max_tokens": self._max_tokens,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": build_user_prompt(request_documents),
                        },
                    ],
                }
                if self._request_extra_body:
                    request["extra_body"] = self._request_extra_body
                response = await self._client.chat.completions.create(**request)
                content = response.choices[0].message.content
                if not content:
                    raise ExtractionResponseError("LLM returned an empty response")
                decoded = json.loads(content)
                if not isinstance(decoded, dict):
                    raise ExtractionResponseError("LLM response must be a JSON object")
                try:
                    return self._validate_payload(decoded, documents)
                except ExtractionResponseError as error:
                    error.raw_response = content
                    raise
            except (
                json.JSONDecodeError,
                AttributeError,
                IndexError,
                TypeError,
                ExtractionResponseError,
                APIConnectionError,
                APITimeoutError,
                InternalServerError,
                RateLimitError,
            ) as error:
                last_error = error
            if attempt < MAX_RETRIES:
                await self._sleep(2**attempt)
        if (
            allow_single_document_fallback
            and len(documents) > 1
            and isinstance(
                last_error,
                (
                    json.JSONDecodeError,
                    AttributeError,
                    IndexError,
                    TypeError,
                    ExtractionResponseError,
                ),
            )
        ):
            return await self._request_documents_individually(documents, last_error)
        raw_response = (
            last_error.raw_response
            if isinstance(last_error, ExtractionResponseError)
            else None
        )
        raise ExtractionResponseError(
            "Invalid LLM response after retries", raw_response=raw_response
        ) from last_error

    async def _request_documents_individually(
        self,
        documents: Sequence[PreparedDocument],
        batch_error: Exception,
    ) -> tuple[list[ExtractedDocument], dict[UUID, str]]:
        """Isolate a protocol-invalid batch without weakening ID validation."""
        valid_documents: list[ExtractedDocument] = []
        failed_document_errors: dict[UUID, str] = {}
        for document in documents:
            logger.warning(
                json.dumps(
                    {
                        "event": "extraction_single_document_fallback",
                        "document_id": str(document.document_id),
                        "reason": f"{type(batch_error).__name__}: {batch_error}",
                    },
                    ensure_ascii=False,
                )
            )
            try:
                extracted, document_errors = await self._request_with_retry(
                    [document], allow_single_document_fallback=False
                )
            except ExtractionResponseError as error:
                failed_document_errors[document.document_id] = (
                    "Single-document fallback failed after retries: "
                    f"{type(error).__name__}: {error}"
                )
                continue
            valid_documents.extend(extracted)
            failed_document_errors.update(document_errors)
        return valid_documents, failed_document_errors

    @staticmethod
    def _validate_payload(
        payload: dict[str, Any], prepared: Sequence[PreparedDocument]
    ) -> tuple[list[ExtractedDocument], dict[UUID, str]]:
        prepared_by_id = {document.document_id: document.body for document in prepared}
        try:
            parsed = ExtractionPayload.model_validate(payload)
        except ValidationError as error:
            raise ExtractionResponseError(
                "LLM response does not match extraction schema"
            ) from error

        seen_ids: set[UUID] = set()
        valid_documents: list[ExtractedDocument] = []
        failed_document_errors: dict[UUID, str] = {}
        for extracted in parsed.documents:
            if (
                extracted.document_id not in prepared_by_id
                or extracted.document_id in seen_ids
            ):
                raise ExtractionResponseError(
                    "LLM returned an unknown or duplicate document ID"
                )
            seen_ids.add(extracted.document_id)
            body = prepared_by_id[extracted.document_id]
            candidate_aspects: list[tuple[int, ExtractedAspect]] = []
            rejected_reasons: list[str] = []
            discarded_count = 0
            for index, raw_aspect in enumerate(extracted.aspects[:3]):
                context_was_too_long = False
                if isinstance(raw_aspect, dict):
                    raw_aspect = raw_aspect.copy()
                    context_window = raw_aspect.get("context_window")
                    if (
                        isinstance(context_window, str)
                        and len(context_window) > MAX_CONTEXT_LENGTH
                    ):
                        # The model has already supplied a valid mention candidate.
                        # Discard only its oversized context and rebuild bounded context
                        # from that exact review excerpt after validation below.
                        raw_aspect["context_window"] = None
                        context_was_too_long = True
                try:
                    aspect = ExtractedAspect.model_validate(raw_aspect)
                except ValidationError as error:
                    discarded_count += 1
                    rejected_reasons.append(
                        f"aspect[{index}] schema validation failed: "
                        f"{error.errors()[0]['msg']}"
                    )
                    continue
                if aspect.aspect_label not in ASPECT_LABELS:
                    discarded_count += 1
                    rejected_reasons.append(
                        f"aspect[{index}] has an unsupported aspect label"
                    )
                    continue
                if aspect.sentiment not in {"positive", "negative", "neutral"}:
                    discarded_count += 1
                    rejected_reasons.append(
                        f"aspect[{index}] has an unsupported sentiment"
                    )
                    continue
                exact_mention = _exact_excerpt(aspect.mention_text, body)
                if exact_mention is None:
                    discarded_count += 1
                    rejected_reasons.append(
                        f"aspect[{index}] mention_text is not a direct review excerpt"
                    )
                    continue
                aspect.mention_text = exact_mention
                if context_was_too_long:
                    aspect.context_window = _evidence_window(exact_mention, body)
                evidence_reason = _evidence_rejection_reason(aspect, body)
                if evidence_reason is not None:
                    discarded_count += 1
                    rejected_reasons.append(f"aspect[{index}] {evidence_reason}")
                    continue
                candidate_aspects.append((index, aspect))
            candidate_aspects, duplicate_scenarios = _deduplicate_scenarios(
                candidate_aspects, body
            )
            for index, reason in duplicate_scenarios:
                discarded_count += 1
                rejected_reasons.append(f"aspect[{index}] {reason}")
            valid_aspects = [aspect for _, aspect in candidate_aspects]
            if len(extracted.aspects) > 3:
                excess_count = len(extracted.aspects) - 3
                discarded_count += excess_count
                rejected_reasons.append(
                    f"{excess_count} mention(s) after aspect[2] exceed the limit"
                )
            if rejected_reasons:
                logger.warning(
                    json.dumps(
                        {
                            "event": "aspect_mentions_discarded",
                            "document_id": str(extracted.document_id),
                            "discarded_count": discarded_count,
                            "reasons": rejected_reasons,
                        },
                        ensure_ascii=False,
                    )
                )
            if extracted.aspects and not valid_aspects:
                failed_document_errors[extracted.document_id] = (
                    "All returned aspect mentions were invalid: "
                    + "; ".join(rejected_reasons)
                )
            valid_documents.append(
                ExtractedDocument(
                    document_id=extracted.document_id,
                    aspects=valid_aspects,
                )
            )
        if seen_ids != set(prepared_by_id):
            raise ExtractionResponseError(
                "LLM response is missing one or more documents"
            )
        return valid_documents, failed_document_errors


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
                    sentiment_score={"positive": 1.0, "negative": -1.0, "neutral": 0.0}[
                        aspect.sentiment
                    ],
                    confidence=aspect.confidence,
                    mention_text=aspect.mention_text,
                    context_window=aspect.context_window,
                    quality_score=quality.score,
                )
            )
    return mentions
