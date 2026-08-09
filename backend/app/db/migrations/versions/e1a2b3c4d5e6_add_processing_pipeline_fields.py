"""add processing pipeline fields

Revision ID: e1a2b3c4d5e6
Revises: 70edb5646c53
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "70edb5646c53"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("processing_status", sa.String(length=20), nullable=False, server_default="raw"),
    )
    op.add_column("documents", sa.Column("processing_error", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("processed_at", sa.DateTime(), nullable=True))
    op.create_index("ix_documents_processing_status", "documents", ["processing_status"])

    op.add_column("aspect_mentions", sa.Column("sku_code", sa.Text(), nullable=True))
    op.add_column("aspect_mentions", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column("aspect_mentions", sa.Column("embed_text", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE aspect_mentions AS mention
        SET sku_code = sku.sku_code
        FROM documents AS document
        JOIN skus AS sku ON sku.id = document.sku_id
        WHERE mention.document_id = document.id
        """
    )
    op.alter_column("aspect_mentions", "sku_code", nullable=False)
    op.create_index("ix_aspect_mentions_sku_code", "aspect_mentions", ["sku_code"])
    op.create_index("ix_aspect_mentions_aspect_label", "aspect_mentions", ["aspect_label"])
    op.create_index("ix_aspect_mentions_week_id", "aspect_mentions", ["week_id"])
    op.create_index("ix_aspect_mentions_quality_score", "aspect_mentions", ["quality_score"])


def downgrade() -> None:
    op.drop_index("ix_aspect_mentions_quality_score", table_name="aspect_mentions")
    op.drop_index("ix_aspect_mentions_week_id", table_name="aspect_mentions")
    op.drop_index("ix_aspect_mentions_aspect_label", table_name="aspect_mentions")
    op.drop_index("ix_aspect_mentions_sku_code", table_name="aspect_mentions")
    op.drop_column("aspect_mentions", "embed_text")
    op.drop_column("aspect_mentions", "confidence")
    op.drop_column("aspect_mentions", "sku_code")
    op.drop_index("ix_documents_processing_status", table_name="documents")
    op.drop_column("documents", "processed_at")
    op.drop_column("documents", "processing_error")
    op.drop_column("documents", "processing_status")
