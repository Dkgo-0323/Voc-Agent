"""add SKU dashboard enablement flag

Revision ID: f7a8b9c0d1e2
Revises: e1a2b3c4d5e6
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: str | Sequence[str] | None = "e1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "skus",
        sa.Column(
            "dashboard_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.execute(
        """
        UPDATE skus
        SET dashboard_enabled = true
        WHERE sku_code IN (
            'ecoflow-delta2',
            'jackery-explorer-1000',
            'jackery-explorer-240',
            'jackery-explorer-300',
            'anker-solix-f2000'
        )
        """
    )
    op.create_index("ix_skus_dashboard_enabled", "skus", ["dashboard_enabled"])


def downgrade() -> None:
    op.drop_index("ix_skus_dashboard_enabled", table_name="skus")
    op.drop_column("skus", "dashboard_enabled")
