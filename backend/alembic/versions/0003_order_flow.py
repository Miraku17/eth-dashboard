"""order flow buckets

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-24

"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_flow",
        sa.Column("ts_bucket", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("side", sa.String(8), primary_key=True),
        sa.Column("usd_value", sa.Numeric(32, 2), nullable=False),
        sa.Column("trade_count", sa.BigInteger, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("order_flow")
