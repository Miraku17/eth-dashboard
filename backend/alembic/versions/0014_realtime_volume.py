"""realtime volume

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-02

"""
import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "realtime_volume",
        sa.Column("ts_minute", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("asset", sa.String(16), primary_key=True),
        sa.Column("transfer_count", sa.Integer, nullable=False),
        sa.Column("usd_volume", sa.Numeric(38, 6), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("realtime_volume")
