"""create strategy_health and user_strategies tables

Revision ID: 003
Revises: 002
Create Date: 2026-07-08
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "strategy_health",
        sa.Column("strategy_id", sa.Text(), primary_key=True),
        sa.Column("user_id", postgresql.UUID(), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=True),
        sa.Column("status", sa.Text(), server_default="draft"),
        sa.Column("last_run", sa.DateTime(timezone=True), nullable=True),
        sa.Column("run_count", sa.Integer(), server_default="0"),
        sa.Column("error_count", sa.Integer(), server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "user_strategies",
        sa.Column("id", postgresql.UUID(), server_default=sa.func.gen_random_uuid(), primary_key=True),
        sa.Column("user_id", postgresql.UUID(), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("strategy_type", sa.Text(), server_default="buyer"),
        sa.Column("status", sa.Text(), server_default="draft"),
        sa.Column("index_symbol", sa.Text(), server_default="NIFTY"),
        sa.Column("exit_time", sa.Text(), nullable=True),
        sa.Column("days_of_week", postgresql.ARRAY(sa.Integer()), server_default="{1,2,3,4,5}"),
        sa.Column("underlying_from", sa.Text(), server_default="option_chain"),
        sa.Column("legs", postgresql.JSONB(), server_default="[]"),
        sa.Column("config", postgresql.JSONB(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("user_strategies")
    op.drop_table("strategy_health")
