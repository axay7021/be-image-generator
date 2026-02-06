"""add_is_deleted_to_plans

Revision ID: 4f315264aa95
Revises: 5f6a284d48e2
Create Date: 2026-02-06 17:52:33.631832

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4f315264aa95"
down_revision: Union[str, Sequence[str], None] = "5f6a284d48e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add is_deleted column to plans table
    op.add_column("plans", sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"))
    op.create_index("ix_plans_is_deleted", "plans", ["is_deleted"])


def downgrade() -> None:
    """Downgrade schema."""
    # Remove is_deleted column from plans table
    op.drop_index("ix_plans_is_deleted", table_name="plans")
    op.drop_column("plans", "is_deleted")
