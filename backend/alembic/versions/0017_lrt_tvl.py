"""lrt tvl

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-03

"""
import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lrt_tvl",
        sa.Column("ts_bucket", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("protocol", sa.String(40), primary_key=True),
        sa.Column("tvl_usd", sa.Numeric(38, 6), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("lrt_tvl")
