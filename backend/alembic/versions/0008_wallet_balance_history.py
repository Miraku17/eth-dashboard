"""wallet balance history

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-01

Daily ETH balance snapshots per wallet, populated lazily on first
profile fetch and reused thereafter. Past-day rows are immutable; only
the rolling "today" row is rewritten on subsequent reads.
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wallet_balance_history",
        sa.Column("address", sa.String(42), primary_key=True),
        sa.Column("date", sa.Date, primary_key=True),
        sa.Column("block_number", sa.BigInteger, nullable=False),
        sa.Column("balance_wei", sa.Numeric(78, 0), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("wallet_balance_history")
