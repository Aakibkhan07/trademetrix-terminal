"""initial schema from supabase_schema.sql

Revision ID: 001
Revises:
Create Date: 2026-06-29 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")

    op.create_table(
        "profiles",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("email", sa.Text(), unique=True, nullable=False),
        sa.Column("full_name", sa.Text(), server_default=""),
        sa.Column("is_admin", sa.Boolean(), server_default="false"),
        sa.Column("subscription_tier", sa.Text(), server_default="free"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "broker_credentials",
        sa.Column("id", postgresql.UUID(), server_default=sa.func.gen_random_uuid(), primary_key=True),
        sa.Column("user_id", postgresql.UUID(), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("broker", sa.Text(), nullable=False),
        sa.Column("encrypted_api_key", sa.Text(), nullable=False),
        sa.Column("encrypted_secret_key", sa.Text(), nullable=False),
        sa.Column("encrypted_access_token", sa.Text(), server_default=""),
        sa.Column("additional_params", postgresql.JSONB(), server_default="{}"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "broker"),
    )

    op.create_table(
        "strategies",
        sa.Column("id", postgresql.UUID(), server_default=sa.func.gen_random_uuid(), primary_key=True),
        sa.Column("user_id", postgresql.UUID(), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), server_default="builtin"),
        sa.Column("config", postgresql.JSONB(), server_default="{}"),
        sa.Column("is_active", sa.Boolean(), server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "strategy_runs",
        sa.Column("id", postgresql.UUID(), server_default=sa.func.gen_random_uuid(), primary_key=True),
        sa.Column("user_id", postgresql.UUID(), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("strategy_id", postgresql.UUID(), sa.ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("broker", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), server_default="PAPER"),
        sa.Column("symbols", postgresql.ARRAY(sa.Text()), server_default="{}"),
        sa.Column("status", sa.Text(), server_default="stopped"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("stopped_at", sa.DateTime(timezone=True)),
        sa.Column("daily_pnl", sa.Float(), server_default="0"),
        sa.Column("total_pnl", sa.Float(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "risk_settings",
        sa.Column("id", postgresql.UUID(), server_default=sa.func.gen_random_uuid(), primary_key=True),
        sa.Column("user_id", postgresql.UUID(), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("strategy_id", postgresql.UUID(), sa.ForeignKey("strategies.id", ondelete="CASCADE")),
        sa.Column("max_capital", sa.Float(), server_default="0"),
        sa.Column("max_position_size", sa.Float(), server_default="0"),
        sa.Column("max_open_positions", sa.Integer(), server_default="10"),
        sa.Column("max_daily_loss", sa.Float(), server_default="0"),
        sa.Column("max_drawdown_pct", sa.Float(), server_default="0"),
        sa.Column("kill_switch_enabled", sa.Boolean(), server_default="false"),
        sa.Column("is_live", sa.Boolean(), server_default="false"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "strategy_id"),
    )

    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(), server_default=sa.func.gen_random_uuid(), primary_key=True),
        sa.Column("user_id", postgresql.UUID(), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("strategy_id", postgresql.UUID(), sa.ForeignKey("strategies.id", ondelete="SET NULL")),
        sa.Column("broker", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("exchange", sa.Text(), nullable=False),
        sa.Column("side", sa.Text(), nullable=False),
        sa.Column("order_type", sa.Text(), nullable=False),
        sa.Column("product", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Float(), server_default="0"),
        sa.Column("status", sa.Text(), server_default="PENDING"),
        sa.Column("filled_quantity", sa.Integer(), server_default="0"),
        sa.Column("average_price", sa.Float(), server_default="0"),
        sa.Column("message", sa.Text(), server_default=""),
        sa.Column("is_paper", sa.Boolean(), server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", postgresql.UUID(), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("resource", sa.Text(), nullable=False),
        sa.Column("resource_id", sa.Text(), server_default=""),
        sa.Column("details", postgresql.JSONB(), server_default="{}"),
        sa.Column("ip_address", sa.Text(), server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "symbol_master",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("exchange", sa.Text(), nullable=False),
        sa.Column("broker", sa.Text(), nullable=False),
        sa.Column("broker_symbol", sa.Text(), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("instrument_type", sa.Text(), server_default=""),
        sa.Column("lot_size", sa.Integer(), server_default="1"),
        sa.Column("tick_size", sa.Float(), server_default="0.05"),
        sa.Column("segment", sa.Text(), server_default=""),
        sa.Column("last_updated", sa.Date(), server_default=sa.func.current_date()),
        sa.UniqueConstraint("broker", "token"),
    )
    op.create_index("idx_symbol_master_lookup", "symbol_master", ["broker", "exchange", "symbol"])

    op.create_table(
        "plans",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("price_monthly", sa.Integer(), server_default="0"),
        sa.Column("price_yearly", sa.Integer(), server_default="0"),
        sa.Column("max_brokers", sa.Integer(), server_default="1"),
        sa.Column("max_strategies", sa.Integer(), server_default="1"),
        sa.Column("max_symbols", sa.Integer(), server_default="5"),
        sa.Column("live_trading", sa.Boolean(), server_default="false"),
        sa.Column("ai_desk", sa.Boolean(), server_default="false"),
        sa.Column("api_access", sa.Boolean(), server_default="false"),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("features", postgresql.JSONB(), server_default="[]"),
    )

    op.execute("""
        INSERT INTO public.plans (id, name, price_monthly, price_yearly, max_brokers, max_strategies, max_symbols, live_trading, ai_desk, api_access, description, features) VALUES
        ('free', 'Free', 0, 0, 1, 1, 3, FALSE, FALSE, FALSE, 'Get started with paper trading', '["1 Broker", "1 Strategy", "3 Symbols", "Paper Trading Only"]'),
        ('starter', 'Starter', 999, 9990, 2, 3, 10, FALSE, TRUE, FALSE, 'For serious learners', '["2 Brokers", "3 Strategies", "10 Symbols", "AI Trade Journal"]'),
        ('pro', 'Pro', 2499, 24990, 5, 10, 50, TRUE, TRUE, TRUE, 'For active algo traders', '["5 Brokers", "10 Strategies", "50 Symbols", "Live Trading", "AI Trading Desk", "API Access"]'),
        ('enterprise', 'Enterprise', 9999, 99990, 20, 50, 500, TRUE, TRUE, TRUE, 'For power users and firms', '["20 Brokers", "50 Strategies", "500 Symbols", "Live Trading", "AI Trading Desk", "API Access", "Priority Support"]')
    """)


def downgrade() -> None:
    op.drop_table("symbol_master")
    op.drop_table("audit_log")
    op.drop_table("orders")
    op.drop_table("risk_settings")
    op.drop_table("strategy_runs")
    op.drop_table("strategies")
    op.drop_table("broker_credentials")
    op.drop_table("plans")
    op.drop_table("profiles")
