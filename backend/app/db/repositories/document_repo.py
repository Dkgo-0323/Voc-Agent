"""Data access for document processing state."""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import Document, Sku, utcnow
from backend.app.db.repositories.schemas import DocumentRead


class DocumentRepository:
    """Repository with no pipeline-specific business logic."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def fetch_unprocessed(
        self, limit: int, *, include_disabled: bool = False
    ) -> list[DocumentRead]:
        if limit <= 0:
            return []
        statement = (
            select(Document, Sku.sku_code)
            .join(Sku, Document.sku_id == Sku.id)
            .where(Document.processing_status == "raw")
            .order_by(Document.ingested_at.asc())
            .limit(limit)
        )
        if not include_disabled:
            statement = statement.where(Sku.dashboard_enabled.is_(True))
        statement = statement.add_columns(
            (Sku.brand + " " + Sku.model).label("sku_name")
        )
        result = await self._session.execute(statement)
        return [
            DocumentRead.model_validate(
                {**document.__dict__, "sku_code": sku_code, "sku_name": sku_name}
            )
            for document, sku_code, sku_name in result
        ]

    async def fetch_by_status(
        self, status: str, *, include_disabled: bool = False
    ) -> list[DocumentRead]:
        statement = (
            select(Document, Sku.sku_code)
            .join(Sku, Document.sku_id == Sku.id)
            .where(Document.processing_status == status)
            .order_by(Document.ingested_at.asc())
        )
        if not include_disabled:
            statement = statement.where(Sku.dashboard_enabled.is_(True))
        statement = statement.add_columns(
            (Sku.brand + " " + Sku.model).label("sku_name")
        )
        result = await self._session.execute(statement)
        return [
            DocumentRead.model_validate(
                {**document.__dict__, "sku_code": sku_code, "sku_name": sku_name}
            )
            for document, sku_code, sku_name in result
        ]

    async def update_status(
        self, doc_id: UUID, status: str, error: str | None = None
    ) -> bool:
        result = await self._session.execute(
            update(Document)
            .where(Document.id == doc_id)
            .values(
                processing_status=status,
                processing_error=error,
                processed_at=utcnow(),
            )
        )
        return result.rowcount == 1

    async def bulk_update_status(self, doc_ids: list[UUID], status: str) -> int:
        if not doc_ids:
            return 0
        result = await self._session.execute(
            update(Document)
            .where(Document.id.in_(doc_ids))
            .values(
                processing_status=status,
                processing_error=None,
                processed_at=utcnow(),
            )
        )
        return result.rowcount or 0
