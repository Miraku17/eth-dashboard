"""derivatives snapshots

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-24

"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "derivatives_snapshots",
        sa.Column("exchange", sa.String(16), primary_key=True),
        sa.Column("symbol", sa.String(32), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("oi_usd", sa.Numeric(32, 2), nullable=True),
        sa.Column("funding_rate", sa.Numeric(18, 10), nullable=True),
        sa.Column("mark_price", sa.Numeric(24, 8), nullable=True),
    )
    op.create_index(
        "ix_derivatives_snapshots_ts",
        "derivatives_snapshots",
        ["ts"],
    )


def downgrade() -> None:
    op.drop_index("ix_derivatives_snapshots_ts", table_name="derivatives_snapshots")
    op.drop_table("derivatives_snapshots")
