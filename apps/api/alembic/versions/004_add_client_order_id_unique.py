"""add unique constraint on client_order_id for duplicate prevention

Revision ID: 004
Revises: 003
Create Date: 2026-07-22 19:00:00.000000
"""
from collections.abc import Sequence

from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_orders_client_order_id",
        "orders",
        ["client_order_id"],
        unique=True,
        postgresql_where=op.text("client_order_id != ''"),
    )


def downgrade() -> None:
    op.drop_index("uq_orders_client_order_id", table_name="orders", postgresql_where=op.text("client_order_id != ''"))
