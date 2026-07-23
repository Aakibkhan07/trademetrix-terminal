"""002_create_subscriptions_table

Revision ID: 002
Revises: 001
Create Date: 2026-07-05

"""

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("razorpay_subscription_id", sa.String(64), nullable=False, unique=True),
        sa.Column("razorpay_plan_id", sa.String(64), nullable=False),
        sa.Column("tier", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="created"),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trial_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_subscriptions_user_status", "subscriptions", ["user_id", "status"])
    op.create_index("ix_subscriptions_razorpay_id", "subscriptions", ["razorpay_subscription_id"])

    op.execute("""
        ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
    """)
    op.execute("""
        CREATE POLICY subscriptions_user_policy ON subscriptions
            FOR ALL
            USING (user_id = auth.uid())
            WITH CHECK (user_id = auth.uid());
    """)
    op.execute("""
        CREATE POLICY subscriptions_admin_policy ON subscriptions
            FOR ALL
            USING (auth.jwt() ->> 'role' IN ('super_admin', 'admin'));
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS subscriptions_admin_policy ON subscriptions")
    op.execute("DROP POLICY IF EXISTS subscriptions_user_policy ON subscriptions")
    op.drop_table("subscriptions")
