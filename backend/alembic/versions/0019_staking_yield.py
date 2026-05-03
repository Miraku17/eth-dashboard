"""staking yield table

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-03

"""
import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "staking_yield",
        sa.Column("kind", sa.String(8), primary_key=True),
        sa.Column("key", sa.String(40), primary_key=True),
        sa.Column("apy", sa.Numeric(10, 4), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("staking_yield")
