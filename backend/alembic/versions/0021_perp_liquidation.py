"""perp liquidation events

Revision ID: 0021
Revises: 0020
Create Date: 2026-05-04

"""
import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "perp_liquidation",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("venue", sa.String(16), nullable=False),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("price", sa.Numeric(18, 8), nullable=False),
        sa.Column("qty", sa.Numeric(38, 8), nullable=False),
        sa.Column("notional_usd", sa.Numeric(38, 6), nullable=False),
    )
    op.create_index("ix_perp_liquidation_ts", "perp_liquidation", ["ts"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_perp_liquidation_ts", table_name="perp_liquidation")
    op.drop_table("perp_liquidation")
