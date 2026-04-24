"""smart money leaderboard snapshots

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-24

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "smart_money_leaderboard",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("run_id", UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_days", sa.SmallInteger, nullable=False),
        sa.Column("rank", sa.SmallInteger, nullable=False),
        sa.Column("wallet_address", sa.String(42), nullable=False),
        sa.Column("label", sa.String(128), nullable=True),
        sa.Column("realized_pnl_usd", sa.Numeric(20, 2), nullable=False),
        sa.Column("unrealized_pnl_usd", sa.Numeric(20, 2), nullable=True),
        sa.Column("win_rate", sa.Numeric(5, 4), nullable=True),
        sa.Column("trade_count", sa.Integer, nullable=False),
        sa.Column("volume_usd", sa.Numeric(24, 2), nullable=False),
        sa.Column("weth_bought", sa.Numeric(36, 18), nullable=False),
        sa.Column("weth_sold", sa.Numeric(36, 18), nullable=False),
    )
    op.create_index(
        "ix_leaderboard_latest",
        "smart_money_leaderboard",
        ["window_days", sa.text("snapshot_at DESC"), "rank"],
    )


def downgrade() -> None:
    op.drop_index("ix_leaderboard_latest", table_name="smart_money_leaderboard")
    op.drop_table("smart_money_leaderboard")
