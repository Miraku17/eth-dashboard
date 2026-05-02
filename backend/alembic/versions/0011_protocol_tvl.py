"""protocol tvl

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-02

"""
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "protocol_tvl",
        sa.Column("ts_bucket", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("protocol", sa.String(32), primary_key=True),
        sa.Column("asset", sa.String(20), primary_key=True),
        sa.Column("tvl_usd", sa.Numeric(38, 6), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("protocol_tvl")
