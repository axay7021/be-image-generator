"""add_basic_plan_granted_to_users

Revision ID: b8c5e2f1d3a7
Revises: 4f315264aa95
Create Date: 2026-02-10 11:35:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8c5e2f1d3a7"
down_revision: Union[str, Sequence[str], None] = "4f315264aa95"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add basic_plan_granted column to users table
    op.add_column("users", sa.Column("basic_plan_granted", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove basic_plan_granted column from users table
    op.drop_column("users", "basic_plan_granted")
