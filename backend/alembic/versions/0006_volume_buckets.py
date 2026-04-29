"""volume buckets

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-29

"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "volume_buckets",
        sa.Column("ts_bucket", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("bucket", sa.String(8), primary_key=True),
        sa.Column("usd_value", sa.Numeric(32, 2), nullable=False),
        sa.Column("trade_count", sa.BigInteger, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("volume_buckets")
