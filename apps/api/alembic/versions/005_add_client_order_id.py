"""add client_order_id column to orders table

Revision ID: 005
Revises: 003
Create Date: 2026-07-23 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("client_order_id", sa.Text(), server_default=""))


def downgrade() -> None:
    op.drop_column("orders", "client_order_id")
