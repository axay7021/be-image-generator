"""add_admin_clerk_transaction_analytics_tables

Revision ID: 5f6a284d48e2
Revises: 6220350154d9
Create Date: 2026-02-05 10:50:11.512330

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5f6a284d48e2"
down_revision: Union[str, Sequence[str], None] = "6220350154d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1. Add clerk_id column to admins table
    op.add_column("admins", sa.Column("clerk_id", sa.String(length=255), nullable=True))
    op.create_index(op.f("ix_admins_clerk_id"), "admins", ["clerk_id"], unique=True)

    # 2. Make password_hash nullable for Clerk admins
    op.alter_column("admins", "password_hash", existing_type=sa.String(length=255), nullable=True)

    # 3-5. Create enums only if they don't exist (using raw SQL for safety)
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DO $$ BEGIN CREATE TYPE paymentstatus AS ENUM ('pending', 'captured', 'failed', 'refunded'); EXCEPTION WHEN duplicate_object THEN null; END $$;"
        )
    )
    conn.execute(
        sa.text(
            "DO $$ BEGIN CREATE TYPE reconciliationstatus AS ENUM ('matched', 'unmatched', 'pending', 'manual'); EXCEPTION WHEN duplicate_object THEN null; END $$;"
        )
    )
    conn.execute(
        sa.text(
            "DO $$ BEGIN CREATE TYPE paymentprovider AS ENUM ('stripe', 'razorpay'); EXCEPTION WHEN duplicate_object THEN null; END $$;"
        )
    )

    # 6. Create transactions table (types should already exist from above or previous migrations)
    conn.execute(
        sa.text(
            """
        CREATE TABLE transactions (
            id VARCHAR(36) PRIMARY KEY,
            user_id VARCHAR(36) NOT NULL REFERENCES users(id),
            plan_id VARCHAR(36) NOT NULL REFERENCES plans(id),
            subscription_id VARCHAR(36) REFERENCES subscriptions(id),
            payment_provider_id VARCHAR(255) NOT NULL UNIQUE,
            amount NUMERIC(10, 2) NOT NULL,
            currency VARCHAR(10) NOT NULL DEFAULT 'INR',
            payment_provider paymentprovider NOT NULL,
            payment_method VARCHAR(50),
            payment_status paymentstatus NOT NULL DEFAULT 'pending',
            reconciliation_status reconciliationstatus NOT NULL DEFAULT 'matched',
            payment_metadata JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """
        )
    )

    # Create indexes for transactions
    op.create_index(op.f("ix_transactions_user_id"), "transactions", ["user_id"], unique=False)
    op.create_index(op.f("ix_transactions_plan_id"), "transactions", ["plan_id"], unique=False)
    op.create_index(op.f("ix_transactions_subscription_id"), "transactions", ["subscription_id"], unique=False)
    op.create_index(op.f("ix_transactions_payment_provider_id"), "transactions", ["payment_provider_id"], unique=True)
    op.create_index(op.f("ix_transactions_payment_provider"), "transactions", ["payment_provider"], unique=False)
    op.create_index(op.f("ix_transactions_payment_status"), "transactions", ["payment_status"], unique=False)
    op.create_index(
        op.f("ix_transactions_reconciliation_status"), "transactions", ["reconciliation_status"], unique=False
    )
    op.create_index(op.f("ix_transactions_created_at"), "transactions", ["created_at"], unique=False)

    # 7. Create daily_analytics table
    op.create_table(
        "daily_analytics",
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("total_revenue", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0"),
        sa.Column("new_users", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_subscriptions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active_subscriptions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_quota_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("razorpay_revenue", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0"),
        sa.Column("stripe_revenue", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0"),
        sa.Column("failed_transactions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("date"),
    )

    # 8. Add indexes to subscriptions table for analytics queries
    op.create_index(op.f("ix_subscriptions_created_at"), "subscriptions", ["created_at"], unique=False)
    op.create_index(op.f("ix_subscriptions_period_end"), "subscriptions", ["period_end"], unique=False)
    op.create_index(op.f("ix_subscriptions_period_start"), "subscriptions", ["period_start"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""

    # Remove indexes from subscriptions
    op.drop_index(op.f("ix_subscriptions_period_start"), table_name="subscriptions")
    op.drop_index(op.f("ix_subscriptions_period_end"), table_name="subscriptions")
    op.drop_index(op.f("ix_subscriptions_created_at"), table_name="subscriptions")

    # Drop daily_analytics table
    op.drop_table("daily_analytics")

    # Drop transactions table and its indexes
    op.drop_index(op.f("ix_transactions_user_id"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_subscription_id"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_reconciliation_status"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_plan_id"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_payment_status"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_payment_provider_id"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_payment_provider"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_created_at"), table_name="transactions")
    op.drop_table("transactions")

    # Drop enums
    sa.Enum(name="paymentprovider").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="reconciliationstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="paymentstatus").drop(op.get_bind(), checkfirst=True)

    # Revert password_hash to NOT NULL
    op.alter_column("admins", "password_hash", existing_type=sa.String(length=255), nullable=False)

    # Remove clerk_id from admins
    op.drop_index(op.f("ix_admins_clerk_id"), table_name="admins")
    op.drop_column("admins", "clerk_id")
