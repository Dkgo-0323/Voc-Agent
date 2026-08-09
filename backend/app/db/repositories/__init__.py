"""Data-access repositories used by the processing pipeline and APIs."""

from backend.app.db.repositories.aspect_repo import AspectRepository
from backend.app.db.repositories.document_repo import DocumentRepository

__all__ = ["AspectRepository", "DocumentRepository"]
