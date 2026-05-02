"""dex pool tvl

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-02

"""
import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dex_pool_tvl",
        sa.Column("ts_bucket", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("pool_id", sa.String(80), primary_key=True),
        sa.Column("dex", sa.String(32), nullable=False),
        sa.Column("symbol", sa.String(80), nullable=False),
        sa.Column("tvl_usd", sa.Numeric(38, 6), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("dex_pool_tvl")
